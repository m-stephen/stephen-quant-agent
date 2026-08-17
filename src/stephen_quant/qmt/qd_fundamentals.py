from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from stephen_quant.integrity.snapshot import build_selected_files_snapshot_manifest

from .csv_adapter import _decode
from .models import QmtDataError

QD_FUNDAMENTAL_ADAPTER_VERSION = "qd-confirmed-fundamentals-1.0.0"
_PARTITION = re.compile(r"^(\d{8})\.csv$", re.IGNORECASE)
_REQUIRED_COLUMNS = {
    "日期",
    "代码",
    "行业",
    "总股本(亿)",
    "每股净资产",
    "每股收益",
    "净利润率%",
    "收入同比%",
    "利润同比%",
}
_FIELDS = (
    "industry",
    "total_shares",
    "book_value_per_share",
    "earnings_per_share",
    "net_margin_pct",
    "revenue_growth_pct",
    "profit_growth_pct",
)
_COLUMNS = {
    "industry": "行业",
    "total_shares": "总股本(亿)",
    "book_value_per_share": "每股净资产",
    "earnings_per_share": "每股收益",
    "net_margin_pct": "净利润率%",
    "revenue_growth_pct": "收入同比%",
    "profit_growth_pct": "利润同比%",
}


@dataclass(frozen=True)
class ConfirmedFundamentalObservation:
    decision_date: str
    available_at: str
    instrument: str
    industry: str | None
    total_shares: float | None
    book_value_per_share: float | None
    earnings_per_share: float | None
    net_margin_pct: float | None
    revenue_growth_pct: float | None
    profit_growth_pct: float | None


@dataclass(frozen=True)
class QdFundamentalAudit:
    adapter_version: str
    source_snapshot_sha256: str
    research_start: str
    research_end: str
    confirmation_sessions: int
    warmup_sessions: int
    source_files: int
    research_sessions: int
    requested_member_rows: int
    emitted_rows: int
    missing_member_rows: int
    invalid_numeric_cells: dict[str, int]
    confirmed_cells: dict[str, int]
    withheld_transition_cells: dict[str, int]
    nonpositive_confirmed_cells: dict[str, int]
    numeric_ranges: dict[str, dict[str, float | None]]
    field_coverage: dict[str, float]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)


@dataclass(frozen=True)
class QdFundamentalDataset:
    observations: tuple[ConfirmedFundamentalObservation, ...]
    audit: QdFundamentalAudit


@dataclass
class _ConfirmationState:
    candidate: str | None = None
    streak: int = 0
    confirmed: str | None = None

    def update(self, value: str | None, required_streak: int) -> None:
        if value is None:
            return
        if value == self.candidate:
            self.streak += 1
        else:
            self.candidate = value
            self.streak = 1
        if self.streak >= required_streak:
            self.confirmed = value


