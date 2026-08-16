from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .models import QmtDataError

MEMBERSHIP_ADAPTER_VERSION = "point-in-time-membership-1.0.0"
MEMBERSHIP_FIELDS = (
    "membership_kind",
    "effective_at",
    "available_at",
    "instrument",
    "group_id",
    "group_name",
)


def _time(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise QmtDataError(f"invalid membership {field}: {value}") from exc
    if parsed.tzinfo is None:
        raise QmtDataError(f"membership {field} must include a timezone")
    return parsed


@dataclass(frozen=True)
class PointInTimeMembership:
    membership_kind: str
    effective_at: str
    available_at: str
    ingested_at: str
    instrument: str
    group_id: str
    group_name: str


@dataclass(frozen=True)
class MembershipAudit:
    adapter_version: str
    source_sha256: str
    rows: int
    instruments: int
    groups: int
    kinds: tuple[str, ...]
    effective_start: str
    effective_end: str
    duplicate_keys: int
    timing_violations: int

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)


def load_point_in_time_memberships(
    source: str | Path,
    *,
    ingested_at: str,
) -> tuple[tuple[PointInTimeMembership, ...], MembershipAudit]:
    """Load a normalized industry/concept mapping; inferred historical membership is forbidden."""

    path = Path(source).expanduser().resolve()
    if not path.is_file():
        raise QmtDataError(f"membership source does not exist: {path}")
    ingested = _time(ingested_at, "ingested_at")
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise QmtDataError("membership source must be UTF-8 CSV") from exc
    reader = csv.DictReader(text.splitlines())
    if tuple(reader.fieldnames or ()) != MEMBERSHIP_FIELDS:
        raise QmtDataError(
            "membership CSV must use the exact normalized point-in-time field order"
        )
    rows: list[PointInTimeMembership] = []
    seen: set[tuple[str, str, str]] = set()
    for line_number, row in enumerate(reader, start=2):
        values = {field: (row.get(field) or "").strip() for field in MEMBERSHIP_FIELDS}
        if any(not value for value in values.values()):
            raise QmtDataError(f"membership row {line_number} contains an empty field")
        if values["membership_kind"] not in {"industry", "concept"}:
            raise QmtDataError(f"membership row {line_number} has unsupported kind")
        effective = _time(values["effective_at"], "effective_at")
        available = _time(values["available_at"], "available_at")
        if available < effective:
            raise QmtDataError(f"membership row {line_number} is available before effective")
        if ingested < available:
            raise QmtDataError(f"membership row {line_number} is ingested before available")
        key = (values["effective_at"], values["instrument"], values["group_id"])
        if key in seen:
            raise QmtDataError(f"duplicate point-in-time membership: {key}")
        seen.add(key)
        rows.append(
            PointInTimeMembership(
                **values,
                ingested_at=ingested.isoformat(),
            )
        )
    if not rows:
        raise QmtDataError("membership source is empty")
    rows.sort(key=lambda row: (row.effective_at, row.instrument, row.group_id))
    audit = MembershipAudit(
        adapter_version=MEMBERSHIP_ADAPTER_VERSION,
        source_sha256=hashlib.sha256(raw).hexdigest(),
        rows=len(rows),
        instruments=len({row.instrument for row in rows}),
        groups=len({(row.membership_kind, row.group_id) for row in rows}),
        kinds=tuple(sorted({row.membership_kind for row in rows})),
        effective_start=rows[0].effective_at,
        effective_end=rows[-1].effective_at,
        duplicate_keys=0,
        timing_violations=0,
    )
    return tuple(rows), audit
