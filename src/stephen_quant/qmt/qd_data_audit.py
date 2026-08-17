from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest

from .csv_adapter import _normalize_header
from .data_plane_policy import (
    validate_research_manifest_control,
    verify_github_isolation_proof,
)
from .models import QmtDataError

AUDIT_VERSION = "qd-allowlist-audit-1.1.0-local-prototype"
AUDIT_START = date(2022, 1, 1)
AUDIT_CUTOFF = date(2024, 12, 31)
RESTRICTED_YEARS = frozenset({2025, 2026})
_ABSOLUTE_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|/(?:Users|home|root)/)")

_LAYER_FIELDS: dict[str, dict[str, tuple[str, ...]]] = {
    "daily_bars": {
        "trade_date": ("日期", "date", "交易日期"),
        "instrument": ("代码", "ts_code", "证券代码", "证券代码.后缀", "stock_code"),
        "industry": ("行业",),
        "open": ("开盘价", "开盘"),
        "high": ("最高价", "最高"),
        "low": ("最低价", "最低"),
        "close": ("收盘价", "收盘"),
        "volume": ("成交量(手)", "成交量（手）", "成交量"),
        "amount": ("成交额(千元)", "成交额（千元）", "成交额"),
        "adjustment_factor": ("复权因子",),
        "turnover_rate": ("换手率%", "换手率(%)"),
        "pe": ("市盈率", "市盈率(动)"),
        "pb": ("市净率",),
        "total_market_value": ("总市值(万元)", "总市值"),
        "float_market_value": ("流通市值(万元)", "流通市值"),
    },
    "fundamentals": {
        "trade_date": ("日期",),
        "instrument": ("代码", "ts_code", "证券代码"),
        "industry": ("行业",),
        "listing_date": ("上市日期",),
        "total_shares": ("总股本(亿)",),
        "float_shares": ("流通股本(亿)",),
        "book_value_per_share": ("每股净资产",),
        "earnings_per_share": ("每股收益",),
        "net_margin_pct": ("净利润率%",),
        "revenue_growth_pct": ("收入同比%",),
        "profit_growth_pct": ("利润同比%",),
    },
    "technical_factors": {
        "trade_date": ("trade_date", "日期", "date"),
        "instrument": ("ts_code", "代码", "证券代码"),
    },
    "shenwan_index_like": {
        "trade_date": ("日期",),
        "instrument": ("代码",),
        "industry": ("行业",),
    },
}
_CLASS_A = frozenset({
    "trade_date", "instrument", "open", "high", "low", "close", "volume",
    "amount", "adjustment_factor", "listing_date",
})
_MANDATORY_STRUCTURAL_FIELDS = {
    "daily_bars": frozenset({
        "trade_date", "instrument", "open", "high", "low", "close", "volume", "amount",
    }),
    "fundamentals": frozenset({"trade_date", "instrument"}),
    "technical_factors": frozenset({"trade_date", "instrument"}),
    "shenwan_index_like": frozenset({"trade_date", "instrument"}),
}


@dataclass(frozen=True)
class AllowlistedFile:
    relative_path: str
    path: Path
    partition: date
    expected_sha256: str


@dataclass
class ExecutionEvidence:
    manifest_entries_enumerated: int = 0
    file_open_operations: int = 0
    file_hash_operations: int = 0
    directory_list_operations: int = 0
    inferential_registry_operations: int = 0
    provenance_breaks: int = 0
    isolation_proof_verifications: int = 0
    restricted_files_read: set[str] = field(default_factory=set)
    restricted_files_hashed: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class QdLayerAudit:
    layer: str
    file_count: int
    row_count: int
    instrument_count: int
    first_date: str
    last_date: str
    missing_cells: dict[str, int]
    missing_rates: dict[str, float]
    missing_headers: tuple[str, ...]
    missing_required_headers: int
    duplicate_primary_keys: int
    invalid_ohlc_rows: int
    negative_volume_rows: int
    schema_variants: int
    revision_risk_cells: int
    source_snapshot_sha256: str
    error_count: int
    empty_files: int
    diagnostic_samples: tuple[str, ...]


