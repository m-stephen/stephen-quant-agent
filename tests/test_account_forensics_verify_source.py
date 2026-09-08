"""Independent source reference must retain absence, mismatch and unknown distinctions."""

from datetime import datetime

import pytest
from test_account_forensics_source import DT, inputs, trace

from stephen_quant.discovery.account_forensics_verify_source import (
    reference_source_row,
    verify_source_row,
)
from stephen_quant.qmt.flow_response_panel import build_response_panel


@pytest.mark.parametrize("bar_present", [False, True])
@pytest.mark.parametrize("field,value", [
    ("open", 9.), ("open", None), ("open", -1), ("open", float("inf")),
    ("open", "9"), ("close", True), ("close", 0), ("close", float("nan")),
    ("close", 1e308), ("adjustment_factor", 0), ("amount", -1), ("amount", 1e308),
    ("available_at", None), ("available_at", "bad"),
    ("available_at", "2023-01-04T12:00:00"),
    ("available_at", "2023-01-04T23:59:59+08:00"),
    ("available_at", "2023-01-05T00:00:00+08:00"),
    ("available_at", datetime.fromisoformat("2023-01-04T15:59:59+00:00")),
])
def test_reference_source_contract(field, value, bar_present):
    source, bar = inputs()
    source[field] = value
    bar = bar if bar_present else None
    result = trace(source, bar)
    assert verify_source_row(DT, "S1", source, bar, result)["source_row_interpretation_verified"]


@pytest.mark.parametrize("source,bar", [(None, None), ({}, None), (None, {}), ({}, {}),
                                       (None, inputs()[1]), (inputs()[0], {})])
def test_absence_and_incomplete_shapes(source, bar):
    result = trace(source, bar)
    verify_source_row(DT, "S1", source, bar, result)


@pytest.mark.parametrize("key,value", [
    ("classification", "source_absent"), ("reason", "source_verified"),
    ("adjusted_open", 9), ("adjusted_close", 10),
    ("actual_suspension_or_delisting_verified", True), ("retrospective_only", False),
    ("source_row_present", False),
])
def test_changed_source_interpretation_rejected(key, value):
    source, bar = inputs()
    result = trace(source, bar)
    result[key] = value
    with pytest.raises(ValueError):
        verify_source_row(DT, "S1", source, bar, result)


def test_saved_price_mismatch_is_not_fixed():
    source, bar = inputs()
    bar["open_price"] = 9
    result = reference_source_row(DT, "S1", source, bar)
    assert result["classification"] == "implementation_mismatch"
    assert bar["open_price"] == 9
    verify_source_row(DT, "S1", source, bar, trace(source, bar))


@pytest.mark.parametrize("where", ["source", "bar", "future"])
def test_wrong_identity_or_future_refused(where):
    source, bar = inputs()
    if where == "source":
        source["instrument"] = "OTHER"
    elif where == "bar":
        bar["instrument"] = "OTHER"
    with pytest.raises(ValueError):
        reference_source_row("2025-01-01" if where == "future" else DT, "S1", source, bar)


@pytest.mark.parametrize("field,value", [("volume", "100"), ("volume", True),
                                        ("name", 123), ("name", [])])
def test_bad_tradability_types_are_unknown(field, value):
    source, bar = inputs()
    source.update(volume=100., name="Example")
    source[field] = value
    result = trace(source, bar)
    assert result["classification"] == "unknown"
    verify_source_row(DT, "S1", source, bar, result)


def test_native_panel_rejects_string_volume_not_a_matched_bar():
    source, bar = inputs()
    source.update(volume="100", name="Example")
    with pytest.raises(TypeError):
        build_response_panel([source], [DT])
    assert trace(source, bar)["classification"] == "unknown"
    assert reference_source_row(DT, "S1", source, bar)["classification"] == "unknown"


@pytest.mark.parametrize("volume,name", [(0, "Example"), (None, "Example"),
                                         (float("nan"), "Example"), (100., None), (100., "")])
def test_native_untradable_metadata_still_has_saved_bar(volume, name):
    source, bar = inputs()
    source.update(volume=volume, name=name)
    _, native_bars, _ = build_response_panel([source], [DT])
    assert native_bars[DT]["S1"].open_price == bar["open_price"]
    assert not native_bars[DT]["S1"].can_buy_open
    assert trace(source, bar)["classification"] == "source_and_saved_bar_match"
    verify_source_row(DT, "S1", source, bar, trace(source, bar))
