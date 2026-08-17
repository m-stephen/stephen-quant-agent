from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from stephen_quant.cli import build_parser
from stephen_quant.workflows import (
    V22BreadthScore,
    cumulative_v22_trial_count,
    load_v22_portfolio_breadth_config,
    select_v22_breadth,
    verify_v22_portfolio_breadth_replay,
)


def _score(top_k: int, raw_sharpe: float) -> V22BreadthScore:
    return V22BreadthScore(
        top_k=top_k,
        trial_id=f"trial_{top_k}",
        local_trial_number=(5, 10, 15, 20).index(top_k) + 1,
        cumulative_trial_number=38 + (5, 10, 15, 20).index(top_k),
        periods=35,
        raw_net_sharpe=raw_sharpe,
        annualized_net_sharpe=raw_sharpe * 3.5,
        net_total_return=raw_sharpe,
        max_drawdown=-0.20,
        total_turnover=1.0,
        total_cost=100.0,
        capacity_clipped_notional=0.0,
    )


def test_v22_manifest_carries_frozen_v21_evidence_and_trial_count() -> None:
    config = load_v22_portfolio_breadth_config("configs/v2.2-portfolio-breadth.json")

    assert config.prior_trial_count == 37
    assert config.top_ks == (5, 10, 15, 20)
    assert config.prior_evidence_sha256 == config.calculated_evidence_sha256
    assert cumulative_v22_trial_count(config, 5) == 42
    with pytest.raises(ValueError, match="four breadth trials"):
        cumulative_v22_trial_count(config, 4)


def test_v22_manifest_rejects_tampered_prior_evidence(tmp_path: Path) -> None:
    payload = json.loads(
        Path("configs/v2.2-portfolio-breadth.json").read_text(encoding="utf-8")
    )
    payload["prior_trial_count"] = 36
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="complete V2.1 evidence|evidence hash"):
        load_v22_portfolio_breadth_config(path)


def test_v22_selection_is_deterministic_and_prefers_smaller_tie() -> None:
    scores = (
        _score(5, 0.1),
        _score(10, 0.2),
        _score(15, 0.2),
        _score(20, 0.15),
    )

    assert select_v22_breadth(scores).top_k == 10
    with pytest.raises(ValueError, match="exactly one frozen"):
        select_v22_breadth(scores[:-1])


def test_v22_replay_is_offline_and_fails_on_tamper(tmp_path: Path) -> None:
    artifacts = {
        "json": tmp_path / "v2.2-portfolio-breadth.json",
        "markdown_en": tmp_path / "v2.2-portfolio-breadth.en.md",
        "markdown_zh": tmp_path / "v2.2-portfolio-breadth.zh.md",
    }
    for name, path in artifacts.items():
        path.write_text(name, encoding="utf-8")
    hashes = {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in artifacts.items()
    }
    manifest = tmp_path / "v2.2-replay-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "replay_version": "v2.2-portfolio-breadth-replay-1.0.0",
                "method_version": "v2.2-frozen-signal-portfolio-breadth-1.0.0",
                "source_snapshot_sha256": "a" * 64,
                "prior_evidence_sha256": "b" * 64,
                "cumulative_trial_count": 42,
                "validation_window_opened": False,
                "test_window_opened": False,
                "artifacts": hashes,
            }
        ),
        encoding="utf-8",
    )

    assert verify_v22_portfolio_breadth_replay(manifest).passed
    artifacts["json"].write_text("tampered", encoding="utf-8")
    verification = verify_v22_portfolio_breadth_replay(manifest)
    assert verification.passed is False
    assert verification.mismatches == ("json",)


def test_v22_cli_replay_and_kill_need_no_local_paths() -> None:
    parser = build_parser()
    replay = parser.parse_args(
        [
            "v2-portfolio-breadth",
            "--mode",
            "replay",
            "--replay-manifest",
            "frozen.json",
        ]
    )
    kill = parser.parse_args(["v2-portfolio-breadth", "--mode", "kill"])

    assert replay.paths_config is None
    assert kill.paths_config is None
