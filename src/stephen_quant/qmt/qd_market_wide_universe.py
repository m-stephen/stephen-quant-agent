from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from stephen_quant.integrity.snapshot import build_selected_files_snapshot_manifest

from .models import QmtDataError
from .qd_dynamic_universe import _is_a_share, _listing_metadata, _partitions, _reader

MARKET_WIDE_UNIVERSE_VERSION = "qd-market-wide-investable-universe-1.0.0"


@dataclass(frozen=True)
class MarketWideUniverseConfig:
    research_start: str
    research_end: str
    minimum_history_sessions: int = 120
    liquidity_lookback: int = 20
    minimum_mean_amount_cny: float = 10_000_000.0
    small_size_fraction: float = 0.30
    mid_size_fraction: float = 0.40
    research_names_per_size_bucket: int = 400
    screening_names_per_size_bucket: int = 100
    allowed_missing_fundamental_dates: tuple[str, ...] = ()


@dataclass(frozen=True)
class DailyMarketWideMembership:
    decision_date: str
    decision_at: str
    eligible_candidates: int
    entries: tuple[str, ...]
    exits: tuple[str, ...]
    turnover_rate: float
    exclusions: dict[str, int]
    members: tuple[str, ...]
    top50: tuple[str, ...]
    top300: tuple[str, ...]
    research_members: tuple[str, ...]
    screening_members: tuple[str, ...]
    size_buckets: dict[str, tuple[str, ...]]
    liquidity_buckets: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class MarketWideUniverseReport:
    method_version: str
    source_snapshot_sha256: str
    research_start: str
    research_end: str
    configuration: MarketWideUniverseConfig
    sessions: int
    unique_members: int
    mean_eligible: float
    minimum_eligible: int
    maximum_eligible: int
    mean_turnover_rate: float
    mean_top50_share: float
    mean_top300_share: float
    mean_research_members: float
    mean_screening_members: float
    exact_fundamental_matches: int
    omitted_fundamental_dates: tuple[str, ...]
    memberships: tuple[DailyMarketWideMembership, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str = "en") -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        lines = [
            "# QD 全市场可投资股票池" if zh else "# QD market-wide investable universe",
            "",
            f"- {'方法' if zh else 'Method'}: `{self.method_version}`",
            f"- Snapshot: `{self.source_snapshot_sha256}`",
            f"- {'研究区间' if zh else 'Research dates'}: {self.research_start} to {self.research_end}",
            f"- {'决策日' if zh else 'Decision sessions'}: {self.sessions}",
            f"- {'唯一成员' if zh else 'Unique members'}: {self.unique_members}",
            f"- {'日均合格股票' if zh else 'Mean eligible names'}: {self.mean_eligible:.2f}",
            f"- {'合格范围' if zh else 'Eligible range'}: {self.minimum_eligible}–{self.maximum_eligible}",
            f"- {'Top50占比' if zh else 'Mean Top50 share'}: {self.mean_top50_share:.2%}",
            f"- {'Top300占比' if zh else 'Mean Top300 share'}: {self.mean_top300_share:.2%}",
            f"- {'日均平衡研究面板' if zh else 'Mean balanced research panel'}: {self.mean_research_members:.2f}",
            f"- {'日均候选筛选面板' if zh else 'Mean candidate screening panel'}: {self.mean_screening_members:.2f}",
            f"- {'平均单边成员换手' if zh else 'Mean one-way membership turnover'}: {self.mean_turnover_rate:.4%}",
            (
                f"- {'明确跳过的基本面日期' if zh else 'Explicitly omitted fundamental dates'}: "
                f"{', '.join(self.omitted_fundamental_dates) or ('无' if zh else 'none')}"
            ),
            "",
        ]
        return "\n".join(lines)


@dataclass(frozen=True)
class MarketWideUniverseArtifacts:
    json_path: Path
    zh_markdown_path: Path
    en_markdown_path: Path
    membership_jsonl_path: Path
    membership_jsonl_sha256: str
    research_membership_jsonl_path: Path
    research_membership_jsonl_sha256: str
    research_tiers_jsonl_path: Path
    research_tiers_jsonl_sha256: str
    screening_membership_jsonl_path: Path
    screening_membership_jsonl_sha256: str


