from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from stephen_quant.cli import main
from stephen_quant.qmt import single_user_data
from stephen_quant.qmt.models import QmtDataError
from stephen_quant.qmt.single_user_data import (
    create_local_unlock,
    inventory_local_data,
    maintain_local_data,
)

COMMIT = "a" * 40


def _source(root: Path, year: int, content: bytes = b"\x00opaque\xff") -> Path:
    path = root / f"year={year}" / f"announcements-{year}0102.bin"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _inventory(tmp_path: Path, year: int = 2025):
    root = tmp_path / "source"
    _source(root, year)
    result, manifest = inventory_local_data(
        root, tmp_path / "manifests", tmp_path / "ledger",
        year=year, code_commit=COMMIT,
    )
    return root, result, manifest


def _unlock(tmp_path: Path, manifest: Path, year: int = 2025):
    return create_local_unlock(
        manifest, tmp_path / "ledger", year=year,
        purpose="pit-maintenance", expires_in_seconds=3600, code_commit=COMMIT,
    )


def test_inventory_manifest_is_deterministic_and_raw_byte_only(tmp_path: Path) -> None:
    root, first, manifest = _inventory(tmp_path)
    first_bytes = manifest.read_bytes()
    second, second_manifest = inventory_local_data(
        root, tmp_path / "manifests", tmp_path / "ledger",
        year=2025, code_commit=COMMIT,
    )
    assert manifest == second_manifest
    assert first_bytes == second_manifest.read_bytes()
    payload = json.loads(first_bytes)
    assert payload["files"][0]["size_bytes"] == len(b"\x00opaque\xff")
    assert len(payload["files"][0]["sha256"]) == 64
    assert first.inferential_trial_delta == second.inferential_trial_delta == 0
    assert str(root.resolve()) not in first.to_json()


def test_maintain_without_unlock_has_zero_source_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _, manifest = _inventory(tmp_path)
    calls = 0

    def observed(path: Path) -> tuple[str, int]:
        nonlocal calls
        calls += 1
        return "", 0

    monkeypatch.setattr(single_user_data, "_file_sha256", observed)
    with pytest.raises(QmtDataError, match="valid local unlock"):
        maintain_local_data(
            root, manifest, tmp_path / "ledger",
            operation_id="missing", code_commit=COMMIT,
        )
    assert calls == 0
    events = [json.loads(path.read_text(encoding="utf-8")) for path in (
        tmp_path / "ledger" / "events"
    ).glob("*.json")]
    assert any(event["operation"] == "maintain" and event["status"] == "denied" for event in events)


def test_unlock_mismatch_expiry_and_2026_sealed_default(tmp_path: Path) -> None:
    _, _, manifest = _inventory(tmp_path)
    with pytest.raises(QmtDataError, match="year does not match"):
        create_local_unlock(
            manifest, tmp_path / "ledger", year=2026,
            purpose="pit-maintenance", expires_in_seconds=60, code_commit=COMMIT,
            allow_sealed_2026=True,
        )
    _, _, sealed_manifest = _inventory(tmp_path / "sealed", 2026)
    with pytest.raises(QmtDataError, match="remains sealed"):
        create_local_unlock(
            sealed_manifest, tmp_path / "sealed" / "ledger", year=2026,
            purpose="pit-maintenance", expires_in_seconds=60, code_commit=COMMIT,
        )
    unlock = _unlock(tmp_path, manifest)
    unlock_path = tmp_path / "ledger" / "unlocks" / f"{unlock.operation_id}.json"
    payload = json.loads(unlock_path.read_text(encoding="utf-8"))
    payload["expires_at"] = "2000-01-01T00:00:00+00:00"
    unlock_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(QmtDataError, match="does not match"):
        maintain_local_data(
            tmp_path / "source", manifest, tmp_path / "ledger",
            operation_id=str(unlock.operation_id), code_commit=COMMIT,
        )


def test_concurrent_operation_only_one_reader_and_replay_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _, manifest = _inventory(tmp_path)
    unlock = _unlock(tmp_path, manifest)
    original = single_user_data._file_sha256
    calls = 0

    def observed(path: Path) -> tuple[str, int]:
        nonlocal calls
        calls += 1
        return original(path)

    monkeypatch.setattr(single_user_data, "_file_sha256", observed)

    def execute() -> str:
        try:
            maintain_local_data(
                root, manifest, tmp_path / "ledger",
                operation_id=str(unlock.operation_id), code_commit=COMMIT,
            )
            return "success"
        except QmtDataError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: execute(), range(2)))
    assert sorted(outcomes) == ["rejected", "success"]
    assert calls == 1
    with pytest.raises(QmtDataError, match="already been recorded"):
        execute_direct = maintain_local_data(
            root, manifest, tmp_path / "ledger",
            operation_id=str(unlock.operation_id), code_commit=COMMIT,
        )
        assert execute_direct


