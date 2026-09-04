from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from stephen_quant.cli import build_parser
from stephen_quant.workflows import v10_empirical
from stephen_quant.workflows import v111_mechanism_discovery as v111


def _feature_rows(days: int = 6, stocks: int = 80) -> tuple[dict[str, object], ...]:
    rows = []
    for day in range(days):
        for index in range(stocks):
            rows.append(
                {
                    "signal_date": f"2024-01-{day + 1:02d}",
                    "execution_date": f"2024-01-{day + 2:02d}",
                    "exit_date": None,
                    "instrument": f"{index:06d}.SZ",
                    "amount_rank_20": index / stocks,
                    "volatility_20": ((index * 7 + day) % stocks) / stocks + 0.01,
                    "concentration": 0.2 + index / 1000,
                    "concentration_change": math.sin(index / 7 + day) / 20,
                    "profit_ratio_change": math.cos(index / 11 - day) / 20,
                    "closing_volume_share": ((index * 13 + day) % stocks) / stocks,
                    "vwap_deviation": math.sin(index / 9) / 100,
                    "main_inflow_ratio": math.cos(index / 8) / 100,
                    "main_inflow_ratio_persistence": math.cos(index / 10 + day) / 100,
                    "net_inflow_ratio_persistence": math.sin(index / 10 + day) / 100,
                    "net_inflow_ratio_change": math.sin(index / 12 - day) / 100,
                    "ret_20": math.cos(index / 13) / 10,
                    "auction_return": math.sin(index / 6) / 100,
                    "late_30_return": math.cos(index / 5) / 100,
                    "intraday_return": math.sin(index / 4) / 100,
                    "realized_volatility": 0.01 + ((index * 17) % stocks) / 1000,
                    "prior_adv": 100_000_000 + index * 1_000_000,
                    "industry_code": f"I{index % 8}",
                    "forward_return": None,
                }
            )
    return tuple(rows)


def test_v111_catalog_is_exactly_three_families_of_five() -> None:
    candidates = v111.frozen_v111_candidates()
    assert len(candidates) == 15
    assert len({item.candidate_id for item in candidates}) == 15
    assert {item.primary_horizon for item in candidates} == {5, 10, 20}
    mechanisms = {item.mechanism for item in candidates}
    assert mechanisms == {
        "auction_close_absorption",
        "chip_state_transition",
        "flow_price_mismatch",
    }
    for mechanism in mechanisms:
        family = [item for item in candidates if item.mechanism == mechanism]
        assert len(family) == 5
        assert sum(item.negative_control for item in family) == 1


def test_v111_cli_is_explicit_and_fixed_budget() -> None:
    args = build_parser().parse_args(
        [
            "v11.1-mechanism-discovery",
            "--warehouse-root",
            "warehouse",
            "--feature-snapshot",
            "a" * 64,
        ]
    )
    assert args.command == "v11.1-mechanism-discovery"
    assert not hasattr(args, "candidate_budget")


def test_v111_label_free_screen_uses_no_return_and_checks_capacity() -> None:
    candidate = v111.frozen_v111_candidates()[0]
    screen = v111.label_free_screen(_feature_rows(), candidate)
    assert screen.passed
    assert screen.coverage_ratio == 1.0
    assert screen.variable_date_ratio == 1.0
    assert screen.estimated_capacity_cny >= 3_000_000
    assert len(screen.score_fingerprint) == 64


def test_v111_risk_cleaning_removes_size_and_volatility_linear_exposure() -> None:
    candidate = v111.frozen_v111_candidates()[0]
    rows = list(_feature_rows(days=1))
    scores = v111._raw_scores(rows, candidate)
    assert len(scores) == 80
    y = [scores[str(row["instrument"])] for row in rows]
    size = [float(row["amount_rank_20"]) for row in rows]
    vol = v10_empirical._rank([float(row["volatility_20"]) for row in rows])
    assert abs(sum((a - sum(size) / len(size)) * b for a, b in zip(size, y, strict=True))) < 1e-8
    assert abs(sum((a - sum(vol) / len(vol)) * b for a, b in zip(vol, y, strict=True))) < 1e-8


def test_v111_feature_only_panel_does_not_query_future_prices(monkeypatch: pytest.MonkeyPatch) -> None:
    queries: list[str] = []

    class Cursor:
        description = (("signal_date",),)

        def fetchall(self):
            return []

    class Connection:
        def execute(self, query, parameters):
            queries.append(query)
            return Cursor()

        def close(self):
            return None

    monkeypatch.setattr(
        v10_empirical,
        "_duckdb",
        lambda: SimpleNamespace(connect=lambda *_args, **_kwargs: Connection()),
    )
    assert v10_empirical._panel(
        Path("warehouse"), "2022-01-01", "2024-12-31", include_labels=False
    ) == ()
    assert "lead(open*adjustment_factor" not in queries[0]
    assert "CAST(NULL AS DOUBLE) forward_return" in queries[0]


def test_v111_prefilter_failure_consumes_no_trial_or_label(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    label_modes: list[bool] = []

    def fake_panel(*_args, **kwargs):
        label_modes.append(kwargs["include_labels"])
        return (), "a" * 64

    monkeypatch.setattr(v111, "_cross_source_panel", fake_panel)
    monkeypatch.setattr(v111, "_attach_industry", lambda _root, rows: rows)
    report = v111.run_v111_mechanism_epoch(
        tmp_path / "warehouse",
        feature_snapshot_id="b" * 64,
        registry=SimpleNamespace(),
        output_dir=tmp_path / "result",
        code_version="c" * 40,
    )
    assert report.decision == "LABEL_FREE_PREFILTER_NOT_READY"
    assert report.inferential_trials_added == 0
    assert report.unauthorized_sealed_label_reads == 0
    assert label_modes == [False, False, False]
    assert (tmp_path / "result" / "V11_1_MECHANISM_RESULT.json").exists()
