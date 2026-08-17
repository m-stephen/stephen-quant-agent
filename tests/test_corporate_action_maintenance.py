from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import pytest

from stephen_quant.qmt.corporate_action_maintenance import (
    merge_corporate_action_operations,
)
from stephen_quant.qmt.models import QmtDataError
from stephen_quant.qmt.pit_staging import CorporateActionPIT


def _operation(tmp_path: Path, name: str, *, quarantine: int = 0) -> Path:
    root = tmp_path / name
    root.mkdir()
    row = CorporateActionPIT(
        code="000001.SZ", event_type="distribution",
        announcement_at="2023-05-01T18:00:00+08:00",
        available_at="2023-05-01T18:00:00+08:00", effective_date="2023-06-01",
        record_date="2023-05-30", ex_date="2023-06-01", revision_id=name,
        source_document_id=name, source_hash=hashlib.sha256(name.encode()).hexdigest(),
        cash_dividend_per_share="0.1", parser_version="test",
    )
    bundle = (json.dumps([asdict(row)], sort_keys=True, separators=(",", ":")) + "\n").encode()
    (root / "corporate-actions.json").write_bytes(bundle)
    manifest = {
        "operation_id": name, "accepted_rows": 1, "quarantined_records": quarantine,
        "quarantined_identity_hashes": ["a" * 64] if quarantine else [],
        "formal_research_eligible": False, "inferential_trial_delta": 0,
        "files": [{"path": "corporate-actions.json", "size": len(bundle),
                   "sha256": hashlib.sha256(bundle).hexdigest()}],
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _config(tmp_path: Path, operations: list[tuple[str, Path]], operation_id: str) -> Path:
    path = tmp_path / f"{operation_id}.local.json"
    path.write_text(json.dumps({
        "operation_id": operation_id, "output_dir": str(tmp_path / "output"),
        "expected_partitions": [name for name, _ in operations],
        "operations": [{"partition": name, "operation_dir": str(root)}
                       for name, root in operations],
    }), encoding="utf-8")
    return path


def test_merge_verifies_files_and_replays(tmp_path: Path) -> None:
    operations = [("2023-05", _operation(tmp_path, "first")),
                  ("2023-06", _operation(tmp_path, "second"))]
    first = merge_corporate_action_operations(_config(tmp_path, operations, "merge-1"))
    second = merge_corporate_action_operations(_config(tmp_path, operations, "merge-2"))
    assert first.rows == 2
    assert first.bundle_sha256 == second.bundle_sha256


def test_merge_rejects_quarantine_and_file_tampering(tmp_path: Path) -> None:
    bad = _operation(tmp_path, "bad", quarantine=1)
    with pytest.raises(QmtDataError, match="quarantined"):
        merge_corporate_action_operations(_config(tmp_path, [("2023-05", bad)], "merge-bad"))
    good = _operation(tmp_path, "good")
    (good / "corporate-actions.json").write_text("tampered")
    with pytest.raises(QmtDataError, match="evidence mismatch"):
        merge_corporate_action_operations(_config(tmp_path, [("2023-05", good)], "merge-tamper"))