@dataclass(frozen=True)
class QdAllowlistAudit:
    audit_version: str
    status: str
    scope_start: str
    scope_end: str
    allowlist_manifest_sha256: str
    exclusion_proof_sha256: str
    source_snapshot_sha256: str
    normalized_report_sha256: str
    layers: dict[str, dict[str, object]]
    cross_source: dict[str, object]
    field_admission: tuple[dict[str, object], ...]
    execution_evidence: dict[str, int]
    gates: dict[str, int]
    gate_pass: bool
    ledger_routing: dict[str, object]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True)

    def to_markdown(self, *, language: str) -> str:
        zh = language == "zh"
        title = "QD 2022-2024 显式白名单数据审计" if zh else "QD 2022-2024 Explicit-Allowlist Data Audit"
        lines = [
            f"# {title}", "",
            f"- {'状态' if zh else 'Status'}: `{self.status}`",
            f"- {'范围' if zh else 'Scope'}: `{self.scope_start}` to `{self.scope_end}`",
            f"- {'源快照' if zh else 'Source snapshot'}: `{self.source_snapshot_sha256}`",
            f"- {'规范报告哈希' if zh else 'Normalized report hash'}: `{self.normalized_report_sha256}`",
            f"- {'门禁通过' if zh else 'Gate pass'}: `{self.gate_pass}`", "",
            f"## {'自动门禁' if zh else 'Automated gates'}", "",
        ]
        lines.extend(f"- `{key}`: `{value}`" for key, value in sorted(self.gates.items()))
        lines.extend(["", f"## {'执行证据' if zh else 'Execution evidence'}", ""])
        lines.extend(
            f"- `{key}`: `{value}`" for key, value in sorted(self.execution_evidence.items())
        )
        lines.extend(["", f"## {'数据层' if zh else 'Layers'}", ""])
        for name, layer in sorted(self.layers.items()):
            lines.extend([
                f"### {name}", f"- rows: {layer['row_count']}",
                f"- instruments: {layer['instrument_count']}",
                f"- duplicate_primary_keys: {layer['duplicate_primary_keys']}",
                f"- schema_variants: {layer['schema_variants']}",
                f"- source_snapshot_sha256: `{layer['source_snapshot_sha256']}`", "",
            ])
        lines.extend([f"## {'账本路由' if zh else 'Ledger routing'}", ""])
        lines.extend(f"- `{key}`: `{value}`" for key, value in sorted(self.ledger_routing.items()))
        return "\n".join(lines) + "\n"


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _valid_sha256(value: object, field_name: str) -> str:
    normalized = str(value).lower()
    if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
        raise QmtDataError(f"invalid {field_name}")
    return normalized


def _canonical_hash(payload: object) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256(raw.encode("utf-8"))


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise QmtDataError(f"duplicate allowlist key: {key}")
        result[key] = value
    return result


