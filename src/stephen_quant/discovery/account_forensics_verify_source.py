"""Independent source value/time reference; never calls producer source helpers."""

import math
from datetime import date, datetime

from .account_forensics_verify import compare


def reference_source_row(dt, name, source, bar):
    if (not isinstance(dt, str) or date.fromisoformat(dt).isoformat() != dt
            or not "2022-01-01" <= dt <= "2024-12-31"
            or not isinstance(name, str) or not name or name.strip() != name):
        raise ValueError("canonical frozen source key required")
    answer = {
        "date": dt, "instrument": name, "source_row_present": source is not None,
        "saved_bar_present": bar is not None, "classification": "unknown", "reason": None,
        "adjusted_open": None, "adjusted_close": None,
        "actual_suspension_or_delisting_verified": False, "retrospective_only": True,
    }

    def finish(category, reason):
        answer.update(classification=category, reason=reason)
        return answer

    if bar is not None:
        if not isinstance(bar, dict) or not {"trade_date", "instrument", "open_price", "close_price"} <= bar.keys():
            return finish("unknown", "incomplete_saved_bar_projection")
        if (bar["trade_date"], bar["instrument"]) != (dt, name):
            raise ValueError("independent saved bar identity mismatch")
    if source is None:
        return finish("source_absent" if bar is None else "implementation_mismatch",
                      "no_frozen_source_row" if bar is None else "saved_bar_without_frozen_source_row")
    if not isinstance(source, dict) or not {
        "trade_date", "instrument", "open", "close", "amount", "adjustment_factor", "available_at"
    } <= source.keys():
        return finish("unknown", "incomplete_source_projection")
    if (source["trade_date"], source["instrument"]) != (dt, name):
        raise ValueError("independent source row identity mismatch")
    available = source["available_at"]
    try:
        if available is None:
            visible = False
        else:
            parsed = datetime.fromisoformat(available.isoformat() if isinstance(available, datetime) else available)
            if parsed.tzinfo is None:
                raise ValueError("missing timezone")
            visible = parsed <= datetime.fromisoformat(dt + "T23:59:59+08:00")
    except (ValueError, TypeError, OverflowError):
        return finish("unknown", "unparseable_source_time_requires_pipeline_investigation")

    def refused(reason):
        return finish("format_time_refused" if bar is None else "implementation_mismatch", reason)

    if not visible:
        return refused("daily_not_available")
    numeric = [source[k] for k in ("close", "adjustment_factor", "amount", "open")]
    if any(x is not None and type(x) not in (int, float) for x in numeric):
        return finish("unknown", "nonnumeric_source_type_requires_pipeline_investigation")
    closing, factor, amount, opening = numeric
    if (any(x is None or not math.isfinite(x) for x in (closing, factor, amount))
            or closing <= 0 or factor <= 0 or amount < 0):
        return refused("invalid_daily_history")
    if not all(math.isfinite(x) for x in (closing * factor, amount * 1000)):
        return finish("unknown", "overflow_would_abort_panel_requires_investigation")
    if opening is None or not math.isfinite(opening) or opening <= 0 or not math.isfinite(opening * factor):
        return refused("invalid_bar_accounted_as_missing")
    volume, display = source.get("volume"), source.get("name")
    if (volume is not None and type(volume) not in (int, float)) or (
            display is not None and not isinstance(display, str)):
        return finish("unknown", "nonstandard_tradability_metadata_requires_pipeline_investigation")
    answer.update(adjusted_open=opening * factor, adjusted_close=closing * factor)
    if bar is None:
        return finish("implementation_mismatch", "visible_valid_row_filtered_out_of_saved_execution_bars")
    for field, value in (("open_price", opening * factor), ("close_price", closing * factor)):
        observed = bar[field]
        if (type(observed) not in (int, float) or not math.isfinite(observed)
                or not math.isclose(observed, value, rel_tol=1e-10, abs_tol=1e-6)):
            return finish("implementation_mismatch", "saved_bar_adjusted_price_mismatch")
    return finish("source_and_saved_bar_match", "visible_source_adjusted_open_close_reconciled")


