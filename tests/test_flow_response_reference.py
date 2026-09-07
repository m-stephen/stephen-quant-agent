import copy
import math
from dataclasses import asdict

import pytest
from test_flow_response_history import frozen_sources
from test_flow_response_panel import daily_source

from stephen_quant.discovery.flow_response_reference import (
    FIELDS,
    opening_flags,
    reference_history,
    reference_ranks,
)
from stephen_quant.discovery.flow_response_series import bridge_rows, fit_response_bundle
from stephen_quant.discovery.flow_response_source_audit import compare, source_streams
from stephen_quant.qmt.flow_response_panel import build_response_panel


def sources():
    days, daily = daily_source()
    flow = [
        {
            "trade_date": r["trade_date"],
            "instrument": r["instrument"],
            "net_inflow_amount": 1e6 * math.sin(i * 0.317 + int(r["instrument"])),
            "available_at": r["trade_date"] + "T18:00:00+08:00",
        }
        for i, r in enumerate(daily)
    ]
    return daily, flow, days


@pytest.mark.parametrize(
    "kind",
    [
        "normal",
        "gap",
        "unavailable",
        "split",
        "zero_amount",
        "zero_volume",
        "flow_unavailable",
        "missing_flow",
        "st",
        "invalid_close",
    ],
)
def test_reference_full_dates_match_frozen_math_and_explicit_gap_rules(kind):
    daily, flow, days = sources()
    row, f = daily[100], flow[100]
    if kind == "gap":
        daily.remove(row)
        flow.remove(f)
    elif kind == "unavailable":
        row.update(available_at="2024-01-01T18:00:00+08:00", close="poison", amount="poison")
    elif kind == "split":
        for r in daily:
            if r["trade_date"] >= days[40]:
                r.update(open=r["open"] / 2, close=r["close"] / 2, adjustment_factor=2.0)
    elif kind == "zero_amount":
        row["amount"] = 0.0
    elif kind == "zero_volume":
        row["volume"] = 0.0
    elif kind == "flow_unavailable":
        f.update(available_at="2024-01-01T18:00:00+08:00", net_inflow_amount="poison")
    elif kind == "missing_flow":
        flow.remove(f)
    elif kind == "st":
        row["name"] = "*ST Synthetic"
    elif kind == "invalid_close":
        row["close"] = 0.0
    expected_risks, expected_bars, _ = build_response_panel(daily, days)
    observations, _ = bridge_rows(daily, flow, days)
    reference = dict(reference_history(daily, flow, days))
    for i, day in enumerate(days):
        compare(reference[day]["bars"], {n: asdict(b) for n, b in expected_bars[day].items()})
        for n, feature in reference[day]["features"].items():
            compare(
                {k: feature[k] for k in ("volatility_20", "ret_20", "liquidity")},
                expected_risks[day][n],
            )
        if 61 <= i < len(days) - 1:
            models = fit_response_bundle(observations, days, i, "a" * 64)["models"]
            assert set(models) == set(reference[day]["models"])
            for n, m in reference[day]["models"].items():
                compare(m, {k: models[n][k] for k in m})
    if kind in ("gap", "unavailable", "invalid_close"):
        assert reference[days[51]]["bars"]["600001"]["capacity_cny"] == 0
        assert "600001" not in reference[days[70]]["models"]


def test_independent_ranks_ties_and_empty_cells():
    features = {str(i): {k: float(i) for k in FIELDS} for i in range(80)}
    # Four names/cell. Explicit average-rank ties, not delegated ranking.
    for i in (0, 1):
        features[str(i)]["flow_ratio"] = 1.0
    ranked = reference_ranks(features)
    assert ranked["0"]["cell"] == ranked["3"]["cell"] == 0
    assert ranked["0"]["ranks"]["flow_ratio"] == pytest.approx(-0.4)
    assert ranked["1"]["ranks"]["flow_ratio"] == pytest.approx(-0.4)
    assert ranked["2"]["ranks"]["flow_ratio"] == pytest.approx(0.2)
    assert reference_ranks({}) == {}


@pytest.mark.parametrize("kind", ["duplicate", "orphan", "timezone", "calendar"])
def test_reference_rejects_source_integrity_failures(kind):
    daily, flow, days = sources()
    if kind == "duplicate":
        daily.insert(0, daily[0])
    elif kind == "orphan":
        flow[0]["instrument"] = "600000"
    elif kind == "timezone":
        daily[0]["available_at"] = days[0] + "T17:00:00"
    else:
        days = days[:-1]
    with pytest.raises(ValueError):
        list(reference_history(daily, flow, days))


def test_reference_support_ignores_orphan_values_and_preserves_past_features():
    daily, flow, days = sources()
    before = dict(reference_history(daily, flow, days))
    flow.append({"trade_date": days[40], "instrument": "orphan"})
    flow.sort(key=lambda r: (r["trade_date"], r["instrument"]))
    after = dict(
        reference_history(daily, flow, days, support_policy="same-date-daily-supported-v1")
    )
    assert "orphan" in after[days[40]]["source_keys"]["fund_flow"]
    for day in days:
        for k in ("models", "ranks", "features", "bars"):
            assert after[day][k] == before[day][k]


def test_future_append_cannot_change_past_reference_features_or_model():
    daily, flow, days = sources()
    before = dict(reference_history(daily, flow, days))
    poisoned = copy.deepcopy(daily)
    for row in poisoned:
        if row["trade_date"] > days[70]:
            row.update(open=777.0, close=888.0, amount=1e12)
    after = dict(reference_history(poisoned, flow, days))
    assert {d: before[d] for d in days[:71]} == {d: after[d] for d in days[:71]}


@pytest.mark.parametrize(
    "instrument,display,op,expected",
    [
        ("600001", "Example", 11.0, (False, True, "open_at_upper_limit")),
        ("600001", "Example", 9.0, (True, False, "open_at_lower_limit")),
        ("600001", "Example", 12.0, (False, False, "uncertain_price_limit_reference")),
        ("300001", "Example", 12.0, (False, True, "open_at_upper_limit")),
        ("600001", "*ST X", 10.5, (False, True, "open_at_upper_limit")),
        ("688001", "N New", 15.0, (True, True, "no_price_limit")),
        ("invalid", "Example", 10.0, (False, False, "unsupported_board")),
    ],
)
def test_reference_frozen_open_proxy(instrument, display, op, expected):
    assert opening_flags(instrument, display, op, 10.0) == expected


def test_independent_stream_reader_only_two_sources_and_exact_scope(tmp_path):
    days, manifest = frozen_sources(tmp_path / "inputs", span_days=70)
    with source_streams(tmp_path / "inputs", manifest_sha256=manifest) as (streams, hashes):
        assert set(streams) == set(hashes) == {"daily", "fund_flow"}
        assert len(list(streams["daily"])) == len(days) * 80
        assert len(list(streams["fund_flow"])) == len(days) * 80
    assert not (tmp_path / "inputs/auction.parquet").exists()


@pytest.mark.parametrize(
    "actual,expected",
    [({"a": 1}, {"a": 2}), ({}, {"a": 1}), (True, 1), (float("nan"), 1.0), ([1], [1, 2])],
)
def test_reference_comparison_cannot_certify_bad_numbers_or_structure(actual, expected):
    with pytest.raises(ValueError):
        compare(actual, expected)