def _load_allowlist(
    path: Path, evidence: ExecutionEvidence, github_token: str | None,
) -> tuple[dict[str, object], str, str]:
    raw = path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QmtDataError("allowlist manifest must be UTF-8 JSON") from exc
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise QmtDataError("allowlist manifest must use version 1")
    validate_research_manifest_control(payload)
    scope = payload.get("scope")
    if not isinstance(scope, dict):
        raise QmtDataError("allowlist manifest requires scope")
    expected = {
        "start_date": AUDIT_START.isoformat(),
        "end_date": AUDIT_CUTOFF.isoformat(),
        "sealed_years_excluded": [2025, 2026],
    }
    for key, value in expected.items():
        if scope.get(key) != value:
            raise QmtDataError(f"allowlist scope {key} must equal {value!r}")
    proof = scope.get("exclusion_proof")
    if not isinstance(proof, dict):
        raise QmtDataError("allowlist scope requires structured exclusion_proof")
    for key in (
        "generated_by", "generated_at", "generator_tool_version", "schema_version",
        "method", "artifact_sha256", "verified_by", "verification_reference",
    ):
        if not isinstance(proof.get(key), str) or not str(proof[key]).strip():
            raise QmtDataError(f"exclusion_proof requires {key}")
    generated_at = datetime.fromisoformat(str(proof["generated_at"]).replace("Z", "+00:00"))
    if generated_at.tzinfo is None:
        raise QmtDataError("exclusion proof generated_at must include timezone")
    proof_sha = _valid_sha256(proof["artifact_sha256"], "exclusion proof hash")
    layers = payload.get("layers")
    if not isinstance(layers, dict) or not layers:
        raise QmtDataError("allowlist manifest requires non-empty layers")
    actual_artifact_sha = _canonical_hash(layers)
    if proof_sha != actual_artifact_sha:
        raise QmtDataError("exclusion proof hash does not bind the allowlist artifact")
    verify_github_isolation_proof(
        str(proof["verification_reference"]),
        artifact_sha256=actual_artifact_sha,
        start_date=AUDIT_START.isoformat(),
        end_date=AUDIT_CUTOFF.isoformat(),
        sealed_years_excluded=(2025, 2026),
        github_token=github_token,
    )
    evidence.isolation_proof_verifications += 1
    return payload, _sha256(raw), proof_sha


def _resolve_files(
    root: Path, payload: dict[str, object], evidence: ExecutionEvidence,
) -> dict[str, tuple[AllowlistedFile, ...]]:
    result: dict[str, tuple[AllowlistedFile, ...]] = {}
    layers = payload["layers"]
    assert isinstance(layers, dict)
    for layer, entries in sorted(layers.items()):
        if layer not in _LAYER_FIELDS or not isinstance(entries, list) or not entries:
            raise QmtDataError(f"invalid allowlist layer: {layer}")
        files: list[AllowlistedFile] = []
        seen: set[str] = set()
        for entry in entries:
            evidence.manifest_entries_enumerated += 1
            if not isinstance(entry, dict):
                raise QmtDataError("allowlist file entries must bind path and sha256")
            raw_path = entry.get("path")
            if not isinstance(raw_path, str) or not raw_path.strip():
                raise QmtDataError("allowlist file path must be non-empty")
            relative = Path(raw_path)
            normalized = relative.as_posix()
            if relative.is_absolute() or ".." in relative.parts:
                raise QmtDataError("allowlist paths must be safe relative paths")
            if normalized in seen:
                raise QmtDataError(f"duplicate allowlist path: {normalized}")
            seen.add(normalized)
            stem = relative.stem
            if relative.suffix.lower() != ".csv" or len(stem) != 8 or not stem.isdigit():
                raise QmtDataError(f"allowlist path is not date-partitioned: {normalized}")
            partition = date(int(stem[:4]), int(stem[4:6]), int(stem[6:8]))
            if not AUDIT_START <= partition <= AUDIT_CUTOFF:
                raise QmtDataError(f"allowlist partition outside 2022-2024 firewall: {stem}")
            candidate = (root / relative).resolve()
            try:
                candidate.relative_to(root)
            except ValueError as exc:
                raise QmtDataError("allowlist path escapes snapshot root") from exc
            files.append(AllowlistedFile(
                relative_path=normalized,
                path=candidate,
                partition=partition,
                expected_sha256=_valid_sha256(entry.get("sha256"), "allowlist file sha256"),
            ))
        result[layer] = tuple(files)
    return result


def _hash_file(source: AllowlistedFile, evidence: ExecutionEvidence) -> tuple[str, int]:
    if not source.path.is_file():
        evidence.provenance_breaks += 1
        return "", 0
    digest = hashlib.sha256()
    size = 0
    with source.path.open("rb") as handle:
        evidence.file_hash_operations += 1
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    actual = digest.hexdigest()
    if actual != source.expected_sha256:
        evidence.provenance_breaks += 1
    return actual, size


@contextmanager
def _open_csv(source: AllowlistedFile, evidence: ExecutionEvidence) -> Iterator[csv.DictReader]:
    evidence.file_open_operations += 1
    with source.path.open("rb") as handle:
        header = handle.readline()
    encoding = "utf-8-sig"
    try:
        header.decode(encoding)
    except UnicodeDecodeError:
        encoding = "gb18030"
    with source.path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise QmtDataError("allowlisted CSV has no header")
        yield reader


