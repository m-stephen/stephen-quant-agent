from pathlib import Path

from stephen_quant.integrity.snapshot import (
    build_composite_snapshot_manifest,
    build_file_snapshot_manifest,
    build_snapshot_manifest,
)


def test_snapshot_hash_is_deterministic(tmp_path: Path) -> None:
    (tmp_path / "a.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    first = build_snapshot_manifest(tmp_path)
    second = build_snapshot_manifest(tmp_path)
    assert first.snapshot_sha256 == second.snapshot_sha256


def test_snapshot_hash_changes_when_data_changes(tmp_path: Path) -> None:
    file = tmp_path / "a.csv"
    file.write_text("x,y\n1,2\n", encoding="utf-8")
    first = build_snapshot_manifest(tmp_path)
    file.write_text("x,y\n1,3\n", encoding="utf-8")
    second = build_snapshot_manifest(tmp_path)
    assert first.snapshot_sha256 != second.snapshot_sha256


def test_file_snapshot_ignores_unrelated_sibling_files(tmp_path: Path) -> None:
    source = tmp_path / "qmt.csv"
    sibling = tmp_path / "notes.txt"
    source.write_text("date,close\n2026-01-01,1\n", encoding="utf-8")
    sibling.write_text("first", encoding="utf-8")
    first = build_file_snapshot_manifest(source)
    sibling.write_text("second", encoding="utf-8")
    second = build_file_snapshot_manifest(source)

    assert first.snapshot_sha256 == second.snapshot_sha256
    assert [item.path for item in first.files] == ["qmt.csv"]


def test_composite_snapshot_freezes_all_named_source_manifests() -> None:
    first = build_composite_snapshot_manifest({"daily": "a" * 64, "fund_flow": "b" * 64})
    reordered = build_composite_snapshot_manifest(
        {"fund_flow": "b" * 64, "daily": "a" * 64}
    )
    changed = build_composite_snapshot_manifest({"daily": "a" * 64, "fund_flow": "c" * 64})
    assert first.snapshot_sha256 == reordered.snapshot_sha256
    assert first.snapshot_sha256 != changed.snapshot_sha256
    assert [item.path for item in first.files] == [
        "daily.manifest.sha256",
        "fund_flow.manifest.sha256",
    ]