def _bucket_members(
    eligible: list[tuple[str, float, float]],
    *,
    small_fraction: float,
    mid_fraction: float,
) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
    count = len(eligible)
    size_small_end = int(count * small_fraction)
    size_mid_end = int(count * (small_fraction + mid_fraction))
    by_size = sorted(eligible, key=lambda item: (item[2], item[0]))
    size = {
        "small": tuple(item[0] for item in by_size[:size_small_end]),
        "mid": tuple(item[0] for item in by_size[size_small_end:size_mid_end]),
        "large": tuple(item[0] for item in by_size[size_mid_end:]),
    }
    low_end = count // 3
    mid_end = (2 * count) // 3
    by_liquidity = sorted(eligible, key=lambda item: (item[1], item[0]))
    liquidity = {
        "low": tuple(item[0] for item in by_liquidity[:low_end]),
        "mid": tuple(item[0] for item in by_liquidity[low_end:mid_end]),
        "high": tuple(item[0] for item in by_liquidity[mid_end:]),
    }
    return size, liquidity


def build_market_wide_universe(
    daily_dir: str | Path,
    fundamental_dir: str | Path,
    config: MarketWideUniverseConfig,
) -> MarketWideUniverseReport:
    if config.minimum_history_sessions < 1 or config.liquidity_lookback < 1:
        raise QmtDataError("market-wide universe history counts must be positive")
    if config.research_names_per_size_bucket < 1:
        raise QmtDataError("research_names_per_size_bucket must be positive")
    if not 1 <= config.screening_names_per_size_bucket <= config.research_names_per_size_bucket:
        raise QmtDataError("screening panel must be positive and no larger than research panel")
    if config.minimum_mean_amount_cny < 0:
        raise QmtDataError("minimum_mean_amount_cny cannot be negative")
    if not 0 < config.small_size_fraction < 1 or not 0 < config.mid_size_fraction < 1:
        raise QmtDataError("size fractions must be between zero and one")
    if config.small_size_fraction + config.mid_size_fraction >= 1:
        raise QmtDataError("small and mid size fractions must leave a large-cap bucket")
    if len(set(config.allowed_missing_fundamental_dates)) != len(
        config.allowed_missing_fundamental_dates
    ):
        raise QmtDataError("allowed missing fundamental dates must be unique")
    try:
        start = date.fromisoformat(config.research_start)
        end = date.fromisoformat(config.research_end)
        allowed_missing = {
            date.fromisoformat(item) for item in config.allowed_missing_fundamental_dates
        }
    except ValueError as exc:
        raise QmtDataError("market-wide universe dates must be ISO dates") from exc
    if start > end:
        raise QmtDataError("research_start must not be after research_end")
    if any(item < start or item > end for item in allowed_missing):
        raise QmtDataError("allowed missing fundamental dates must fall inside the research window")

    daily_root = Path(daily_dir).expanduser().resolve()
    fundamental_root = Path(fundamental_dir).expanduser().resolve()
    daily = _partitions(daily_root)
    fundamentals = dict(_partitions(fundamental_root))
    research_positions = [index for index, (day, _) in enumerate(daily) if start <= day <= end]
    if not research_positions:
        raise QmtDataError("market-wide universe research window contains no daily partitions")
    first_position = research_positions[0]
    history_width = max(config.minimum_history_sessions, config.liquidity_lookback) - 1
    selected_daily = daily[max(first_position - history_width, 0) : research_positions[-1] + 1]
    research_daily = [(day, path) for day, path in selected_daily if day >= start]
    missing_fundamental = [
        day for day, _ in research_daily if day not in fundamentals and day not in allowed_missing
    ]
    if missing_fundamental:
        raise QmtDataError(f"missing exact same-day fundamental snapshots: {missing_fundamental[:3]}")
    fundamental_files = [fundamentals[day] for day, _ in research_daily if day in fundamentals]
    common_root = Path(os.path.commonpath((daily_root, fundamental_root)))
    snapshot = build_selected_files_snapshot_manifest(
        common_root, tuple(path for _, path in selected_daily) + tuple(fundamental_files)
    )

    observation_count: dict[str, int] = defaultdict(int)
    amount_history: dict[str, deque[float]] = defaultdict(
        lambda: deque(maxlen=config.liquidity_lookback)
    )
    memberships: list[DailyMarketWideMembership] = []
    previous: set[str] = set()
    unique_members: set[str] = set()
    for day, daily_path in selected_daily:
        omit_fundamental = day in allowed_missing
        metadata = (
            _listing_metadata(fundamentals[day]) if day >= start and not omit_fundamental else {}
        )
        reader: csv.DictReader = _reader(daily_path)
        required = {"代码", "名称", "成交量(手)", "成交额(千元)", "总市值(万元)"}
        if not reader.fieldnames or not required <= set(reader.fieldnames):
            raise QmtDataError(f"{daily_path.name}: missing market-wide universe columns")
        rows: list[tuple[str, str, float, float, float]] = []
        for row_number, row in enumerate(reader, start=2):
            instrument = (row.get("代码") or "").strip().upper()
            name = (row.get("名称") or "").strip().upper()
            try:
                volume = float((row.get("成交量(手)") or "0").strip())
                amount = float((row.get("成交额(千元)") or "0").strip()) * 1000
                market_cap = float((row.get("总市值(万元)") or "0").strip()) * 10_000
            except ValueError as exc:
                raise QmtDataError(
                    f"{daily_path.name} row {row_number}: invalid market-wide numeric value"
                ) from exc
            rows.append((instrument, name, volume, amount, market_cap))
            if _is_a_share(instrument) and volume > 0 and amount > 0:
                observation_count[instrument] += 1
                amount_history[instrument].append(amount)
        if day < start:
            continue
        if omit_fundamental:
            continue

        exclusions: dict[str, int] = defaultdict(int)
        eligible: list[tuple[str, float, float]] = []
        for instrument, name, volume, amount, market_cap in rows:
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
            if not math.isfinite(market_cap) or market_cap <= 0:
                exclusions["invalid_market_cap"] += 1
                continue
            eligible.append((instrument, mean_amount, market_cap))

        ranked = sorted(eligible, key=lambda item: (-item[1], item[0]))
        members = tuple(item[0] for item in ranked)
        size_buckets, liquidity_buckets = _bucket_members(
            eligible,
            small_fraction=config.small_size_fraction,
            mid_fraction=config.mid_size_fraction,
        )
        research_members = tuple(
            instrument
            for bucket in ("large", "mid", "small")
            for instrument in sorted(
                size_buckets[bucket],
                key=lambda item: (hashlib.sha256(item.encode()).hexdigest(), item),
            )[: config.research_names_per_size_bucket]
        )
        size_sets = {bucket: set(members) for bucket, members in size_buckets.items()}
        research_by_bucket = {
            bucket: tuple(
                instrument
                for instrument in research_members
                if instrument in size_sets[bucket]
            )
            for bucket in ("large", "mid", "small")
        }
        screening_members = tuple(
            instrument
            for bucket in ("large", "mid", "small")
            for instrument in research_by_bucket[bucket][
                : config.screening_names_per_size_bucket
            ]
        )
        current = set(members)
        entries = tuple(sorted(current - previous))
        exits = tuple(sorted(previous - current))
        denominator = max(len(previous), len(current), 1)
        turnover = (len(entries) + len(exits)) / (2 * denominator) if memberships else 0.0
        memberships.append(
            DailyMarketWideMembership(
                decision_date=day.isoformat(),
                decision_at=f"{day.isoformat()}T15:01:00+08:00",
                eligible_candidates=len(eligible),
                entries=entries,
                exits=exits,
                turnover_rate=turnover,
                exclusions=dict(sorted(exclusions.items())),
                members=members,
                top50=members[:50],
                top300=members[:300],
                research_members=research_members,
                screening_members=screening_members,
                size_buckets=size_buckets,
                liquidity_buckets=liquidity_buckets,
            )
        )
        previous = current
        unique_members.update(current)

    if not memberships:
        raise QmtDataError("market-wide universe produced no decision sessions")
    counts = [item.eligible_candidates for item in memberships]
    return MarketWideUniverseReport(
        method_version=MARKET_WIDE_UNIVERSE_VERSION,
        source_snapshot_sha256=snapshot.snapshot_sha256,
        research_start=start.isoformat(),
        research_end=end.isoformat(),
        configuration=config,
        sessions=len(memberships),
        unique_members=len(unique_members),
        mean_eligible=sum(counts) / len(counts),
        minimum_eligible=min(counts),
        maximum_eligible=max(counts),
        mean_turnover_rate=sum(item.turnover_rate for item in memberships) / len(memberships),
        mean_top50_share=sum(min(50, item.eligible_candidates) / item.eligible_candidates for item in memberships) / len(memberships),
        mean_top300_share=sum(min(300, item.eligible_candidates) / item.eligible_candidates for item in memberships) / len(memberships),
        mean_research_members=sum(len(item.research_members) for item in memberships)
        / len(memberships),
        mean_screening_members=sum(len(item.screening_members) for item in memberships)
        / len(memberships),
        exact_fundamental_matches=len(memberships),
        omitted_fundamental_dates=tuple(sorted(item.isoformat() for item in allowed_missing)),
        memberships=tuple(memberships),
    )


