"""Synthetic source eligibility diagnostics, never real source ingestion."""

import pytest

from stephen_quant.discovery.account_forensics_source import source_bar_evidence

DT = "2023-01-04"


def inputs():
    return ({"trade_date": DT, "instrument": "S1", "available_at": DT + "T18:00:00+08:00",
             "close": 10., "open": 9., "amount": 100., "adjustment_factor": 2.},
            {"trade_date": DT, "instrument": "S1", "open_price": 18., "close_price": 20.})


def trace(source, bar):
    return source_bar_evidence(DT, "S1", source_row=source, saved_bar=bar)


def test_exact_price_reconciliation_not_tradability_test():
    source, bar = inputs()
    source.update(volume=0, name=None, amount=0)
    result = trace(source, bar)
    assert result["classification"] == "source_and_saved_bar_match"
    assert result["adjusted_open"] == 18
    assert result["retrospective_only"]
    assert not result["actual_suspension_or_delisting_verified"]


def test_absence_is_not_delisting():
    result = trace(None, None)
    assert result["classification"] == "source_absent"
    assert not result["actual_suspension_or_delisting_verified"]


@pytest.mark.parametrize("field,value,reason", [
    ("available_at", None, "daily_not_available"),
    ("available_at", "2023-01-05T00:00:00+08:00", "daily_not_available"),
    ("close", 0, "invalid_daily_history"),
    ("adjustment_factor", float("nan"), "invalid_daily_history"),
    ("amount", -1, "invalid_daily_history"),
    ("open", None, "invalid_bar_accounted_as_missing"),
])
def test_refusal_or_contradictory_saved_bar(field, value, reason):
    source, bar = inputs()
    source[field] = value
    result = trace(source, None)
    assert result["classification"] == "format_time_refused"
    assert result["reason"] == reason
    assert trace(source, bar)["classification"] == "implementation_mismatch"


def test_mismatches_are_not_silently_corrected():
    source, bar = inputs()
    assert trace(source, None)["classification"] == "implementation_mismatch"
    assert trace(None, bar)["classification"] == "implementation_mismatch"
    bar["open_price"] = 9
    assert trace(source, bar)["classification"] == "implementation_mismatch"
    assert bar["open_price"] == 9


def test_unknown_incomplete_or_unparseable_evidence():
    source, bar = inputs()
    assert trace({}, None)["classification"] == "unknown"
    assert trace(source, {})["classification"] == "unknown"
    source["available_at"] = "not-a-time"
    assert trace(source, bar)["classification"] == "unknown"


@pytest.mark.parametrize("field", ["close", "open", "adjustment_factor", "amount"])
def test_nonnumeric_types_do_not_claim_normal_pipeline_filtering(field):
    source, bar = inputs()
    source[field] = "10"
    for saved in (bar, None):
        result = trace(source, saved)
        assert result["classification"] == "unknown"
        assert result["reason"] == "nonnumeric_source_type_requires_pipeline_investigation"


def test_source_absence_does_not_bypass_saved_bar_validation():
    assert trace(None, {})["classification"] == "unknown"
    _, bar = inputs()
    bar["instrument"] = "S2"
    with pytest.raises(ValueError, match="saved bar lookup identity"):
        trace(None, bar)


def test_lookup_identity_and_future_year_refused():
    source, bar = inputs()
    source["instrument"] = "S2"
    with pytest.raises(ValueError, match="identity"):
        trace(source, bar)
    with pytest.raises(ValueError):
        source_bar_evidence("2025-01-02", "S1", source_row=None, saved_bar=None)
