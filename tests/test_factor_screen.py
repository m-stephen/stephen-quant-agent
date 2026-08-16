from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from stephen_quant.factors import build_seed_registry
from stephen_quant.qmt import (
    QmtDailyBar,
    screen_factor_redundancy,
    write_factor_redundancy_screen,
)


def _bars() -> tuple[QmtDailyBar, ...]:
    start = date(2023, 1, 2)
    growth = {"A": 1.003, "B": 1.002, "C": 1.001}
    bars: list[QmtDailyBar] = []
    for index in range(30):
        day = (start + timedelta(days=index)).isoformat()
        for instrument, rate in growth.items():
            value = 100 * rate**index
            bars.append(
                QmtDailyBar(
                    instrument=instrument,
                    trade_date=day,
                    open=value,
                    high=value * 1.01,
                    low=value * 0.99,
                    close=value,
                    volume=1_000_000,
                    amount=100_000_000,
                )
            )
    return tuple(bars)


def test_factor_redundancy_screen_finds_rank_equivalent_signals(tmp_path: Path) -> None:
    registry = build_seed_registry()
    screen = screen_factor_redundancy(
        _bars(),
        (registry.get("ret_5"), registry.get("ret_20")),
        source_snapshot_sha256="source-sha",
        screen_start="2023-01-23",
        screen_end="2023-01-29",
        high_correlation_threshold=0.8,
    )
    artifacts = write_factor_redundancy_screen(screen, tmp_path)

    assert len(screen.pairs) == 1
    assert screen.pairs[0].mean_rank_correlation == pytest.approx(-1.0)
    assert screen.high_correlation_pairs == screen.pairs
    assert artifacts.json_path.exists()
    assert artifacts.markdown_path.exists()