def _columns(
    headers: tuple[str, ...], required: dict[str, tuple[str, ...]],
) -> dict[str, str | None]:
    normalized = {_normalize_header(value): value for value in headers}
    return {
        field: next((
            normalized[_normalize_header(alias)]
            for alias in aliases
            if _normalize_header(alias) in normalized
        ), None)
        for field, aliases in required.items()
    }


def _value(row: dict[str, Any], column: str | None) -> str:
    return "" if column is None or row.get(column) is None else str(row[column]).strip()


def _date(value: str) -> date | None:
    raw = value.replace("-", "")[:8]
    if len(raw) != 8 or not raw.isdigit():
        return None
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
    except ValueError:
        return None


def _layer_snapshot(entries: list[tuple[str, str, int]]) -> str:
    return _canonical_hash([
        {"path": path, "sha256": digest, "size_bytes": size}
        for path, digest, size in sorted(entries)
    ])


def _audit_layer(
    layer: str,
    files: tuple[AllowlistedFile, ...],
    evidence: ExecutionEvidence,
) -> tuple[QdLayerAudit, set[str]]:
    required = _LAYER_FIELDS[layer]
    missing: Counter[str] = Counter()
    schemas: set[str] = set()
    instruments: set[str] = set()
    seen_keys: set[tuple[date, str]] = set()
    partitions = [source.partition for source in files]
    duplicates = invalid_ohlc = negative_volume = revisions = errors = empty_files = rows = 0
    missing_headers = 0
    absent_headers: set[str] = set()
    samples: list[str] = []
    prior: dict[tuple[str, str], str] = {}
    snapshot_entries: list[tuple[str, str, int]] = []
    for source in files:
        actual_hash, size = _hash_file(source, evidence)
        snapshot_entries.append((source.relative_path, actual_hash, size))
        if not actual_hash or actual_hash != source.expected_sha256:
            errors += 1
            continue
        file_rows = 0
        with _open_csv(source, evidence) as reader:
            headers = tuple(reader.fieldnames or ())
            schemas.add("|".join(headers))
            columns = _columns(headers, required)
            absent_fields = {field for field, column in columns.items() if column is None}
            absent_headers.update(absent_fields)
            missing_headers += len(absent_fields)
            for line_number, row in enumerate(reader, start=2):
                rows += 1
                file_rows += 1
                for field in absent_fields:
                    missing[field] += 1
                observed = _date(_value(row, columns.get("trade_date")))
                if observed != source.partition:
                    errors += 1
                    if observed is not None and observed.year in RESTRICTED_YEARS:
                        evidence.restricted_files_read.add(source.relative_path)
                        evidence.restricted_files_hashed.add(source.relative_path)
                    if len(samples) < 100:
                        samples.append(
                            f"{layer}:{source.relative_path}:{line_number}:partition_mismatch"
                        )
                    continue
                instrument = _value(row, columns.get("instrument")).upper()
                if not instrument:
                    errors += 1
                    continue
                key = (observed, instrument)
                if key in seen_keys:
                    duplicates += 1
                seen_keys.add(key)
                instruments.add(instrument)
                for field, column in columns.items():
                    if column is not None and not _value(row, column):
                        missing[field] += 1
                if all(columns.get(field) for field in ("open", "high", "low", "close")):
                    try:
                        open_, high, low, close = (
                            float(_value(row, columns[field]))
                            for field in ("open", "high", "low", "close")
                        )
                        if low > high or not low <= open_ <= high or not low <= close <= high:
                            invalid_ohlc += 1
                    except ValueError:
                        invalid_ohlc += 1
                if columns.get("volume"):
                    try:
                        if float(_value(row, columns["volume"])) < 0:
                            negative_volume += 1
                    except ValueError:
                        negative_volume += 1
                if layer == "fundamentals":
                    for field in required:
                        if field in {"trade_date", "instrument"}:
                            continue
                        cell = _value(row, columns.get(field))
                        if cell:
                            history_key = (instrument, field)
                            if history_key in prior and prior[history_key] != cell:
                                revisions += 1
                            prior[history_key] = cell
        if file_rows == 0:
            empty_files += 1
    rates = {
        field: round(missing[field] / rows, 8) if rows else 1.0
        for field in required
    }
    return QdLayerAudit(
        layer=layer,
        file_count=len(files),
        row_count=rows,
        instrument_count=len(instruments),
        first_date=min(partitions).isoformat(),
        last_date=max(partitions).isoformat(),
        missing_cells=dict(sorted(missing.items())),
        missing_rates=rates,
        missing_headers=tuple(sorted(absent_headers)),
        missing_required_headers=missing_headers,
        duplicate_primary_keys=duplicates,
        invalid_ohlc_rows=invalid_ohlc,
        negative_volume_rows=negative_volume,
        schema_variants=len(schemas),
        revision_risk_cells=revisions,
        source_snapshot_sha256=_layer_snapshot(snapshot_entries),
        error_count=errors,
        empty_files=empty_files,
        diagnostic_samples=tuple(samples),
    ), instruments


