from __future__ import annotations

import csv
from pathlib import Path

import pytest

from stephen_quant.qmt.industry_proxy_audit import (
    audit_industry_proxy,
    build_industry_proxy_manifest,
    write_industry_proxy_audit,
)
from stephen_quant.qmt.models import QmtDataError

HEADER = ("日期", "代码", "行业", "开盘价")


def _write(path: Path, rows: list[tuple[str, str, str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        writer.writerows(rows)


def _fixture(root: Path, *, change: bool = True) -> None:
    for year in (2022, 2023, 2024):
        for session in range(1, 21):
            day = f"{year}01{session:02d}"
            rows = []
            for index in range(12):
                label = f"行业{index}"
                if change and year == 2024 and index < 5:
                    label = f"新行业{index}"
                rows.append((day, f"{index:06d}.SZ", label, "10"))
            _write(root / f"{day}.csv", rows)


def test_audit_grants_only_provisional_proxy_use(tmp_path: Path) -> None:
    _fixture(tmp_path)
    manifest = build_industry_proxy_manifest(tmp_path)
    audit = audit_industry_proxy(tmp_path, manifest)
    assert audit.classification == "A_PROXY_PIT_CANDIDATE"
    assert audit.research_usage == "PROVISIONAL_PROXY_INDUSTRY"
    assert audit.inferential_trial_delta == 0
    assert audit.changed_securities == 5


def test_static_labels_are_diagnostics_only(tmp_path: Path) -> None:
    _fixture(tmp_path, change=False)
    audit = audit_industry_proxy(tmp_path, build_industry_proxy_manifest(tmp_path))
    assert audit.classification == "B_CURRENT_LABEL_BACKFILL"
    assert audit.research_usage == "DIAGNOSTICS_ONLY"


def test_manifest_rejects_mutation_and_future_partition(tmp_path: Path) -> None:
    _fixture(tmp_path)
    _write(tmp_path / "20250102.csv", [("20250102", "000001.SZ", "银行", "10")])
    manifest = build_industry_proxy_manifest(tmp_path)
    assert all(not item.path.startswith("2025") for item in manifest.files)
    (tmp_path / manifest.files[0].path).write_text("changed", encoding="utf-8")
    with pytest.raises(QmtDataError, match="changed"):
        audit_industry_proxy(tmp_path, manifest)


def test_conflicting_same_day_label_is_unusable(tmp_path: Path) -> None:
    _fixture(tmp_path)
    target = tmp_path / "20220101.csv"
    with target.open("a", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerow(("20220101", "000000.SZ", "冲突行业", "10"))
    audit = audit_industry_proxy(tmp_path, build_industry_proxy_manifest(tmp_path))
    assert audit.classification == "C_UNUSABLE"
    assert audit.conflicting_keys == 1


def test_artifacts_are_bilingual_and_replay_deterministic(tmp_path: Path) -> None:
    root = tmp_path / "source"
    _fixture(root)
    first, artifacts = write_industry_proxy_audit(root, tmp_path / "first")
    second, _ = write_industry_proxy_audit(root, tmp_path / "second")
    assert first.result_sha256 == second.result_sha256
    assert "不替代 Issue #92" in artifacts.markdown_zh_path.read_text(encoding="utf-8")
    assert "does not replace" in artifacts.markdown_en_path.read_text(encoding="utf-8")
