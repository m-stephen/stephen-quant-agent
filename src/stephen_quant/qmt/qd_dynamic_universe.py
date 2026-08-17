from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from stephen_quant.integrity.snapshot import build_selected_files_snapshot_manifest

from .csv_adapter import _decode
from .models import QmtDataError

DYNAMIC_UNIVERSE_VERSION = "qd-point-in-time-dynamic-universe-1.0.0"
_PARTITION = re.compile(r"^(\d{8})\.csv$", re.IGNORECASE)


@dataclass(frozen=True)
class DynamicUniverseConfig:
    research_start: str
    research_end: str
    top_n: int = 300
    minimum_history_sessions: int = 120
    liquidity_lookback: int = 20
    minimum_mean_amount_cny: float = 20_000_000.0


@dataclass(frozen=True)
class DailyUniverseMembership:
    decision_date: str
    decision_at: str
    eligible_candidates: int
    selected: int
    entries: tuple[str, ...]
    exits: tuple[str, ...]
    turnover_rate: float
    exclusions: dict[str, int]
    members: tuple[str, ...]


@dataclass(frozen=True)
class DynamicUniverseReport:
    method_version: str
    source_snapshot_sha256: str
    research_start: str
    research_end: str
    configuration: DynamicUniverseConfig
    sessions: int
    unique_members: int
    mean_selected: float
    mean_eligible: float
    mean_turnover_rate: float
    exact_fundamental_matches: int
    memberships: tuple[DailyUniverseMembership, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self) -> str:
        lines = [
            "# QD point-in-time dynamic universe",
            "",
            f"- Method: `{self.method_version}`",
            f"- Source snapshot: `{self.source_snapshot_sha256}`",
            f"- Research dates: {self.research_start} to {self.research_end}",
            f"- Sessions: {self.sessions}",
            f"- Target size: {self.configuration.top_n}",
            f"- Unique members: {self.unique_members}",
            f"- Mean selected: {self.mean_selected:.2f}",
            f"- Mean eligible: {self.mean_eligible:.2f}",
            f"- Mean one-way membership turnover: {self.mean_turnover_rate:.4%}",
            f"- Exact same-day fundamental matches: {self.exact_fundamental_matches}",
            "",
            "| Decision date | Eligible | Selected | Entries | Exits | Turnover |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        lines.extend(
            f"| {item.decision_date} | {item.eligible_candidates} | {item.selected} | "
            f"{len(item.entries)} | {len(item.exits)} | {item.turnover_rate:.4%} |"
            for item in self.memberships
        )
        return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class DynamicUniverseArtifacts:
    json_path: Path
    markdown_path: Path
    membership_jsonl_path: Path
    json_sha256: str
    markdown_sha256: str
    membership_jsonl_sha256: str


def _partitions(root: Path) -> list[tuple[date, Path]]:
    result: list[tuple[date, Path]] = []
    for path in root.iterdir():
        match = _PARTITION.fullmatch(path.name)
        if path.is_file() and match:
            result.append((date.fromisoformat(f"{match[1][:4]}-{match[1][4:6]}-{match[1][6:]}"), path))
    return sorted(result)


def _reader(path: Path) -> csv.DictReader:
    text, _ = _decode(path.read_bytes())
    return csv.DictReader(text.splitlines())


def _is_a_share(instrument: str) -> bool:
    code, separator, exchange = instrument.partition(".")
    if not separator:
        return False
    if exchange == "SH":
        return code.startswith(("600", "601", "603", "605", "688", "689"))
    if exchange == "SZ":
        return code.startswith(("000", "001", "002", "003", "300", "301"))
    return exchange == "BJ" and code.isdigit()


