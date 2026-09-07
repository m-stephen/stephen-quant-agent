import numpy as np
import pytest

from stephen_quant.discovery.flow_response_synthetic import (
    generator_contract,
    simulate,
    synthetic_calendar,
    write_synthetic_sources,
)
from stephen_quant.qmt.flow_response_inputs import load_response_sources


def test_causal_generator_prefix_is_unchanged_by_later_extension():
    dates = synthetic_calendar()
    short = simulate(dates[:80], case="planted", stocks=80)
    long = simulate(dates[:100], case="planted", stocks=80)
    for k in short:
        np.testing.assert_array_equal(short[k], long[k][:80])
    np.testing.assert_array_equal(long["open"][1:], long["close"][:-1])


def test_paired_null_uses_same_exogenous_flow_but_no_predictable_carry():
    dates = synthetic_calendar()[:100]
    planted, null = [simulate(dates, case=c, stocks=80) for c in ("planted", "null")]
    np.testing.assert_array_equal(planted["flow_ratio"], null["flow_ratio"])
    np.testing.assert_array_equal(planted["close"][:61], null["close"][:61])
    assert np.count_nonzero(null["oracle_carry"]) == 0
    assert np.any(planted["oracle_carry"][61:] != 0)
    assert np.max(np.abs(planted["oracle_signal"])) <= 1
    assert generator_contract()["case_strength"] == {"planted": 0.06, "null": 0.0}


def test_raw_source_files_have_no_oracle_and_roundtrip_through_frozen_reader(tmp_path):
    root = tmp_path / "synthetic"
    days, sha, oracle = write_synthetic_sources(
        root, case="null", calendar=synthetic_calendar()[:80], stocks=80
    )
    rows, evidence = load_response_sources(root, expected_manifest_sha256=sha, calendar=days)
    daily, flow = rows["daily"], rows["fund_flow"]
    assert len(daily) == len(flow) == 6400
    assert all(not any(k.startswith("oracle") for k in row) for row in daily + flow)
    assert set(oracle) == {"oracle_signal", "oracle_carry"}
    assert evidence["parent_snapshot_sha256"] == sha
    assert not any((root / f"{s}.parquet").exists() for s in ("auction", "chip", "minute"))
    with pytest.raises(FileExistsError):
        write_synthetic_sources(root, case="null", calendar=days, stocks=80)


@pytest.mark.parametrize("kind", ["case", "stock", "calendar"])
def test_synthetic_contract_rejects_unbounded_or_unknown_request(kind):
    with pytest.raises(ValueError):
        simulate(
            synthetic_calendar()[:80] if kind != "calendar" else ["2025-01-01"] * 80,
            case="null" if kind != "case" else "search",
            stocks=10000 if kind == "stock" else 80,
        )