def _write(path: Path, content: str) -> str:
    path.write_text(content, encoding="utf-8", newline="\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _research_tier_payload(item: DailyMarketWideMembership) -> dict[str, object]:
    research = set(item.research_members)
    return {
        "decision_date": item.decision_date,
        "size_buckets": {
            bucket: tuple(instrument for instrument in members if instrument in research)
            for bucket, members in item.size_buckets.items()
        },
        "liquidity_buckets": {
            bucket: tuple(instrument for instrument in members if instrument in research)
            for bucket, members in item.liquidity_buckets.items()
        },
    }


def write_market_wide_universe(
    report: MarketWideUniverseReport, output_dir: str | Path
) -> MarketWideUniverseArtifacts:
    directory = Path(output_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "market-wide-universe.json"
    zh_path = directory / "market-wide-universe.zh.md"
    en_path = directory / "market-wide-universe.en.md"
    membership_path = directory / "market-wide-membership.jsonl"
    research_membership_path = directory / "market-wide-research-membership.jsonl"
    research_tiers_path = directory / "market-wide-research-tiers.jsonl"
    screening_membership_path = directory / "market-wide-screening-membership.jsonl"
    _write(json_path, report.to_json() + "\n")
    _write(zh_path, report.to_markdown("zh") + "\n")
    _write(en_path, report.to_markdown("en") + "\n")
    membership_content = "".join(
        json.dumps(asdict(item), sort_keys=True, ensure_ascii=False) + "\n"
        for item in report.memberships
    )
    membership_sha = _write(membership_path, membership_content)
    research_membership_content = "".join(
        json.dumps(
            {
                "decision_date": item.decision_date,
                "decision_at": item.decision_at,
                "members": item.research_members,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
        for item in report.memberships
    )
    research_membership_sha = _write(
        research_membership_path, research_membership_content
    )
    research_tiers_content = "".join(
        json.dumps(
            _research_tier_payload(item),
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
        for item in report.memberships
    )
    research_tiers_sha = _write(research_tiers_path, research_tiers_content)
    screening_membership_content = "".join(
        json.dumps(
            {
                "decision_date": item.decision_date,
                "decision_at": item.decision_at,
                "members": item.screening_members,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
        for item in report.memberships
    )
    screening_membership_sha = _write(
        screening_membership_path, screening_membership_content
    )
    return MarketWideUniverseArtifacts(
        json_path,
        zh_path,
        en_path,
        membership_path,
        membership_sha,
        research_membership_path,
        research_membership_sha,
        research_tiers_path,
        research_tiers_sha,
        screening_membership_path,
        screening_membership_sha,
    )
