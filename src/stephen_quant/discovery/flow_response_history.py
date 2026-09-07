"""Frozen sources -> native rolling bundles -> immutable historical feature cache.

This is an engineering building block, NOT permission to start a market epoch.
The empirical runner still needs the complete preregistered budget and anchors.
No caller-supplied feature matrix is accepted by the integrated predictor path.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from stephen_quant.baseline.stateful import StatefulBar
from stephen_quant.integrity.fit_lineage import digest
from stephen_quant.qmt.flow_response_inputs import load_response_sources
from stephen_quant.qmt.flow_response_panel import build_response_panel
from stephen_quant.qmt.reliable_panel import file_sha

from .flow_response import ResponseFit, response_features
from .flow_response_predictor import (
    assert_predictor_contract,
    fit_and_bind_predictor,
    pairs_for_year,
    prefix,
    ranked_rows,
)
from .flow_response_series import (
    bind_response_bundle,
    bridge_rows,
    clock,
    fit_response_bundle,
    response_stages,
    validate_calendar,
)
from .search_power_dsl import sha256_json

VERSION = "11.21-response-history-1"


def _write(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as output:
        json.dump(value, output, sort_keys=True, allow_nan=False, separators=(",", ":"))


def _preflight(registry, provider, consumers, calendar, manifest_sha256):
    validate_calendar(calendar)
    if not consumers or len(set(consumers)) != len(consumers) or provider in consumers:
        raise ValueError("explicit unique response consumers required")
    with registry.connect() as conn:
        row = conn.execute(
            "SELECT t.experiment_id,t.hyperparams,t.result_json,f.stages_json,c.providers_json "
            "FROM trials t JOIN trial_fit_contracts f USING(trial_id) "
            "JOIN trial_feature_contracts c USING(trial_id) WHERE trial_id=?",
            (provider,),
        ).fetchone()
        if row is None or row[2] is not None or json.loads(row[4]) != []:
            raise ValueError("uncompleted explicit leaf provider required before source read")
        params = json.loads(row[1])
        if (
            json.loads(row[3]) != [asdict(s) for s in response_stages(calendar)]
            or params.get("response_history_version") != VERSION
            or params.get("response_manifest_sha256") != manifest_sha256
            or params.get("response_calendar_sha256") != sha256_json(list(calendar))
        ):
            raise ValueError("predeclared exact response source/calendar/stages required")
        snapshot_row = conn.execute(
            "SELECT s.snapshot_sha256,s.manifest_json FROM experiments e JOIN data_snapshots s "
            "ON s.snapshot_id=e.dataset_snapshot_id WHERE e.experiment_id=?",
            (row[0],),
        ).fetchone()
        if manifest_sha256 != snapshot_row[0] and manifest_sha256 not in {
            f["sha256"] for f in json.loads(snapshot_row[1])["files"]
        }:
            raise ValueError("experiment snapshot must bind the frozen source manifest")
        for tid in (provider, *consumers):
            item = conn.execute(
                "SELECT t.experiment_id,t.result_json,c.providers_json FROM trials t "
                "JOIN trial_feature_contracts c USING(trial_id) WHERE trial_id=?",
                (tid,),
            ).fetchone()
            if (
                item is None
                or item[0] != row[0]
                or item[1] is not None
                or json.loads(item[2]) != ([] if tid == provider else [provider])
                or conn.execute(
                    "SELECT 1 FROM trial_model_fits WHERE trial_id=?", (tid,)
                ).fetchone()
                or conn.execute(
                    "SELECT 1 FROM trial_feature_bindings WHERE trial_id=?", (tid,)
                ).fetchone()
            ):
                raise ValueError("unfitted same-experiment source contracts must precede reads")
    return registry.snapshot_sha256(registry.experiment_snapshot_id(row[0]))


def build_history_from_frozen(
    registry, provider, consumers, *, input_folder, output_folder, calendar, manifest_sha256
):
    snapshot = _preflight(registry, provider, consumers, calendar, manifest_sha256)
    source, root = Path(input_folder).resolve(), Path(output_folder).resolve()
    if root == source or root in source.parents or source in root.parents:
        raise ValueError("history output and frozen source trees must be disjoint")
    root.mkdir(parents=True, exist_ok=False)  # Claim once, before any numerical source read.
    rows, source_evidence = load_response_sources(
        source, expected_manifest_sha256=manifest_sha256, calendar=calendar
    )
    observations, exclusions = bridge_rows(rows["daily"], rows["fund_flow"], calendar)
    risk, bars, quality = build_response_panel(rows["daily"], calendar)
    del rows
    bundle_files = {}
    for i in range(61, len(calendar) - 1):
        bundle = fit_response_bundle(observations, calendar, i, snapshot)
        path = root / f"response-{calendar[i]}.json"
        _write(path, bundle)
        bind_response_bundle(registry, provider, bundle, path)
        bundle_files[calendar[i]] = path
    # All native fits now exist; prediction guards can run without pretending the
    # provider is complete before the actual cache has been produced and bound.
    lineage = registry.fit_lineage(provider)
    cache = {d: {} for d in calendar}
    evidence = {}
    for dt, path in bundle_files.items():
        bundle = json.loads(path.read_bytes())
        registry.assert_prediction_fit(
            provider,
            model=bundle,
            artifact_path=path,
            prediction_date=bundle["execution_date"],
            signal_date=dt,
        )  # Guard before current observations or feature values.
        features = {}
        for name in sorted(bundle["models"].keys() & observations[dt].keys() & risk[dt].keys()):
            current, model = observations[dt][name], ResponseFit(**bundle["models"][name])
            response = response_features(
                model,
                current,
                decision_at=clock(dt, "23:59:59"),
                expected_model_sha256=model.sha256,
            )
            features[name] = risk[dt][name] | {
                "flow_ratio": current.flow_ratio,
                "close_return": current.close_return,
                **{
                    k: response[k]
                    for k in ("flow_surprise", "standardized_own_return", "price_response_residual")
                },
            }
        cache[dt] = ranked_rows(features)
        evidence[dt] = {
            "bundle_file": path.name,
            "bundle_sha256": file_sha(path),
            "bundle_content_sha256": digest(bundle),
            "feature_values_sha256": sha256_json(features),
            "ranked_rows_sha256": sha256_json(cache[dt]),
            "support": len(cache[dt]),
            "current_observations_sha256": sha256_json(
                {n: asdict(o) for n, o in observations[dt].items()}
            ),
            "risk_rows_sha256": sha256_json(risk[dt]),
        }
    document = {
        "version": VERSION,
        "provider_id": provider,
        "snapshot_sha256": snapshot,
        "source_evidence": source_evidence,
        "calendar": list(calendar),
        "native_fit_lineage_sha256": lineage["sha256"],
        "ranks": cache,
        "bars": {d: {n: asdict(b) for n, b in items.items()} for d, items in bars.items()},
        "days": evidence,
        "bridge_exclusions": exclusions,
        "panel_quality": quality,
        "validated_alpha": False,
    }
    path = root / "history.json"
    _write(path, document)
    # This actual cache-byte digest is frozen into the append-only provider result.
    # A caller cannot swap the matrix and replace an unauthenticated sidecar hash.
    registry.record_trial_result(
        provider,
        json.dumps(
            {
                "feature_provider_ready": True,
                "native_fit_lineage_sha256": lineage["sha256"],
                "response_history_version": VERSION,
                "history_artifact_sha256": file_sha(path),
                "source_evidence_sha256": sha256_json(source_evidence),
            },
            sort_keys=True,
        ),
    )
    for consumer in consumers:
        registry.bind_feature_source(consumer, provider)
    return path


def read_verified_history(registry, consumer, path):
    sources = registry.feature_sources(consumer)  # Must precede all cached numeric values.
    if len(sources["providers"]) != 1:
        raise ValueError("one completed historical response provider required")
    provider = sources["providers"][0]
    with registry.connect() as conn:
        result = json.loads(
            conn.execute("SELECT result_json FROM trials WHERE trial_id=?", (provider,)).fetchone()[
                0
            ]
        )
    if result.get("response_history_version") != VERSION or file_sha(path) != result.get(
        "history_artifact_sha256"
    ):
        raise ValueError("historical matrix bytes differ from native provider result")
    document = json.loads(Path(path).read_bytes())
    validate_calendar(document["calendar"])
    if (
        document["version"] != VERSION
        or document["provider_id"] != provider
        or document["native_fit_lineage_sha256"] != result["native_fit_lineage_sha256"]
        or sha256_json(document["source_evidence"]) != result["source_evidence_sha256"]
    ):
        raise ValueError("historical source identity changed")
    # Recheck all persisted model files against their native records once per cache
    # load, not on every cost/day. No shared provider fit is recomputed here.
    fits = {f["stage"]["stage_id"]: f for f in registry.fit_lineage(provider)["fits"]}
    for dt, proof in document["days"].items():
        fit = fits[f"response-{dt}"]
        bundle_path = Path(path).parent / f"response-{dt}.json"
        if (
            proof["bundle_file"] != bundle_path.name
            or file_sha(bundle_path) != proof["bundle_sha256"]
            or proof["bundle_sha256"] != fit["artifact_sha256"]
            or proof["bundle_content_sha256"] != fit["model_content_sha256"]
            or sha256_json(document["ranks"][dt]) != proof["ranked_rows_sha256"]
        ):
            raise ValueError("historical bundle/rank proof changed")
    return document, {
        "history_artifact_sha256": result["history_artifact_sha256"],
        "native_fit_lineage_sha256": result["native_fit_lineage_sha256"],
        "source_evidence_sha256": result["source_evidence_sha256"],
    }


class _FrozenDict(dict):
    def _reject(self, *args, **kwargs):
        raise TypeError("verified historical cache is immutable")

    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = __ior__ = _reject


def _freeze(value):
    if isinstance(value, dict):
        return _FrozenDict({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


class VerifiedHistoryCache:
    """One-process immutable decode; preserve native/actual-file checks on each use.

    This avoids repeatedly parsing a large historical matrix. It is not a saved
    authorization token and cannot accept a caller-supplied matrix.
    """

    def __init__(self, registry, consumer, path):
        document, proof = read_verified_history(registry, consumer, path)
        self._path = Path(path).resolve()
        self._document, self._proof = _freeze(document), _freeze(proof)
        self._sources = _freeze(registry.feature_sources(consumer))

    def get(self, registry, consumer, path):
        if (
            Path(path).resolve() != self._path
            or sha256_json(registry.feature_sources(consumer)) != sha256_json(self._sources)
            or file_sha(self._path) != self._proof["history_artifact_sha256"]
        ):
            raise ValueError("verified cache source/path/bytes changed")
        for proof in self._document["days"].values():
            if file_sha(self._path.parent / proof["bundle_file"]) != proof["bundle_sha256"]:
                raise ValueError("verified cache bundle bytes changed")
        return self._document, dict(self._proof)


def verified_history(registry, consumer, path, *, cache=None):
    if cache is None:
        return read_verified_history(registry, consumer, path)
    if type(cache) is not VerifiedHistoryCache:
        raise ValueError("only a runtime-verified historical cache is accepted")
    return cache.get(registry, consumer, path)


def fit_history_predictor(
    registry, consumer, provider, *, history_path, year, policy, model_path, cache=None
):
    assert_predictor_contract(registry, consumer, provider, year, policy, model_path)
    history, provenance = verified_history(registry, consumer, history_path, cache=cache)
    days = prefix(history["calendar"], year)
    # Materialize training bars only inside the already-purged mature prefix.
    bars = {d: {n: StatefulBar(**b) for n, b in history["bars"][d].items()} for d in days}
    pairs = pairs_for_year(history["calendar"], history["ranks"], bars, year)
    provenance["training_prefix_sha256"] = sha256_json(
        {
            "calendar": days,
            "ranks": {d: history["ranks"][d] for d in days},
            "bars": {d: history["bars"][d] for d in days},
            "days": {d: history["days"][d] for d in days if d in history["days"]},
        }
    )
    return fit_and_bind_predictor(
        registry,
        consumer,
        provider,
        pairs=pairs,
        calendar=history["calendar"],
        year=year,
        policy=policy,
        artifact_path=model_path,
        training_provenance=provenance,
    )


def bind_shared_history_predictor(
    registry, source_trial, consumer, provider, *, history_path, model_path, year, policy, calendar
):
    """Reuse actual fitted bytes for the other counted cost Trial; never call a fit."""
    target_sources = assert_predictor_contract(
        registry, consumer, provider, year, policy, model_path, new_artifact=False
    )
    source_sources = registry.feature_sources(source_trial)
    validate_calendar(calendar)
    if source_trial == consumer or target_sources != source_sources:
        raise ValueError("distinct cost consumers of exactly the same provider required")
    with registry.connect() as conn:
        metadata = [
            json.loads(
                conn.execute("SELECT hyperparams FROM trials WHERE trial_id=?", (t,)).fetchone()[0]
            )
            for t in (source_trial, consumer)
        ]
    if (
        any(m.get("response_policy") != policy for m in metadata)
        or any(m.get("response_calendar_sha256") != sha256_json(list(calendar)) for m in metadata)
        or {m.get("roundtrip_bps") for m in metadata} != {82, 164}
        or {k: v for k, v in metadata[0].items() if k not in {"key", "roundtrip_bps"}}
        != {k: v for k, v in metadata[1].items() if k not in {"key", "roundtrip_bps"}}
    ):
        raise ValueError("only82/164cost may differ for shared fitted predictors")
    model = json.loads(Path(model_path).read_bytes())
    days = [d for d in calendar if d.startswith(str(year))]
    if len(days) < 2:
        raise ValueError("actual registered prediction sessions required")
    # Native file identity and completed source stages, before any target/predictor use.
    registry.assert_prediction_fit(
        source_trial,
        model=model,
        artifact_path=model_path,
        prediction_date=days[1],
        signal_date=days[0],
    )
    if (
        model["year"] != year
        or model["policy"] != policy
        or model["feature_sources_sha256"] != target_sources["sha256"]
        or model.get("training_provenance", {}).get("history_artifact_sha256")
        != file_sha(history_path)
    ):
        raise ValueError("shared predictor lacks exact historical provenance")
    return registry.record_model_fit(consumer, str(year), model=model, artifact_path=model_path)
