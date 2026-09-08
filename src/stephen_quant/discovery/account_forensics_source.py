"""Pure frozen source versus saved bar evidence; no provider or account execution."""

import math

from .account_forensics import close, day
from .flow_response import aware
from .flow_response_series import clock, timestamp


def _valid(value, positive=False):
    return (type(value) in (float, int) and math.isfinite(value)
            and (value > 0 if positive else value >= 0))


def source_bar_evidence(dt, name, *, source_row, saved_bar):
    """Both inputs must be an explicit indexed lookup: None means verified absence.

    Caller must bind source/history bytes and actually inspect the requested key.
    Never pass None merely because a lookup was not performed. Invalid incomplete
    mappings yield unknown, not a fabricated absence. Missing bars do NOT establish
    suspension, delisting or fraudulent data. Valid rows excluded from the saved
    panel are flagged as an implementation mismatch, not repaired here.
    """
    day(dt)
    if not isinstance(name, str) or not name or name.strip() != name:
        raise ValueError("explicit canonical instrument required")
    result = {
        "date": dt, "instrument": name,
        "source_row_present": source_row is not None,
        "saved_bar_present": saved_bar is not None,
        "classification": "unknown", "reason": None,
        "adjusted_open": None, "adjusted_close": None,
        "actual_suspension_or_delisting_verified": False,
        "retrospective_only": True,
    }
    if saved_bar is not None:
        if not isinstance(saved_bar, dict) or not {
            "trade_date", "instrument", "open_price", "close_price"
        } <= saved_bar.keys():
            result["reason"] = "incomplete_saved_bar_projection"
            return result
        if saved_bar["trade_date"] != dt or saved_bar["instrument"] != name:
            raise ValueError("saved bar lookup identity mismatch")
    if source_row is None:
        result.update(classification="source_absent" if saved_bar is None
                      else "implementation_mismatch",
                      reason="no_frozen_source_row" if saved_bar is None
                      else "saved_bar_without_frozen_source_row")
        return result
    required = {"trade_date", "instrument", "available_at", "close",
                "adjustment_factor", "amount", "open"}
    if not isinstance(source_row, dict) or not required <= source_row.keys():
        result["reason"] = "incomplete_source_projection"
        return result
    if source_row["trade_date"] != dt or source_row["instrument"] != name:
        raise ValueError("source row lookup identity mismatch")
    refusal = None
    try:
        visible = source_row["available_at"] is not None and timestamp(
            source_row["available_at"]) <= aware(clock(dt, "23:59:59"))
    except (ValueError, TypeError, OverflowError):
        result["reason"] = "unparseable_source_time_requires_pipeline_investigation"
        return result
    if not visible:
        refusal = "daily_not_available"
    elif any(source_row[k] is not None and type(source_row[k]) not in (int, float)
             for k in ("close", "adjustment_factor", "amount", "open")):
        result["reason"] = "nonnumeric_source_type_requires_pipeline_investigation"
        return result
    elif (not _valid(source_row["close"], True)
          or not _valid(source_row["adjustment_factor"], True)
          or not _valid(source_row["amount"])):
        refusal = "invalid_daily_history"
    else:
        factor = source_row["adjustment_factor"]
        adjusted = source_row["close"] * factor
        if not math.isfinite(adjusted) or not math.isfinite(source_row["amount"] * 1000):
            result["reason"] = "overflow_would_abort_panel_requires_investigation"
            return result
        if not _valid(source_row["open"], True) or not math.isfinite(source_row["open"] * factor):
            refusal = "invalid_bar_accounted_as_missing"
        else:
            result["adjusted_open"] = source_row["open"] * factor
            result["adjusted_close"] = adjusted
    if refusal:
        result.update(classification="format_time_refused" if saved_bar is None
                      else "implementation_mismatch", reason=refusal)
        return result
    if saved_bar is None:
        result.update(classification="implementation_mismatch",
                      reason="visible_valid_row_filtered_out_of_saved_execution_bars")
        return result
    try:
        close(saved_bar["open_price"], result["adjusted_open"])
        close(saved_bar["close_price"], result["adjusted_close"])
    except ValueError:
        result.update(classification="implementation_mismatch",
                      reason="saved_bar_adjusted_price_mismatch")
        return result
    result.update(classification="source_and_saved_bar_match",
                  reason="visible_source_adjusted_open_close_reconciled")
    return result


