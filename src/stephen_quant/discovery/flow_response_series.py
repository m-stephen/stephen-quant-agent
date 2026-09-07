"""As-of daily/flow row bridge and shared native response bundles.

No filesystem source reader or empirical runner lives here. These primitives are
tested with synthetic records; the complete market preregistration is pending.
"""

from __future__ import annotations

import math
from dataclasses import asdict
from datetime import date, datetime

from stephen_quant.integrity.fit_lineage import UnsupervisedFitStage

from .flow_response import (
    LOOKBACK,
    ResponseFit,
    ResponseObservation,
    aware,
    fit_response_prefix,
    validate_response_fit,
)
from .flow_response import response_features as evaluate_response
from .search_power_dsl import sha256_json

VERSION = "11.21-response-series-1"


def validate_calendar(calendar):
    if (
        not calendar
        or list(calendar) != sorted(set(calendar))
        or any(
            not isinstance(d, str)
            or date.fromisoformat(d).isoformat() != d
            or not "2022-01-01" <= d <= "2024-12-31"
            for d in calendar
        )
    ):
        raise ValueError("explicit ordered 2022-2024 global calendar required")


def clock(day, time):
    return f"{day}T{time}+08:00"


def timestamp(value):
    # Parquet timestamp values may already be aware datetime objects. No guessed timezone.
    return aware(value.isoformat() if isinstance(value, datetime) else value)


def bridge_rows(daily_rows, flow_rows, calendar):
    """Strict key join, daily amount thousands->CNY, adjusted close-to-close return.

    Visibility is vendor-recorded historical availability, not a live first-seen
    certificate. Observations unavailable by their own signal-day end are excluded
    permanently in this bounded protocol; no retrospective backfill into a fit.
    """
    validate_calendar(calendar)
    allowed, indexed = set(calendar), {}
    for source, rows in (("daily", daily_rows), ("fund_flow", flow_rows)):
        table = {d: {} for d in calendar}
        for row in rows:
            dt, asset = str(row["trade_date"]), row["instrument"]
            if (
                dt not in allowed
                or not isinstance(asset, str)
                or not asset
                or asset.strip() != asset
            ):
                raise ValueError("source key outside frozen calendar or invalid asset")
            if asset in table[dt]:
                raise ValueError("duplicate source key")
            table[dt][asset] = row
        indexed[source] = table
    # Foreign keys are not silently dropped, including flow-only symbols/dates.
    if any(indexed["fund_flow"][d].keys() - indexed["daily"][d].keys() for d in calendar):
        raise ValueError("flow keys without a daily source record")
    by_date = indexed["daily"]
    observations, exclusions, previous = {d: {} for d in calendar}, [], {}
    for i, dt in enumerate(calendar):
        decision, close_clock = aware(clock(dt, "23:59:59")), aware(clock(dt, "15:00:00"))
        for asset, row in sorted(by_date[dt].items()):
            reason, prior = None, previous.pop(asset, None)
            if row["available_at"] is None:
                reason = "daily_timestamp_missing"
            else:
                visible = timestamp(row["available_at"])
                if visible > decision:
                    reason = "daily_not_available"
            if reason:
                exclusions.append({"date": dt, "asset": asset, "reason": reason})
                continue  # Do not inspect poisoned/unavailable numeric columns.
            raw, factor = row["close"], row["adjustment_factor"]
            if any(v is None or not math.isfinite(v) or v <= 0 for v in (raw, factor)):
                exclusions.append({"date": dt, "asset": asset, "reason": "invalid_close"})
                continue
            adjusted = raw * factor
            if not math.isfinite(adjusted):
                raise ValueError("nonfinite source-adjusted close")
            previous[asset] = (i, adjusted, max(visible, close_clock))
            flow = indexed["fund_flow"][dt].get(asset)
            if prior is None or prior[0] != i - 1:
                reason = "missing_previous_global_close"
            elif flow is None or flow["available_at"] is None:
                reason = "flow_missing"
            else:
                flow_at = timestamp(flow["available_at"])
                if flow_at > decision:
                    reason = "flow_not_available"
            if reason:
                exclusions.append({"date": dt, "asset": asset, "reason": reason})
                continue
            amount, net = row["amount"], flow["net_inflow_amount"]
            if (
                amount is None
                or net is None
                or not math.isfinite(amount)
                or not math.isfinite(net)
                or amount <= 0
            ):
                exclusions.append(
                    {"date": dt, "asset": asset, "reason": "invalid_flow_denominator"}
                )
                continue
            denominator = amount * 1000
            if not math.isfinite(denominator):
                exclusions.append(
                    {"date": dt, "asset": asset, "reason": "invalid_flow_denominator"}
                )
                continue
            ratio, ret = net / denominator, adjusted / prior[1] - 1
            if not all(math.isfinite(v) for v in (ratio, ret)) or ret <= -1:
                exclusions.append({"date": dt, "asset": asset, "reason": "invalid_response_input"})
                continue
            available = max(close_clock, visible, flow_at, prior[2])
            observations[dt][asset] = ResponseObservation(
                asset, i, close_clock.isoformat(), available.isoformat(), ratio, ret
            )
    return observations, exclusions


def response_stages(calendar):
    validate_calendar(calendar)
    # index0 has no preceding adjusted close; the first complete fit is signal index61.
    return tuple(
        UnsupervisedFitStage(
            f"response-{calendar[i]}",
            calendar[i - LOOKBACK],
            calendar[i - 1],
            calendar[i + 1],
            calendar[i + 1],
        )
        for i in range(LOOKBACK + 1, len(calendar) - 1)
    )


