from pathlib import Path

from stephen_quant.integrity.snapshot import build_snapshot_manifest


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
