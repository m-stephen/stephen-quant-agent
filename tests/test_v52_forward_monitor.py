from __future__ import annotations

from pathlib import Path

import pytest

from stephen_quant.workflows.v52_forward_monitor import (
    FROZEN_LINES,
    V52ForwardConfig,
    run_v52_forward_monitor,
)


def _files(root: Path, days: range) -> None:
    root.mkdir()
    for day in days:
        (root / f"202609{day:02d}.csv").write_text("fixture\n", encoding="utf-8")


def test_v52_waits_without_creating_performance_trials(tmp_path: Path) -> None:
    roots = tuple(tmp_path / name for name in ("daily", "flow", "chip"))
    for root in roots:
        _files(root, range(1, 11))
    report = run_v52_forward_monitor(
        *roots,
        membership_path=None,
        output_dir=tmp_path / "output",
        as_of="2026-09-30",
    )
    assert report.decision == "WAITING_FOR_DATA"
    assert report.common_new_sessions == 10
    assert report.performance_trials == 0
    assert report.frozen_lines == FROZEN_LINES


def test_v52_requires_forward_membership_after_25_sessions(tmp_path: Path) -> None:
    roots = tuple(tmp_path / name for name in ("daily", "flow", "chip"))
    for root in roots:
        _files(root, range(1, 26))
    report = run_v52_forward_monitor(
        *roots,
        membership_path=None,
        output_dir=tmp_path / "output",
        as_of="2026-09-30",
    )
    assert report.decision == "BLOCKED_BY_MEMBERSHIP"
    assert not report.membership_ready


def test_v52_rejects_lower_forward_checkpoint() -> None:
    with pytest.raises(ValueError, match="checkpoints"):
        V52ForwardConfig(early_sessions=20).validate()