def _field_admission(layers: dict[str, dict[str, object]]) -> tuple[dict[str, object], ...]:
    result: list[dict[str, object]] = []
    for layer, audit in sorted(layers.items()):
        missing_rates = audit["missing_rates"]
        assert isinstance(missing_rates, dict)
        missing_headers = set(audit["missing_headers"])
        mandatory = _MANDATORY_STRUCTURAL_FIELDS[layer]
        for field_name in _LAYER_FIELDS[layer]:
            missing_rate = float(missing_rates[field_name])
            rejected = field_name in missing_headers or (
                field_name in mandatory and missing_rate > 0
            )
            classification = (
                "REJECT" if rejected else "C" if layer == "technical_factors"
                else "A" if field_name in _CLASS_A else "B"
            )
            result.append({
                "source": layer,
                "field": field_name,
                "date_from": audit["first_date"],
                "date_to": audit["last_date"],
                "classification": classification,
                "evidence_sha256": audit["source_snapshot_sha256"],
                "coverage_rate": round(1.0 - missing_rate, 8),
                "missing_rate": missing_rate,
                "revision_risk_cells": audit["revision_risk_cells"],
                "allowed_use": (
                    "none_required_field_missing" if rejected
                    else "coverage_filtered" if missing_rate > 0
                    else "after_close_or_next_session" if classification == "A"
                    else "candidate_only_requires_pit_evidence" if classification == "B"
                    else "not_for_formal_alpha_acceptance"
                ),
            })
    return tuple(result)


def _absolute_path_leaks(payload: object) -> int:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return len(_ABSOLUTE_PATH.findall(serialized))


