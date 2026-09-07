"""Exclusive V11.15 operation. All90 native trials reserved before numerical reads."""

import argparse
import csv
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

from stephen_quant.discovery.risk_stratified import mechanism_days
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.discovery.signal_timing import (
    FIELDS,
    VERSION,
    contract,
    day_response,
    endpoints,
    mature_indices,
    memberships,
    plans,
    require_contract,
    strong_responses,
    summarize,
)
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest
from stephen_quant.qmt.reliable_panel import file_sha, load_frozen_days
from stephen_quant.workflows.v114_reliable_epoch import (
    protected_digest,
    runtime_code_hash,
    write_json,
)

PARENT_SHA = "c364e7c720f38e4cb5d621af2ef988834a5e47cd392afc62ca8fa169b3b790d0"
SNAPSHOT_SHA = "b813a94d5342013488b8192e8ecf940c898ce984e47fbe2fdcb95a3c570c5a51"
CARD_SHA = "c854fad704e08902051a3c4f2f25fdaeb8c9e7d32cda6b69bb76bf3fc6302134"
CLAIMS = Path(__file__).resolve().parents[1] / "artifacts/signal-timing/claims"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run(path):
    cfg = read(path)
    parent, original, inputs, output = [
        Path(cfg[k]).resolve() for k in ("parent_dir", "original_tree", "input_dir", "output_dir")
    ]
    if type(cfg.get("preregistration_comment")) is not int or cfg["preregistration_comment"] <= 0:
        raise ValueError("preregistration required")
    if output.exists() or any(
        output == p or output in p.parents or p in output.parents
        for p in (parent, original, inputs)
    ):
        raise ValueError("new independent output required;never rerun")
    prior = read(parent / "RESULT.json")
    card = original / "configs/v11.11-frozen-stability-observation.json"
    if (
        file_sha(parent / "RESULT.json") != PARENT_SHA
        or prior["raw_global_trial_lower_bound"] != 3366
        or not read(parent / "INDEPENDENT_AUDIT.json")["pass"]
        or file_sha(card) != CARD_SHA
    ):
        raise ValueError("parent/debt/card integrity mismatch")
    manifest = read(inputs / "manifest.json")
    if (
        sha256_json(manifest["sources"]) != SNAPSHOT_SHA
        or manifest["snapshot_sha256"] != SNAPSHOT_SHA
    ):
        raise ValueError("snapshot mismatch")
    source_paths = []
    for s in manifest["sources"]:
        source = (inputs / s["file"]).resolve()
        if (
            source.parent != inputs
            or s["max_date"] >= "2025-01-01"
            or file_sha(source) != s["sha256"]
        ):
            raise ValueError("source bounds/hash mismatch")
        source_paths.append(source)
    protected = [
        parent / "RESULT.json",
        parent / "registry.sqlite3",
        card,
        original / "artifacts/temporal-increments/epoch-001/targets/lowvol.json",
        original / "artifacts/temporal-increments/epoch-001/targets/stable_lowrisk.json",
        inputs / "manifest.json",
        *source_paths,
    ]
    before, _ = protected_digest(protected)
    planned = plans()
    spec = {
        "contract": contract(),
        "plans": planned,
        "parent_sha256": PARENT_SHA,
        "snapshot_sha256": SNAPSHOT_SHA,
        "runtime_sha256": runtime_code_hash(),
        "driver_sha256": file_sha(Path(__file__)),
        "preregistration_comment": cfg["preregistration_comment"],
        "protected_before": before,
        "protected_files": {str(p): file_sha(p) for p in protected},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(CLAIMS / f"{PARENT_SHA}.json", {"reserved": 90, "spec_sha256": sha256_json(spec)})
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "frozen_spec.json", spec)
    write_json(
        output / "first_read_reservations.json",
        {"spec_sha256": sha256_json(spec), "plans": planned},
    )
    try:
        registry = ExperimentRegistry(output / "registry.sqlite3")
        sid = registry.register_snapshot(
            build_composite_snapshot_manifest({"inputs": SNAPSHOT_SHA}), vendor_version=VERSION
        )
        eid = registry.create_experiment_deterministic(
            ExperimentSpec(
                "signal_timing",
                "locate the response relative to executable entry",
                sid,
                spec["runtime_sha256"],
                json.dumps(spec),
            ),
            sha256_json(spec),
        )
        tids = {
            p["key"]: registry.create_trial_deterministic(
                TrialSpec(
                    eid,
                    p["key"],
                    sha256_json(p),
                    json.dumps(p),
                    184,
                    "unused",
                    "unused",
                    "2023-01-01",
                    "2024-12-31",
                    "unused",
                    "unused",
                    fit_stages=(),
                ),
                sha256_json(p),
            )[0]
            for p in planned
        }
        require_contract(registry, tids)
        print(json.dumps({"reserved": 90, "stage": "before_numerical_read"}), flush=True)
        days, quality = load_frozen_days(inputs)
        write_json(output / "DATA_PREFLIGHT.json", quality)
        panel, coverage = mechanism_days(days)
        write_json(output / "coverage.json", coverage)
        maps = [{b.instrument: b for b in d.bars} for d in panel]
        indices = mature_indices(panel)
        daily, count, writer = [], 0, None
        evidence = output / "endpoints.csv.gz"
        with gzip.open(evidence, "xt", encoding="utf-8", newline="") as stream:
            for i in indices:
                # Membership is frozen before retrieving any future endpoint for this date.
                selected = memberships(panel[i].features)
                rows = [
                    {
                        **endpoints(panel, maps, i, n),
                        **selected[n],
                        **{k: panel[i].features[n][k] for k in FIELDS},
                    }
                    for n in sorted(selected)
                ]
                if writer is None:
                    writer = csv.DictWriter(stream, list(rows[0]))
                    writer.writeheader()
                writer.writerows(rows)
                count += len(rows)
                daily.extend(day_response(rows))
                if len(daily) % (90 * 40) == 0:
                    print(
                        json.dumps({"signal_dates": len(daily) // 90, "evidence_rows": count}),
                        flush=True,
                    )
        write_json(output / "date_responses.json", daily)
        summary = summarize(daily)
        for p in planned:
            registry.record_trial_result(
                tids[p["key"]],
                json.dumps(
                    [
                        r
                        for r in summary
                        if (r["group"], r["policy"], r["label"])
                        == (p["group"], p["policy"], p["label"])
                    ],
                    sort_keys=True,
                ),
            )
        if (
            protected_digest(protected)[0] != before
            or runtime_code_hash() != spec["runtime_sha256"]
            or file_sha(Path(__file__)) != spec["driver_sha256"]
        ):
            raise ValueError("protected evidence or runtime changed")
        result = {
            "version": VERSION,
            "spec": spec,
            "completed_trials": 90,
            "reserved_trials": 90,
            "raw_global_trial_lower_bound": 3456,
            "evidence_rows": count,
            "signal_dates": len(indices),
            "first_signal": panel[indices[0]].date,
            "last_signal": panel[indices[-1]].date,
            "summary": summary,
            "strong_responses": strong_responses(summary),
            "validated_alpha": False,
            "restricted_rows_read": 0,
            "protected_unchanged": True,
            "evidence_sha256": file_sha(evidence),
            "daily_sha256": file_sha(output / "date_responses.json"),
            "statistics": {
                "status": "EXPLORATORY_RESPONSE_NOT_ACCOUNT_OR_COURT",
                "DSR": None,
                "PBO": None,
                "placebo": None,
            },
        }
        write_json(output / "RESULT.json", result)
        print(
            json.dumps(
                {"completed": 90, "strong_responses": result["strong_responses"], "debt": 3456}
            ),
            flush=True,
        )
    except Exception as exc:
        write_json(output / "ABORTED.json", {"error_type": type(exc).__name__, "reserved": 90})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    run(parser.parse_args().config)