def _listing_metadata(path: Path) -> dict[str, tuple[str, date | None]]:
    reader = _reader(path)
    required = {"代码", "名称", "上市日期"}
    if not reader.fieldnames or not required <= set(reader.fieldnames):
        raise QmtDataError(f"{path.name}: missing dynamic-universe fundamental columns")
    result: dict[str, tuple[str, date | None]] = {}
    for row in reader:
        instrument = (row.get("代码") or "").strip().upper()
        raw = (row.get("上市日期") or "").strip()
        listed = None
        if len(raw) >= 8 and raw[:8].isdigit() and raw[:8] != "00000000":
            listed = date.fromisoformat(f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}")
        result[instrument] = ((row.get("名称") or "").strip().upper(), listed)
    return result


def build_dynamic_universe(
    daily_dir: str | Path,
    fundamental_dir: str | Path,
    config: DynamicUniverseConfig,
) -> DynamicUniverseReport:
    if config.top_n < 1 or config.minimum_history_sessions < 1 or config.liquidity_lookback < 1:
        raise QmtDataError("dynamic-universe counts must be positive")
    if config.minimum_mean_amount_cny < 0:
        raise QmtDataError("minimum_mean_amount_cny cannot be negative")
    try:
        start = date.fromisoformat(config.research_start)
        end = date.fromisoformat(config.research_end)
    except ValueError as exc:
        raise QmtDataError("dynamic-universe boundaries must be ISO dates") from exc
    if start > end:
        raise QmtDataError("research_start must not be after research_end")

    daily_root = Path(daily_dir).expanduser().resolve()
    fundamental_root = Path(fundamental_dir).expanduser().resolve()
    daily = _partitions(daily_root)
    fundamentals = dict(_partitions(fundamental_root))
    research_positions = [index for index, (day, _) in enumerate(daily) if start <= day <= end]
    if not research_positions:
        raise QmtDataError("dynamic-universe research window contains no daily partitions")
    first_position = research_positions[0]
    history_width = max(config.minimum_history_sessions, config.liquidity_lookback) - 1
    selected_daily = daily[max(first_position - history_width, 0) : research_positions[-1] + 1]
    research_daily = [(day, path) for day, path in selected_daily if day >= start]
    missing_fundamental = [day for day, _ in research_daily if day not in fundamentals]
    if missing_fundamental:
        raise QmtDataError(
            f"missing exact same-day fundamental snapshots: {missing_fundamental[:3]}"
        )
    fundamental_files = [fundamentals[day] for day, _ in research_daily]
    common_root = Path(os.path.commonpath((daily_root, fundamental_root)))
    snapshot = build_selected_files_snapshot_manifest(
        common_root, tuple(path for _, path in selected_daily) + tuple(fundamental_files)
    )

    observation_count: dict[str, int] = defaultdict(int)
    amount_history: dict[str, deque[float]] = defaultdict(
        lambda: deque(maxlen=config.liquidity_lookback)
    )
    memberships: list[DailyUniverseMembership] = []
    previous: set[str] = set()
    unique_members: set[str] = set()
    for day, daily_path in selected_daily:
        metadata = _listing_metadata(fundamentals[day]) if day >= start else {}
        reader = _reader(daily_path)
        required = {"代码", "名称", "成交量(手)", "成交额(千元)"}
        if not reader.fieldnames or not required <= set(reader.fieldnames):
            raise QmtDataError(f"{daily_path.name}: missing dynamic-universe daily columns")
        rows: list[tuple[str, str, float, float]] = []
        for row_number, row in enumerate(reader, start=2):
            instrument = (row.get("代码") or "").strip().upper()
            name = (row.get("名称") or "").strip().upper()
            try:
                volume = float((row.get("成交量(手)") or "0").strip())
                amount = float((row.get("成交额(千元)") or "0").strip()) * 1000
            except ValueError as exc:
                raise QmtDataError(f"{daily_path.name} row {row_number}: invalid liquidity") from exc
            rows.append((instrument, name, volume, amount))
            if _is_a_share(instrument) and volume > 0 and amount > 0:
                observation_count[instrument] += 1
                amount_history[instrument].append(amount)
        if day < start:
            continue

        exclusions: dict[str, int] = defaultdict(int)
        eligible: list[tuple[str, float]] = []
        for instrument, name, volume, amount in rows:
            if not _is_a_share(instrument):
                exclusions["non_a_share"] += 1
                continue
            if instrument not in metadata:
                exclusions["missing_fundamental"] += 1
                continue
            fundamental_name, listed = metadata[instrument]
            if listed is None or listed > day:
                exclusions["unknown_or_future_listing_date"] += 1
                continue
            if "ST" in name or "ST" in fundamental_name or "退" in name or "退" in fundamental_name:
                exclusions["risk_warning_or_delisting"] += 1
                continue
            if volume <= 0 or amount <= 0:
                exclusions["not_trading"] += 1
                continue
            if observation_count[instrument] < config.minimum_history_sessions:
                exclusions["insufficient_history"] += 1
                continue
            history = amount_history[instrument]
            if len(history) < config.liquidity_lookback:
                exclusions["insufficient_liquidity_history"] += 1
                continue
            mean_amount = sum(history) / len(history)
            if mean_amount < config.minimum_mean_amount_cny:
                exclusions["below_liquidity_floor"] += 1
                continue
            eligible.append((instrument, mean_amount))
        ranked = sorted(eligible, key=lambda item: (-item[1], item[0]))
        members = tuple(instrument for instrument, _ in ranked[: config.top_n])
        current = set(members)
        entries = tuple(sorted(current - previous))
        exits = tuple(sorted(previous - current))
        denominator = max(len(previous), len(current), 1)
        turnover = (
            (len(entries) + len(exits)) / (2 * denominator)
            if memberships
            else 0.0
        )
        memberships.append(
            DailyUniverseMembership(
                decision_date=day.isoformat(),
                decision_at=f"{day.isoformat()}T15:01:00+08:00",
                eligible_candidates=len(eligible),
                selected=len(members),
                entries=entries,
                exits=exits,
                turnover_rate=turnover,
                exclusions=dict(sorted(exclusions.items())),
                members=members,
            )
        )
        previous = current
        unique_members.update(current)

    return DynamicUniverseReport(
        method_version=DYNAMIC_UNIVERSE_VERSION,
        source_snapshot_sha256=snapshot.snapshot_sha256,
        research_start=start.isoformat(),
        research_end=end.isoformat(),
        configuration=config,
        sessions=len(memberships),
        unique_members=len(unique_members),
        mean_selected=sum(item.selected for item in memberships) / len(memberships),
        mean_eligible=sum(item.eligible_candidates for item in memberships) / len(memberships),
        mean_turnover_rate=sum(item.turnover_rate for item in memberships) / len(memberships),
        exact_fundamental_matches=len(memberships),
        memberships=tuple(memberships),
    )


def _write(path: Path, content: str) -> str:
    path.write_text(content, encoding="utf-8", newline="\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def write_dynamic_universe(
    report: DynamicUniverseReport, output_dir: str | Path
) -> DynamicUniverseArtifacts:
    directory = Path(output_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "dynamic-universe.json"
    markdown_path = directory / "dynamic-universe.md"
    membership_jsonl_path = directory / "dynamic-universe-membership.jsonl"
    json_content = report.to_json() + "\n"
    markdown_content = report.to_markdown()
    jsonl_content = "".join(
        json.dumps(asdict(item), sort_keys=True, ensure_ascii=False) + "\n"
        for item in report.memberships
    )
    return DynamicUniverseArtifacts(
        json_path=json_path,
        markdown_path=markdown_path,
        membership_jsonl_path=membership_jsonl_path,
        json_sha256=_write(json_path, json_content),
        markdown_sha256=_write(markdown_path, markdown_content),
        membership_jsonl_sha256=_write(membership_jsonl_path, jsonl_content),
    )
