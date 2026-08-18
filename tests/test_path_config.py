from __future__ import annotations

import json
from pathlib import Path

import pytest

from stephen_quant.cli import build_parser
from stephen_quant.path_config import PathConfigError, load_local_path_config


def test_local_path_config_resolves_relative_paths_and_cli_override(tmp_path: Path) -> None:
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    config = config_dir / "qd-paths.local.json"
    config.write_text(
        json.dumps(
            {
                "version": 1,
                "paths": {
                    "qd_daily_dir": "../market/daily",
                    "csi300_csv": "../market/csi300.csv",
                    "dynamic_membership_jsonl": "../artifacts/membership.jsonl",
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = load_local_path_config(config)

    assert loaded.paths["qd_daily_dir"] == (tmp_path / "market" / "daily").resolve()
    assert loaded.choose("csi300_csv", None, "--benchmark-csv") == str(
        (tmp_path / "market" / "csi300.csv").resolve()
    )
    assert loaded.choose("qd_daily_dir", str(tmp_path / "override"), "--daily-dir") == str(
        (tmp_path / "override").resolve()
    )


def test_local_path_config_rejects_unknown_duplicate_and_missing_keys(tmp_path: Path) -> None:
    unknown = tmp_path / "unknown.json"
    unknown.write_text('{"version":1,"paths":{"secret":"x"}}', encoding="utf-8")
    with pytest.raises(PathConfigError, match="unknown"):
        load_local_path_config(unknown)

    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(
        '{"version":1,"paths":{"qd_daily_dir":"a","qd_daily_dir":"b"}}',
        encoding="utf-8",
    )
    with pytest.raises(PathConfigError, match="duplicate"):
        load_local_path_config(duplicate)

    empty = load_local_path_config(None)
    with pytest.raises(PathConfigError, match="--daily-dir"):
        empty.choose("qd_daily_dir", None, "--daily-dir")


def test_dynamic_backtest_cli_accepts_ignored_path_config_without_inline_paths() -> None:
    args = build_parser().parse_args(
        [
            "qd-dynamic-backtest",
            "--paths-config",
            "configs/qd-paths.local.json",
            "--data-start",
            "2021-07-01",
            "--research-start",
            "2022-01-04",
            "--research-end",
            "2024-12-31",
            "--validation-start",
            "2025-01-03",
            "--validation-end",
            "2025-12-31",
            "--test-start",
            "2026-01-05",
            "--test-end",
            "2026-08-14",
        ]
    )

    assert args.paths_config == "configs/qd-paths.local.json"
    assert args.daily_dir is None
    assert args.membership_jsonl is None
    assert args.benchmark_csv is None


def test_dynamic_cpcv_cli_accepts_ignored_path_config_without_inline_paths() -> None:
    args = build_parser().parse_args(
        [
            "qd-dynamic-cpcv",
            "--paths-config",
            "configs/qd-paths.local.json",
        ]
    )

    assert args.paths_config == "configs/qd-paths.local.json"
    assert args.daily_dir is None
    assert args.membership_jsonl is None
    assert args.candidate_manifest == "configs/v1.8.14-candidates.json"


def test_v48_portfolio_report_cli_uses_ignored_path_config() -> None:
    args = build_parser().parse_args(
        [
            "v4.8-portfolio-report",
            "--paths-config",
            "configs/qd-paths.local.json",
        ]
    )

    assert args.paths_config == "configs/qd-paths.local.json"
    assert args.output == "reports/v4.8-portfolio-report"