def explain_event_sources(chain_report, *, source_lookups, saved_bars):
    """Attach explicit source lookups to every event's full saved missing-bar chain.

    `source_lookups[(date,instrument)] = None` means a completed query found no row.
    An unqueried key is an error, never evidence of source absence. Source lookup
    and byte verification belong to the read-only runtime, not this pure helper.
    """
    events = []
    for event in chain_report["events"]:
        name, chain = event["instrument"], event["stale_chain"]
        dates = [chain["last_marked_date"]] + [r["date"] for r in chain["missing_sessions"]]
        if event["event_type"] == "recovery":
            dates.append(event["date"])
        rows = []
        for dt in dates:
            if (dt, name) not in source_lookups or dt not in saved_bars:
                raise ValueError("explicit completed source and history lookup required")
            rows.append(source_bar_evidence(
                dt, name, source_row=source_lookups[(dt, name)], saved_bar=saved_bars[dt].get(name)))
        categories = {r["classification"] for r in rows}
        status = ("IMPLEMENTATION_MISMATCH" if "implementation_mismatch" in categories else
                  "UNKNOWN" if "unknown" in categories else "EXPLAINED_BY_FROZEN_SOURCE")
        out = {**event, "source_rows": rows, "source_explanation_status": status,
               "actual_suspension_or_delisting_verified": False,
               "cash_receipt_inferred_from_recovery": False}
        if event["event_type"] == "recovery":
            out["source_recovery_cny"] = None
            out["source_recovery_status"] = rows[-1]["classification"]
            if rows[-1]["classification"] == "source_and_saved_bar_match":
                value = event["prior_shares"] * rows[-1]["adjusted_open"]
                close(value, event["saved_bar_recovery_cny"])
                out["source_recovery_cny"] = value
                out["source_recovery_status"] = "SOURCE_OPEN_TIMES_PRIOR_SHARES_RECONCILED"
        elif event["event_type"] == "writeoff":
            out["source_last_mark_writeoff_cny"] = None
            if rows[0]["classification"] == "source_and_saved_bar_match":
                value = event["prior_shares"] * rows[0]["adjusted_close"]
                close(value, event["amount_cny"])
                out["source_last_mark_writeoff_cny"] = value
        else:
            raise ValueError("unknown saved event type")
        events.append(out)
    tails = []
    for tail in chain_report.get("open_stale_chains", []):
        name, chain = tail["instrument"], tail["stale_chain"]
        dates = [chain["last_marked_date"]] + [r["date"] for r in chain["missing_sessions"]]
        rows = []
        for dt in dates:
            if (dt, name) not in source_lookups or dt not in saved_bars:
                raise ValueError("explicit completed tail source and history lookup required")
            rows.append(source_bar_evidence(
                dt, name, source_row=source_lookups[(dt, name)], saved_bar=saved_bars[dt].get(name)))
        categories = {r["classification"] for r in rows}
        status = ("IMPLEMENTATION_MISMATCH" if "implementation_mismatch" in categories else
                  "UNKNOWN" if "unknown" in categories else "EXPLAINED_BY_FROZEN_SOURCE")
        tails.append({**tail, "source_rows": rows, "source_explanation_status": status,
                      "actual_suspension_or_delisting_verified": False})
    statuses = {e["source_explanation_status"] for e in events + tails}
    return {**chain_report, "events": events, "open_stale_chains": tails,
            "source_explanation_status": (
                "IMPLEMENTATION_MISMATCH" if "IMPLEMENTATION_MISMATCH" in statuses else
                "UNKNOWN" if "UNKNOWN" in statuses else "EXPLAINED_BY_FROZEN_SOURCE"
                if events or tails else "NO_WRITEOFF_RECOVERY_EVENTS_OR_OPEN_STALE_CHAINS"),
            "source_truth_verified": False}