def _partitions(root: Path) -> list[tuple[date, Path]]:
    result: list[tuple[date, Path]] = []
    for path in root.iterdir():
        match = _PARTITION.fullmatch(path.name)
        if path.is_file() and match:
            raw = match[1]
            result.append((date.fromisoformat(f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"), path))
    return sorted(result)


def read_dynamic_memberships(path: str | Path) -> dict[str, tuple[str, ...]]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise QmtDataError(f"dynamic membership JSONL does not exist: {source}")
    result: dict[str, tuple[str, ...]] = {}
    for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            decision_date = date.fromisoformat(str(payload["decision_date"])).isoformat()
            members = tuple(sorted({str(item).strip().upper() for item in payload["members"]}))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise QmtDataError(f"membership JSONL line {line_number} is invalid") from exc
        if decision_date in result:
            raise QmtDataError(f"duplicate dynamic membership date: {decision_date}")
        result[decision_date] = members
    if not result:
        raise QmtDataError("dynamic membership JSONL is empty")
    return result


def _canonical_cell(raw: str | None, field: str, invalid: dict[str, int]) -> str | None:
    value = (raw or "").strip()
    if not value or value in {"--", "-", "N/A", "NA", "NULL", "null"}:
        return None
    if field == "industry":
        return value
    try:
        number = float(value.replace(",", ""))
    except ValueError:
        invalid[field] += 1
        return None
    if not math.isfinite(number):
        invalid[field] += 1
        return None
    if number == 0:
        number = 0.0
    return format(number, ".15g")


def _number(value: str | None, field: str) -> float | None:
    if value is None:
        return None
    result = float(value)
    return result * 100_000_000 if field == "total_shares" else result


def load_qd_confirmed_fundamentals(
    source_dir: str | Path,
    memberships: Mapping[str, Sequence[str]],
    *,
    confirmation_sessions: int = 2,
    warmup_sessions: int = 20,
) -> QdFundamentalDataset:
    """Load point-in-time daily snapshots with per-field persistence confirmation.

    A new field value is promoted only after it appears unchanged in the requested
    number of consecutive source snapshots. Until then, the last confirmed value is
    retained. Observations become usable after the source day's close.
    """

    if confirmation_sessions < 1:
        raise QmtDataError("confirmation_sessions must be positive")
    if warmup_sessions < confirmation_sessions:
        raise QmtDataError("warmup_sessions must cover confirmation_sessions")
    normalized_memberships = {
        date.fromisoformat(str(day)).isoformat(): tuple(
            sorted({str(item).strip().upper() for item in members})
        )
        for day, members in memberships.items()
    }
    if not normalized_memberships:
        raise QmtDataError("fundamental memberships cannot be empty")
    research_dates = sorted(normalized_memberships)
    start = date.fromisoformat(research_dates[0])
    end = date.fromisoformat(research_dates[-1])
    root = Path(source_dir).expanduser().resolve()
    if not root.is_dir():
        raise QmtDataError(f"fundamental source is not a directory: {root}")
    partitions = _partitions(root)
    positions = [index for index, (day, _) in enumerate(partitions) if start <= day <= end]
    if not positions:
        raise QmtDataError(f"missing exact same-day fundamental snapshots: {research_dates[:3]}")
    selected = partitions[max(positions[0] - warmup_sessions, 0) : positions[-1] + 1]
    available_dates = {day.isoformat() for day, _ in selected}
    missing_dates = [day for day in research_dates if day not in available_dates]
    if missing_dates:
        raise QmtDataError(f"missing exact same-day fundamental snapshots: {missing_dates[:3]}")

    snapshot = build_selected_files_snapshot_manifest(root, (path for _, path in selected))
    union = {instrument for members in normalized_memberships.values() for instrument in members}
    states = {
        instrument: {field: _ConfirmationState() for field in _FIELDS} for instrument in union
    }
    observations: list[ConfirmedFundamentalObservation] = []
    invalid = {field: 0 for field in _FIELDS if field != "industry"}
    confirmed = {field: 0 for field in _FIELDS}
    withheld = {field: 0 for field in _FIELDS}
    nonpositive = {field: 0 for field in _FIELDS if field != "industry"}
    ranges: dict[str, list[float]] = {
        field: [] for field in _FIELDS if field != "industry"
    }
    requested_rows = 0
    missing_rows = 0

    for partition_date, path in selected:
        text, _ = _decode(path.read_bytes())
        reader = csv.DictReader(text.splitlines())
        if not reader.fieldnames or not _REQUIRED_COLUMNS <= set(reader.fieldnames):
            missing = sorted(_REQUIRED_COLUMNS - set(reader.fieldnames or ()))
            raise QmtDataError(f"{path.name}: missing fundamental columns: {missing}")
        expected_date = partition_date.strftime("%Y%m%d")
        seen: set[str] = set()
        rows: dict[str, dict[str, str | None]] = {}
        for row_number, row in enumerate(reader, start=2):
            instrument = (row.get("代码") or "").strip().upper()
            if instrument not in union:
                continue
            raw_date = (row.get("日期") or "").strip().replace("-", "")[:8]
            if raw_date != expected_date:
                raise QmtDataError(
                    f"{path.name} row {row_number}: row date does not match filename"
                )
            if instrument in seen:
                raise QmtDataError(f"{path.name} row {row_number}: duplicate instrument")
            seen.add(instrument)
            rows[instrument] = row
            for field, column in _COLUMNS.items():
                states[instrument][field].update(
                    _canonical_cell(row.get(column), field, invalid), confirmation_sessions
                )

        decision_date = partition_date.isoformat()
        members = normalized_memberships.get(decision_date)
        if members is None:
            continue
        requested_rows += len(members)
        for instrument in members:
            if instrument not in rows:
                missing_rows += 1
                continue
            values = {field: states[instrument][field].confirmed for field in _FIELDS}
            for field, value in values.items():
                if value is not None:
                    confirmed[field] += 1
                state = states[instrument][field]
                if state.candidate is not None and state.candidate != state.confirmed:
                    withheld[field] += 1
                if field != "industry" and value is not None:
                    number = _number(value, field)
                    if number is not None:
                        ranges[field].append(number)
                        if number <= 0:
                            nonpositive[field] += 1
            observations.append(
                ConfirmedFundamentalObservation(
                    decision_date=decision_date,
                    available_at=f"{decision_date}T15:01:00+08:00",
                    instrument=instrument,
                    industry=values["industry"],
                    total_shares=_number(values["total_shares"], "total_shares"),
                    book_value_per_share=_number(
                        values["book_value_per_share"], "book_value_per_share"
                    ),
                    earnings_per_share=_number(values["earnings_per_share"], "earnings_per_share"),
                    net_margin_pct=_number(values["net_margin_pct"], "net_margin_pct"),
                    revenue_growth_pct=_number(
                        values["revenue_growth_pct"], "revenue_growth_pct"
                    ),
                    profit_growth_pct=_number(values["profit_growth_pct"], "profit_growth_pct"),
                )
            )

    denominator = max(requested_rows, 1)
    audit = QdFundamentalAudit(
        adapter_version=QD_FUNDAMENTAL_ADAPTER_VERSION,
        source_snapshot_sha256=snapshot.snapshot_sha256,
        research_start=start.isoformat(),
        research_end=end.isoformat(),
        confirmation_sessions=confirmation_sessions,
        warmup_sessions=warmup_sessions,
        source_files=len(selected),
        research_sessions=len(research_dates),
        requested_member_rows=requested_rows,
        emitted_rows=len(observations),
        missing_member_rows=missing_rows,
        invalid_numeric_cells=dict(sorted(invalid.items())),
        confirmed_cells=dict(sorted(confirmed.items())),
        withheld_transition_cells=dict(sorted(withheld.items())),
        nonpositive_confirmed_cells=dict(sorted(nonpositive.items())),
        numeric_ranges={
            field: {
                "minimum": min(values) if values else None,
                "maximum": max(values) if values else None,
            }
            for field, values in sorted(ranges.items())
        },
        field_coverage={
            field: confirmed[field] / denominator for field in sorted(confirmed)
        },
    )
    return QdFundamentalDataset(observations=tuple(observations), audit=audit)


def write_qd_fundamental_dataset(
    dataset: QdFundamentalDataset, output_dir: str | Path
) -> tuple[Path, Path, str, str]:
    directory = Path(output_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    audit_path = directory / "fundamental-audit.json"
    observations_path = directory / "confirmed-fundamentals.jsonl"
    audit_content = dataset.audit.to_json() + "\n"
    observation_content = "".join(
        json.dumps(asdict(item), sort_keys=True, ensure_ascii=False) + "\n"
        for item in dataset.observations
    )
    audit_path.write_text(audit_content, encoding="utf-8", newline="\n")
    observations_path.write_text(observation_content, encoding="utf-8", newline="\n")
    return (
        audit_path,
        observations_path,
        hashlib.sha256(audit_content.encode("utf-8")).hexdigest(),
        hashlib.sha256(observation_content.encode("utf-8")).hexdigest(),
    )
