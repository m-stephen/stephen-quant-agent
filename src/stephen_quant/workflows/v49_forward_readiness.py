from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

V49_READINESS_VERSION = "v4.9-forward-readiness-1.0.0"
CONSUMED_THROUGH = "2026-08-16"
MINIMUM_NEW_COMMON_DATES = 25
_DATE_NAME = re.compile(r"^(?P<year>\d{4})[-_]?(?P<month>\d{2})[-_]?(?P<day>\d{2})$")


@dataclass(frozen=True)
class SourceCoverage:
    source: str
    new_dates: int
    latest_date: str | None
    inventory_sha256: str


@dataclass(frozen=True)
class V49ReadinessReport:
    method_version: str
    as_of: str
    consumed_through: str
    minimum_new_common_dates: int
    sources: tuple[SourceCoverage, ...]
    common_new_dates: int
    latest_common_date: str | None
    missing_by_source: tuple[tuple[str, int], ...]
    ready: bool
    decision: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        lines = [
            "# V4.9 前向续验就绪检查" if zh else "# V4.9 Forward Continuation Readiness",
            "",
            f"**{'结论' if zh else 'Decision'}: `{self.decision}`**",
            "",
            f"- {'检查日期' if zh else 'As of'}: {self.as_of}",
            f"- {'已消费至' if zh else 'Consumed through'}: {self.consumed_through}",
            (
                f"- {'共同新增交易日' if zh else 'New common trading dates'}: "
                f"{self.common_new_dates}/{self.minimum_new_common_dates}"
            ),
            (
                f"- {'最新共同日期' if zh else 'Latest common date'}: "
                f"{self.latest_common_date or 'N/A'}"
            ),
            "",
            "| Source | New dates | Latest | Inventory SHA-256 |",
            "|---|---:|---|---|",
        ]
        lines.extend(
            f"| {item.source} | {item.new_dates} | {item.latest_date or 'N/A'} | `{item.inventory_sha256}` |"
            for item in self.sources
        )
        return "\n".join(lines) + "\n"


def _date_from_file(path: Path) -> str | None:
    match = _DATE_NAME.fullmatch(path.stem)
    if match is None:
        return None
    value = f"{match['year']}-{match['month']}-{match['day']}"
    try:
        date.fromisoformat(value)
    except ValueError:
        return None
    return value


def _inventory(root: str | Path, *, as_of: str) -> tuple[set[str], str]:
    directory = Path(root).expanduser().resolve()
    if not directory.is_dir():
        raise ValueError(f"V4.9 source directory does not exist: {directory}")
    rows = []
    dates = set()
    for path in sorted(directory.rglob("*.csv")):
        day = _date_from_file(path)
        if day is None or day > as_of:
            continue
        relative = path.relative_to(directory).as_posix()
        rows.append((relative, path.stat().st_size))
        if day > CONSUMED_THROUGH:
            dates.add(day)
    digest = hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return dates, digest


def run_v49_forward_readiness(
    daily_dir: str | Path,
    fund_flow_dir: str | Path,
    auction_dir: str | Path,
    *,
    output_dir: str | Path,
    as_of: str | None = None,
) -> V49ReadinessReport:
    as_of = as_of or datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    date.fromisoformat(as_of)
    if as_of <= CONSUMED_THROUGH:
        raise ValueError("V4.9 as-of must be after the consumed window")
    inventories = {}
    coverage = []
    for source, root in (
        ("qd_daily", daily_dir),
        ("qd_fund_flow", fund_flow_dir),
        ("qd_auction", auction_dir),
    ):
        dates, digest = _inventory(root, as_of=as_of)
        inventories[source] = dates
        coverage.append(SourceCoverage(source, len(dates), max(dates) if dates else None, digest))
    common = set.intersection(*inventories.values())
    union = set.union(*inventories.values())
    missing = tuple(
        (source, len(union - dates))
        for source, dates in sorted(inventories.items())
    )
    ready = len(common) >= MINIMUM_NEW_COMMON_DATES
    report = V49ReadinessReport(
        V49_READINESS_VERSION,
        as_of,
        CONSUMED_THROUGH,
        MINIMUM_NEW_COMMON_DATES,
        tuple(coverage),
        len(common),
        max(common) if common else None,
        missing,
        ready,
        "READY_FOR_FROZEN_V4_9_COURT" if ready else "WAIT_FOR_NEW_COMMON_DATA",
    )
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "v4.9-forward-readiness.json").write_text(report.to_json() + "\n", encoding="utf-8")
    (output / "v4.9-forward-readiness.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (output / "v4.9-forward-readiness.en.md").write_text(report.to_markdown("en"), encoding="utf-8")
    return report