def fit_response_bundle(observations, calendar, signal_index, snapshot_sha256):
    validate_calendar(calendar)
    i = signal_index
    if type(i) is not int or not LOOKBACK + 1 <= i < len(calendar) - 1:
        raise ValueError("registered response signal session required")
    signal, execution = calendar[i], calendar[i + 1]
    prefix_dates = list(calendar[i - LOOKBACK : i])
    names = sorted(observations[calendar[i - 1]])  # Never use today's/future stock presence to fit.
    models, excluded = {}, {}
    for asset in names:
        history = [observations[d].get(asset) for d in prefix_dates]
        if any(o is None for o in history):
            excluded[asset] = "missing_global_session"
            continue
        try:
            model = fit_response_prefix(
                history,
                cutoff=clock(signal, "09:00:00"),
                prediction_session=i,
                snapshot_sha256=snapshot_sha256,
            )
        except ValueError as exc:
            excluded[asset] = str(exc)
            continue
        if model.asset != asset:
            raise ValueError("source/model asset mismatch")
        models[asset] = asdict(model)
    if not models:
        # Do not manufacture successful native fit evidence from zero observations.
        raise ValueError("no identifiable prefix models; record failed operation, not fake fit")
    return {
        "version": VERSION,
        "fit_kind": "unsupervised",
        "year": int(execution[:4]),
        "signal_date": signal,
        "execution_date": execution,
        "global_signal_index": i,
        "stage_id": f"response-{signal}",
        "snapshot_sha256": snapshot_sha256,
        "fit_cutoff": calendar[i - 1],
        "maximum_observation_at": calendar[i - 1],
        "training_observation_sessions": prefix_dates,
        "training_observation_dates": LOOKBACK,
        "calendar_window_sha256": sha256_json(list(calendar[i - LOOKBACK : i + 2])),
        "models": models,
        "excluded": excluded,
        "model_count": len(models),
        "model_training_observations": len(models) * LOOKBACK,
        "attempted_assets": names,
        "not_causal": True,
        "validated_alpha": False,
    }


def validate_bundle(bundle):
    if (
        bundle["version"] != VERSION
        or bundle["fit_kind"] != "unsupervised"
        or bundle["model_count"] != len(bundle["models"])
        or bundle["model_training_observations"] != len(bundle["models"]) * LOOKBACK
        or not bundle["models"]
        or set(bundle["models"]) & set(bundle["excluded"])
        or sorted(set(bundle["models"]) | set(bundle["excluded"])) != bundle["attempted_assets"]
    ):
        raise ValueError("response bundle identity/coverage failed")
    sessions = bundle["training_observation_sessions"]
    validate_calendar(sessions + [bundle["signal_date"], bundle["execution_date"]])
    if (
        len(sessions) != LOOKBACK
        or sessions != sorted(set(sessions))
        or bundle["training_observation_dates"] != LOOKBACK
        or not sessions[-1] == bundle["fit_cutoff"] == bundle["maximum_observation_at"]
        or not sessions[-1] < bundle["signal_date"] < bundle["execution_date"]
        or bundle["stage_id"] != f"response-{bundle['signal_date']}"
        or type(bundle["global_signal_index"]) is not int
        or bundle["global_signal_index"] < LOOKBACK + 1
        or bundle["year"] != int(bundle["execution_date"][:4])
        or bundle["calendar_window_sha256"]
        != sha256_json(sessions + [bundle["signal_date"], bundle["execution_date"]])
    ):
        raise ValueError("response bundle training chronology failed")
    for asset, payload in bundle["models"].items():
        model = ResponseFit(**payload)
        validate_response_fit(model)
        if (
            model.asset != asset
            or model.snapshot_sha256 != bundle["snapshot_sha256"]
            or model.prediction_session != bundle["global_signal_index"]
            or model.fit_cutoff != clock(bundle["signal_date"], "09:00:00")
            or model.last_observed_at[:10] != sessions[-1]
            or model.last_session != model.prediction_session - 1
            or model.first_session != model.prediction_session - LOOKBACK
        ):
            raise ValueError("response member model lineage mismatch")
    return sha256_json(bundle)


def bind_response_bundle(registry, provider_trial, bundle, path):
    validate_bundle(bundle)
    with registry.connect() as conn:
        row = conn.execute(
            "SELECT experiment_id FROM trials WHERE trial_id=?", (provider_trial,)
        ).fetchone()
        if row is None:
            raise ValueError("response provider Trial required")
    expected = registry.snapshot_sha256(registry.experiment_snapshot_id(row[0]))
    if (
        expected != bundle["snapshot_sha256"]
        or registry.feature_sources(provider_trial)["providers"]
    ):
        raise ValueError("response provider snapshot/leaf contract mismatch")
    return registry.record_model_fit(
        provider_trial, bundle["stage_id"], model=bundle, artifact_path=path
    )


def guarded_response_values(registry, consumer_trial, provider_trial, bundle, path, current_rows):
    sources = registry.feature_sources(consumer_trial)
    if sources["providers"] != [provider_trial]:
        raise ValueError("exact shared response source required")
    validate_bundle(bundle)
    registry.assert_prediction_fit(
        provider_trial,
        model=bundle,
        artifact_path=path,
        prediction_date=bundle["execution_date"],
        signal_date=bundle["signal_date"],
    )
    result = {}
    for asset in sorted(bundle["models"].keys() & current_rows.keys()):
        current = current_rows[asset]
        if current.asset != asset:
            raise ValueError("current source key mismatch")
        model = ResponseFit(**bundle["models"][asset])
        result[asset] = evaluate_response(
            model,
            current,
            decision_at=clock(bundle["signal_date"], "23:59:59"),
            expected_model_sha256=model.sha256,
        )
    return result