@pytest.mark.parametrize("failure", ["hash", "size", "missing", "permission"])
def test_file_failures_are_recorded_and_operation_stays_consumed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str,
) -> None:
    root, _, manifest = _inventory(tmp_path)
    unlock = _unlock(tmp_path, manifest)
    source = next((root / "year=2025").iterdir())
    if failure == "hash":
        source.write_bytes(b"x" * source.stat().st_size)
    elif failure == "size":
        source.write_bytes(source.read_bytes() + b"extra")
    elif failure == "missing":
        source.unlink()
    else:
        monkeypatch.setattr(
            single_user_data,
            "_file_sha256",
            lambda path: (_ for _ in ()).throw(QmtDataError("source file I/O failed")),
        )
    with pytest.raises(QmtDataError):
        maintain_local_data(
            root, manifest, tmp_path / "ledger",
            operation_id=str(unlock.operation_id), code_commit=COMMIT,
        )
    operation = json.loads((
        tmp_path / "ledger" / "operations" / f"{unlock.operation_id}.json"
    ).read_text(encoding="utf-8"))
    assert operation["status"] == "failed"
    assert operation["completed_at"]
    with pytest.raises(QmtDataError, match="already been recorded"):
        maintain_local_data(
            root, manifest, tmp_path / "ledger",
            operation_id=str(unlock.operation_id), code_commit=COMMIT,
        )


def test_inventory_rejects_symlink_escape_when_supported(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    outside = _source(tmp_path / "outside", 2025)
    link = root / "year=2025-link.bin"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symbolic links are not available")
    with pytest.raises(QmtDataError, match="symbolic-link"):
        inventory_local_data(
            root, tmp_path / "manifests", tmp_path / "ledger",
            year=2025, code_commit=COMMIT,
        )


@pytest.mark.parametrize("control", ["manifest", "ledger"])
def test_control_paths_cannot_be_inside_data_root(tmp_path: Path, control: str) -> None:
    root = tmp_path / "source"
    _source(root, 2025)
    manifest_dir = root / "manifests" if control == "manifest" else tmp_path / "manifests"
    ledger_dir = root / "ledger" if control == "ledger" else tmp_path / "ledger"
    with pytest.raises(QmtDataError, match="outside the data root"):
        inventory_local_data(
            root, manifest_dir, ledger_dir, year=2025, code_commit=COMMIT,
        )


def test_maintain_rejects_manifest_inside_data_root(tmp_path: Path) -> None:
    root, _, manifest = _inventory(tmp_path)
    inside = root / "control" / manifest.name
    inside.parent.mkdir()
    inside.write_bytes(manifest.read_bytes())
    with pytest.raises(QmtDataError, match="outside the data root"):
        maintain_local_data(
            root, inside, tmp_path / "ledger",
            operation_id="unused", code_commit=COMMIT,
        )


def test_inventory_failure_and_sealed_unlock_are_ledgered(tmp_path: Path) -> None:
    with pytest.raises(QmtDataError):
        inventory_local_data(
            tmp_path / "missing", tmp_path / "manifests", tmp_path / "ledger",
            year=2025, code_commit=COMMIT,
        )
    _, _, manifest = _inventory(tmp_path / "sealed", 2026)
    with pytest.raises(QmtDataError, match="remains sealed"):
        create_local_unlock(
            manifest, tmp_path / "sealed" / "ledger", year=2026,
            purpose="pit-maintenance", expires_in_seconds=60, code_commit=COMMIT,
        )
    statuses = {
        (event["operation"], event["status"])
        for ledger in (tmp_path / "ledger", tmp_path / "sealed" / "ledger")
        for path in (ledger / "events").glob("*.json")
        for event in [json.loads(path.read_text(encoding="utf-8"))]
    }
    assert ("inventory", "failed") in statuses
    assert ("unlock", "denied") in statuses


def test_cli_inventory_unlock_maintain_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "source"
    _source(root, 2025)
    config = tmp_path / "local-paths.json"
    config.write_text(json.dumps({
        "version": 1,
        "paths": {
            "qd_single_user_data_root": str(root),
            "qd_single_user_manifest_dir": str(tmp_path / "manifests"),
            "qd_single_user_ledger_dir": str(tmp_path / "ledger"),
        },
    }), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "stephen-quant", "data-inventory", "--paths-config", str(config),
        "--year", "2025",
    ])
    main()
    inventory_output = json.loads(capsys.readouterr().out)
    manifest = tmp_path / "manifests" / inventory_output["manifest_file"]
    monkeypatch.setattr(sys, "argv", [
        "stephen-quant", "data-unlock", "--paths-config", str(config),
        "--manifest", str(manifest), "--year", "2025",
        "--purpose", "pit-maintenance", "--expires-seconds", "3600",
    ])
    main()
    unlock_output = json.loads(capsys.readouterr().out)
    monkeypatch.setattr(sys, "argv", [
        "stephen-quant", "data-maintain", "--paths-config", str(config),
        "--manifest", str(manifest), "--operation-id", unlock_output["operation_id"],
    ])
    main()
    maintain_output = json.loads(capsys.readouterr().out)
    assert maintain_output["status"] == "success"
    assert maintain_output["inferential_trial_delta"] == 0
    assert str(root.resolve()) not in json.dumps(maintain_output)