def verify_source_row(dt, name, source, bar, emitted):
    compare(emitted, reference_source_row(dt, name, source, bar))
    return {"source_row_interpretation_verified": True,
            "actual_suspension_or_delisting_verified": False, "validated_alpha": False}


def _status(rows):
    labels = {r["classification"] for r in rows}
    if "implementation_mismatch" in labels:
        return "IMPLEMENTATION_MISMATCH"
    return "UNKNOWN" if "unknown" in labels else "EXPLAINED_BY_FROZEN_SOURCE"


def verify_source_details(reference, emitted, *, lookups, bars):
    """Use reference derived internally from raw account/history, never producer JSON.

    Call only after independent global query coverage and actual reader byte checks.
    This verifies explanations of saved events, not market suspension or delisting.
    """
    compare(emitted["account"], reference["account"])
    statuses = []
    for label in ("events", "open_stale_chains"):
        actual = emitted[label]
        expected = reference[label]
        key = (lambda e: (e["date"], e["instrument"], e["event_type"])) if label == "events" else (
            lambda e: e["instrument"])
        by_key = {key(e): e for e in actual}
        if len(by_key) != len(actual) or set(by_key) != {key(e) for e in expected}:
            raise ValueError("independent source explanation identity coverage mismatch")
        for event in expected:
            out = by_key[key(event)]
            compare({k: out[k] for k in event}, event)
            name, chain = event["instrument"], event["stale_chain"]
            dates = [chain["last_marked_date"]] + [r["date"] for r in chain["missing_sessions"]]
            if event.get("event_type") == "recovery":
                dates.append(event["date"])
            rows = []
            for dt in dates:
                if (dt, name) not in lookups or dt not in bars:
                    raise ValueError("explicit source/bar lookup required for every reference event row")
                rows.append(reference_source_row(dt, name, lookups[(dt, name)], bars[dt].get(name)))
            compare(out["source_rows"], rows)
            status = _status(rows)
            statuses.append(status)
            compare(out["source_explanation_status"], status)
            compare(out["actual_suspension_or_delisting_verified"], False)
            if label != "events":
                continue
            compare(out["cash_receipt_inferred_from_recovery"], False)
            if event["event_type"] == "recovery":
                value, explanation = None, rows[-1]["classification"]
                if explanation == "source_and_saved_bar_match":
                    value = event["prior_shares"] * rows[-1]["adjusted_open"]
                    compare(value, event["saved_bar_recovery_cny"])
                    explanation = "SOURCE_OPEN_TIMES_PRIOR_SHARES_RECONCILED"
                compare(out["source_recovery_cny"], value)
                compare(out["source_recovery_status"], explanation)
            else:
                value = None
                if rows[0]["classification"] == "source_and_saved_bar_match":
                    value = event["prior_shares"] * rows[0]["adjusted_close"]
                    compare(value, event["amount_cny"])
                compare(out["source_last_mark_writeoff_cny"], value)
    overall = ("IMPLEMENTATION_MISMATCH" if "IMPLEMENTATION_MISMATCH" in statuses else
               "UNKNOWN" if "UNKNOWN" in statuses else "EXPLAINED_BY_FROZEN_SOURCE" if statuses else
               "NO_WRITEOFF_RECOVERY_EVENTS_OR_OPEN_STALE_CHAINS")
    compare(emitted["source_explanation_status"], overall)
    compare(emitted["source_truth_verified"], False)
    return {"independent_source_explanations_verified": True, "source_explanation_status": overall,
            "events": len(reference["events"]), "open_stale_chains": len(reference["open_stale_chains"]),
            "actual_suspension_or_delisting_verified": False, "validated_alpha": False}
