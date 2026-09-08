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