def run_qd_data_audit(
    snapshot_root: str | Path,
    allowlist_manifest: str | Path,
    *,
    github_token: str | None = None,
) -> QdAllowlistAudit:
    root = Path(snapshot_root).expanduser().resolve()
    manifest = Path(allowlist_manifest).expanduser().resolve()
    if not root.is_dir() or not manifest.is_file():
        raise QmtDataError("snapshot root and allowlist manifest must exist")
    evidence = ExecutionEvidence()
    payload, manifest_sha, proof_sha = _load_allowlist(manifest, evidence, github_token)
    allowlisted = _resolve_files(root, payload, evidence)
    layers: dict[str, dict[str, object]] = {}
    instrument_sets: dict[str, set[str]] = {}
    for layer, files in sorted(allowlisted.items()):
        audit, instruments = _audit_layer(layer, files, evidence)
        layers[layer] = asdict(audit)
        instrument_sets[layer] = instruments
    source_snapshot = build_composite_snapshot_manifest({
        name: str(layer["source_snapshot_sha256"])
        for name, layer in layers.items()
    }).snapshot_sha256
    daily = instrument_sets.get("daily_bars", set())
    fundamentals = instrument_sets.get("fundamentals", set())
    union = daily | fundamentals
    cross = {
        "daily_instruments": len(daily),
        "fundamental_instruments": len(fundamentals),
        "overlap_instruments": len(daily & fundamentals),
        "overlap_ratio": round(len(daily & fundamentals) / len(union), 8) if union else 0.0,
    }
    layer_values = tuple(layers.values())
    evidence_payload = {
        "manifest_entries_enumerated": evidence.manifest_entries_enumerated,
        "file_open_operations": evidence.file_open_operations,
        "file_hash_operations": evidence.file_hash_operations,
        "directory_list_operations": evidence.directory_list_operations,
        "inferential_registry_operations": evidence.inferential_registry_operations,
        "isolation_proof_verifications": evidence.isolation_proof_verifications,
    }
    gates = {
        "duplicate_primary_keys": sum(int(value["duplicate_primary_keys"]) for value in layer_values),
        "provenance_breaks": evidence.provenance_breaks,
        "restricted_year_files_read": len(evidence.restricted_files_read),
        "restricted_year_files_hashed": len(evidence.restricted_files_hashed),
        "restricted_year_directory_lists": evidence.directory_list_operations,
        "date_or_row_errors": sum(int(value["error_count"]) for value in layer_values),
        "missing_mandatory_headers": sum(
            len(set(value["missing_headers"]) & _MANDATORY_STRUCTURAL_FIELDS[str(value["layer"])])
            for value in layer_values
        ),
        "missing_mandatory_cells": sum(
            sum(
                int(dict(value["missing_cells"]).get(field_name, 0))
                for field_name in _MANDATORY_STRUCTURAL_FIELDS[str(value["layer"])]
            )
            for value in layer_values
        ),
        "empty_files": sum(int(value["empty_files"]) for value in layer_values),
        "invalid_ohlc_rows": sum(int(value["invalid_ohlc_rows"]) for value in layer_values),
        "negative_volume_rows": sum(int(value["negative_volume_rows"]) for value in layer_values),
        "schema_drift_layers": sum(int(value["schema_variants"]) != 1 for value in layer_values),
        "inferential_registry_operations": evidence.inferential_registry_operations,
        "isolation_proof_failures": int(evidence.isolation_proof_verifications != 1),
    }
    ledger = {
        "audit": "data_search_ledger",
        "remote_retrieval": "not_run_phase_0_1a",
        "inferential_trials": "registry_not_opened",
    }
    base: dict[str, object] = {
        "audit_version": AUDIT_VERSION,
        "status": "local_prototype_evidence_pending_pr_review",
        "scope_start": AUDIT_START.isoformat(),
        "scope_end": AUDIT_CUTOFF.isoformat(),
        "allowlist_manifest_sha256": manifest_sha,
        "exclusion_proof_sha256": proof_sha,
        "source_snapshot_sha256": source_snapshot,
        "layers": layers,
        "cross_source": cross,
        "field_admission": _field_admission(layers),
        "execution_evidence": evidence_payload,
        "gates": gates,
        "ledger_routing": ledger,
    }
    gates["absolute_path_leaks"] = _absolute_path_leaks(base)
    gate_pass = all(value == 0 for value in gates.values())
    base["gate_pass"] = gate_pass
    normalized_hash = _canonical_hash(base)
    return QdAllowlistAudit(normalized_report_sha256=normalized_hash, **base)


def data_search_ledger_record(report: QdAllowlistAudit) -> dict[str, object]:
    payload = {
        "ledger": "data_search_ledger",
        "operation": "qd_allowlist_audit",
        "audit_version": report.audit_version,
        "allowlist_manifest_sha256": report.allowlist_manifest_sha256,
        "source_snapshot_sha256": report.source_snapshot_sha256,
        "normalized_report_sha256": report.normalized_report_sha256,
        "gate_pass": report.gate_pass,
        "inferential_registry_operations": report.execution_evidence[
            "inferential_registry_operations"
        ],
        "remote_retrieval_operations": 0,
    }
    return {"event_id": _canonical_hash(payload), **payload}
