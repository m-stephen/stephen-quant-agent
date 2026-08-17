from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def _response(page: int, code: str) -> dict[str, object]:
    item = {
        "announcementId": f"transient-{page}",
        "title": f"Example annual report {page}",
        "publishTime": "2025-04-30 18:00:00",
        "actualPublishTime": "2025-04-30 18:00:00",
        "endDate": "2024-12-31 00:00:00",
        "announcementType": "年度报告",
        "announcementTypeCode": "annual",
        "market": "A",
        "stockTag": [{"code": code, "name": "Example"}],
        "industryTag": [],
        "hasPdf": True,
    }
    return {
        "code": 200000,
        "data": {
            "pageNum": page, "pageSize": 1, "totalPageNum": 2,
            "totalSize": 2, "data": [item],
        },
    }


def _run(config: Path) -> subprocess.CompletedProcess[str]:
    root = Path(__file__).parents[1]
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(root / "src")
    return subprocess.run(
        [sys.executable, str(root / "scripts" / "build_alphapai_pit_bundle.py"),
         "--config", str(config)],
        cwd=root, env=environment, text=True, capture_output=True, check=False,
    )


def test_builder_binds_envelope_pages_and_rejects_overwrite_and_source_output(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    second = source / "second.json"
    first = source / "first.json"
    second.write_text(json.dumps(_response(2, "000002.SZ")), encoding="utf-8")
    first.write_text(json.dumps(_response(1, "000001.SZ")), encoding="utf-8")
    output = tmp_path / "output"
    config = tmp_path / "build.local.json"
    payload = {
        "operation_id": "operation-1", "output_dir": str(output),
        "query_start": "2025-01-01", "query_end": "2025-12-31",
        "ingested_at": "2026-08-17T22:00:00+08:00",
        "partitions": [{"name": "2025", "pages": [str(second), str(first)]}],
    }
    config.write_text(json.dumps(payload), encoding="utf-8")
    assert _run(config).returncode == 0
    manifest = json.loads(
        (output / "operation-1" / "source-page-manifest.json").read_text(encoding="utf-8")
    )
    assert [row["page"] for row in manifest["files"]] == [1, 2]
    hashes = {row["page"]: row["sha256"] for row in manifest["files"]}
    assert hashes[1] == hashlib.sha256(first.read_bytes()).hexdigest()
    assert hashes[2] == hashlib.sha256(second.read_bytes()).hexdigest()
    assert all(row["total_pages"] == 2 and row["total_size"] == 2
               for row in manifest["files"])
    assert _run(config).returncode != 0
    payload["operation_id"] = "operation-2"
    payload["output_dir"] = str(source / "generated")
    config.write_text(json.dumps(payload), encoding="utf-8")
    result = _run(config)
    assert result.returncode != 0
    assert "physically disjoint" in result.stderr
