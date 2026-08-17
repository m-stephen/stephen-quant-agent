from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from stephen_quant.cli import main
from stephen_quant.qmt.models import QmtDataError
from stephen_quant.qmt.qd_data_audit import data_search_ledger_record, run_qd_data_audit

HEADER = "日期,代码,行业,开盘价,最高价,最低价,收盘价,成交量(手),成交额(千元),复权因子,换手率(%),市盈率,市净率,总市值(万元),流通市值(万元)"


def _write_csv(path: Path, rows: list[str], header: str = HEADER) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")


def _manifest(path: Path, root: Path, files: list[str]) -> Path:
    entries = []
    for relative in files:
        source = root / relative
        raw = source.read_bytes() if source.is_file() else b"missing"
        entries.append({"path": relative, "sha256": hashlib.sha256(raw).hexdigest()})
    payload = {
        "version": 1,
        "plane": "research",
        "state": "RESEARCH_ALLOWED_2022_2024",
        "scope": {
            "start_date": "2022-01-01",
            "end_date": "2024-12-31",
            "sealed_years_excluded": [2025, 2026],
            "generated_by": "external-isolation-owner",
            "exclusion_proof": {
                "generated_by": "external-isolation-owner",
                "generated_at": "2026-08-17T18:00:00+08:00",
                "generator_tool_version": "fixture-v1",
                "schema_version": "fixture-v1",
                "method": "explicit allowlist copy",
                "artifact_sha256": "a" * 64,
                "verified_by": "repository-maintainer",
                "verification_reference": "https://github.com/m-stephen/stephen-quant-agent/issues/75",
            },
        },
        "layers": {"daily_bars": entries},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _row(day: str, code: str = "000001.SZ") -> str:
    return f"{day},{code},银行,10,11,9,10.5,100,1000,1,0.5,12,1.2,1000,500"


def test_allowlist_audit_is_deterministic_path_safe_and_ledger_safe(tmp_path: Path) -> None:
    root = tmp_path / "isolated"
    _write_csv(root / "daily" / "20220104.csv", [_row("20220104")])
    _write_csv(root / "daily" / "20241231.csv", [_row("20241231", "000002.SZ")])
    allowlist = _manifest(
        tmp_path / "allowlist.json", root,
        ["daily/20220104.csv", "daily/20241231.csv"],
    )
    first = run_qd_data_audit(root, allowlist)
    second = run_qd_data_audit(root, allowlist)
    assert first.normalized_report_sha256 == second.normalized_report_sha256
    assert first.gate_pass is True
    assert all(value == 0 for value in first.gates.values())
    assert str(root.resolve()) not in first.to_json()
    assert data_search_ledger_record(first)["inferential_registry_operations"] == 0


def test_mislabeled_2024_file_with_2025_row_records_breach_and_fails(tmp_path: Path) -> None:
    root = tmp_path / "isolated"
    _write_csv(root / "daily" / "20241231.csv", [_row("20250102")])
    report = run_qd_data_audit(
        root, _manifest(tmp_path / "allowlist.json", root, ["daily/20241231.csv"])
    )
    assert report.gate_pass is False
    assert report.gates["restricted_year_files_read"] == 1
    assert report.gates["restricted_year_files_hashed"] == 1


def test_missing_header_has_zero_coverage_rejects_and_fails(tmp_path: Path) -> None:
    root = tmp_path / "isolated"
    header = HEADER.replace(",成交量(手)", "")
    row = _row("20240102").replace(",100,1000", ",1000")
    _write_csv(root / "daily" / "20240102.csv", [row], header)
    report = run_qd_data_audit(
        root, _manifest(tmp_path / "allowlist.json", root, ["daily/20240102.csv"])
    )
    volume = next(item for item in report.field_admission if item["field"] == "volume")
    assert volume["coverage_rate"] == 0.0
    assert volume["classification"] == "REJECT"
    assert report.gate_pass is False


def test_cross_file_duplicate_primary_key_fails_gate(tmp_path: Path) -> None:
    root = tmp_path / "isolated"
    _write_csv(root / "a" / "20230103.csv", [_row("20230103")])
    _write_csv(root / "b" / "20230103.csv", [_row("20230103")])
    report = run_qd_data_audit(
        root, _manifest(
            tmp_path / "allowlist.json", root,
            ["a/20230103.csv", "b/20230103.csv"],
        )
    )
    assert report.gates["duplicate_primary_keys"] == 1
    assert report.gate_pass is False


def test_sealed_partition_is_rejected_before_file_access(tmp_path: Path) -> None:
    root = tmp_path / "isolated"
    root.mkdir()
    with pytest.raises(QmtDataError, match="outside 2022-2024 firewall"):
        run_qd_data_audit(
            root, _manifest(tmp_path / "allowlist.json", root, ["daily/20260105.csv"])
        )


def test_cli_failure_writes_evidence_nonzero_without_paths_and_ledger_is_immutable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "isolated"
    row = _row("20240102")
    _write_csv(root / "daily" / "20240102.csv", [row, row])
    allowlist = _manifest(tmp_path / "allowlist.json", root, ["daily/20240102.csv"])
    output = tmp_path / "output"
    argv = [
        "stephen-quant", "qd-data-audit", "--snapshot-root", str(root),
        "--allowlist-manifest", str(allowlist), "--output-dir", str(output),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as first:
        main()
    assert first.value.code == 2
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit):
        main()
    names = {item.name for item in output.iterdir()}
    assert len([name for name in names if name.startswith("data-search-ledger-")]) == 1
    rendered = "".join((output / name).read_text(encoding="utf-8") for name in names)
    captured = capsys.readouterr()
    terminal = captured.out + captured.err
    assert str(root.resolve()) not in rendered
    assert str(root.resolve()) not in terminal


def test_cli_rejects_output_inside_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "isolated"
    _write_csv(root / "daily" / "20240102.csv", [_row("20240102")])
    allowlist = _manifest(tmp_path / "allowlist.json", root, ["daily/20240102.csv"])
    monkeypatch.setattr(sys, "argv", [
        "stephen-quant", "qd-data-audit", "--snapshot-root", str(root),
        "--allowlist-manifest", str(allowlist), "--output-dir", str(root / "output"),
    ])
    with pytest.raises(SystemExit, match="physically disjoint"):
        main()
