from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from stephen_quant.qmt.asset_inventory import inventory_assets
from stephen_quant.qmt.models import QmtDataError


def test_inventory_classifies_archive_extracted_source_and_unknown(tmp_path: Path) -> None:
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    extracted = source / "daily.csv"
    extracted.write_bytes("日期,代码\n20260101,000001\n".encode("gb18030"))
    with zipfile.ZipFile(source / "daily.zip", "w") as archive:
        archive.writestr("nested/daily.csv", extracted.read_bytes())
    (source / "standalone.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (source / "opaque.bin").write_bytes(b"opaque")
    before = {path.name: path.read_bytes() for path in source.iterdir()}

    first = inventory_assets(source, output)
    payload = json.loads(Path(first["manifest_path"]).read_text(encoding="utf-8"))
    statuses = {item["relative_path"]: item["status"] for item in payload["entries"]}

    assert statuses == {
        "daily.csv": "extracted_from_archive",
        "daily.zip": "raw_archive",
        "opaque.bin": "unknown_review",
        "standalone.csv": "source_uncompressed",
    }
    assert before == {path.name: path.read_bytes() for path in source.iterdir()}

    second = inventory_assets(source, output)
    assert second["snapshot_sha256"] == first["snapshot_sha256"]
    assert second["hash_cache_reused"] == 4


def test_inventory_rejects_output_inside_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    with pytest.raises(QmtDataError, match="outside"):
        inventory_assets(source, source / "output")
