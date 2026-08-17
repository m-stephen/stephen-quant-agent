from __future__ import annotations

import json
from pathlib import Path

import pytest

from stephen_quant.qmt.models import QmtDataError
from stephen_quant.qmt.source_completion import (
    build_source_completion_report,
    write_source_completion_report,
)

STATES = {
    2022: "RESEARCH_ALLOWED_2022_2024", 2023: "RESEARCH_ALLOWED_2022_2024",
    2024: "RESEARCH_ALLOWED_2022_2024",
    2025: "CONSUMED_2025_DATA_MAINTENANCE_ONLY",
    2026: "SEALED_2026_DATA_MAINTENANCE_ONLY",
}


def _config(tmp_path: Path, *, quarantine: int = 0, industry: int = 1,
            corporate: int = 1) -> Path:
    entries = []
    for year, state in STATES.items():
        path = tmp_path / f"alpha-{year}.json"
        identities = [f"{index:064x}" for index in range(quarantine)] if year == 2023 else []
        path.write_text(json.dumps({
            "formal_research_eligible": False, "inferential_trial_delta": 0,
            "quarantined_source_records": len(identities),
            "quarantined_transient_id_hashes": identities,
        }))
        entries.append({"year": year, "state": state, "path": str(path)})
    authoritative = tmp_path / "authoritative.json"
    authoritative.write_text(json.dumps({
        "formal_research_eligible": False, "inferential_trial_delta": 0,
        "industry_rows": industry, "corporate_action_rows": corporate,
        "files": [{"role": "source_document", "sha256": "a" * 64}],
    }))
    config = tmp_path / "completion.local.json"
    config.write_text(json.dumps({
        "candidate_commit": "b" * 40, "expected_years": list(STATES),
        "alphapai_manifests": entries, "authoritative_manifests": [str(authoritative)],
    }))
    return config


def test_completion_gate_passes_only_with_all_sources(tmp_path: Path) -> None:
    report = build_source_completion_report(_config(tmp_path))
    assert report.gate_pass is True
    assert report.formal_research_eligible is False
    output = tmp_path / "out" / "report.json"
    assert len(write_source_completion_report(report, output)) == 64
    with pytest.raises(FileExistsError):
        write_source_completion_report(report, output)


def test_completion_gate_lists_quarantine_and_source_gaps(tmp_path: Path) -> None:
    report = build_source_completion_report(
        _config(tmp_path, quarantine=2, industry=0, corporate=0)
    )
    assert report.gate_pass is False
    assert report.unresolved_quarantine_records == 2
    assert len(report.blockers) == 3


def test_completion_gate_rejects_missing_year_and_bad_commit(tmp_path: Path) -> None:
    config = _config(tmp_path)
    payload = json.loads(config.read_text())
    payload["alphapai_manifests"].pop()
    config.write_text(json.dumps(payload))
    with pytest.raises(QmtDataError, match="every expected year"):
        build_source_completion_report(config)
    payload["candidate_commit"] = "short"
    config.write_text(json.dumps(payload))
    with pytest.raises(QmtDataError, match="full 40-character"):
        build_source_completion_report(config)
