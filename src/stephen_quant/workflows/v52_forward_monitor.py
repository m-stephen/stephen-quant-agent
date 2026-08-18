from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

V52_VERSION = "v5.2-frozen-forward-monitor-1.0.0"
FREEZE_THROUGH = "2026-08-16"
FROZEN_LINES = (
    "raw_chip_flow_equal_rank",
    "style_residual_chip_flow_equal_rank",
    "flow_price_divergence_20_20d_only",
)
_DATE_NAME = re.compile(r"^(?P<year>\d{4})[-_]?(?P<month>\d{2})[-_]?(?P<day>\d{2})$")


@dataclass(frozen=True)
class V52ForwardConfig:
    freeze_through: str = FREEZE_THROUGH
    early_sessions: int = 25
    preliminary_sessions: int = 60
    decision_sessions: int = 120
    breadth: int = 50
    horizon: int = 20
    nav: float = 3_000_000.0
    minimum_dsr: float = 0.95
    maximum_pbo: float = 0.05
    maximum_placebo_p: float = 0.05

    def validate(self) -> None:
        if self.freeze_through != FREEZE_THROUGH:
            raise ValueError("V5.2 freeze date is immutable")
        if (self.early_sessions, self.preliminary_sessions, self.decision_sessions) != (
            25,
            60,
            120,
        ):
            raise ValueError("V5.2 forward checkpoints are frozen")
        if (self.breadth, self.horizon, self.nav) != (50, 20, 3_000_000.0):
            raise ValueError("V5.2 portfolio definition is frozen")
        if (self.minimum_dsr, self.maximum_pbo, self.maximum_placebo_p) != (
            0.95,
            0.05,
            0.05,
        ):
            raise ValueError("V5.2 Alpha Court gates are frozen")


@dataclass(frozen=True)
class ForwardSourceCoverage:
    source: str
    latest_partition: str | None
    new_partitions: int
    inventory_sha256: str


@dataclass(frozen=True)
class V52ForwardReport:
    method_version: str
    as_of: str
    protocol_sha256: str
    freeze_through: str
    frozen_lines: tuple[str, ...]
    source_coverage: tuple[ForwardSourceCoverage, ...]
    common_new_sessions: int
    latest_common_session: str | None
    checkpoint: str
    membership_ready: bool
    performance_trials: int
    cumulative_trial_count: int
    decision: str
    blockers: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        lines = [
            "# V5.2 冻结候选前向监控报告" if zh else "# V5.2 Frozen Candidate Forward Monitor",
            "",
            f"**{'结论' if zh else 'Decision'}: `{self.decision}`**",
            "",
            f"- {'检查日期' if zh else 'As of'}: {self.as_of}",
            f"- {'冻结截止日' if zh else 'Frozen through'}: {self.freeze_through}",
            f"- {'新增共同交易日' if zh else 'New common sessions'}: {self.common_new_sessions}",
            f"- {'当前检查点' if zh else 'Checkpoint'}: {self.checkpoint}",
            f"- {'性能 Trials' if zh else 'Performance Trials'}: {self.performance_trials}",
            "",
            "| Source | Latest partition | New partitions | Inventory SHA-256 |",
            "|---|---|---:|---|",
        ]
        for item in self.source_coverage:
            lines.append(
                f"| {item.source} | {item.latest_partition or 'N/A'} | "
                f"{item.new_partitions} | `{item.inventory_sha256}` |"
            )
        lines.extend(
            [
                "",
                f"- {'冻结观察线' if zh else 'Frozen lines'}: {', '.join(self.frozen_lines)}",
                f"- {'阻断项' if zh else 'Blockers'}: {', '.join(self.blockers) or 'none'}",
                "",
                (
                    "数据不足时不会创建收益 Trial，也不会用冻结日前的数据替代前向证据。"
                    if zh
                    else "No performance Trial is created while coverage is insufficient, and pre-freeze data never substitutes for forward evidence."
                ),
            ]
        )
        return "\n".join(lines) + "\n"


def _partition_date(path: Path) -> str | None:
    match = _DATE_NAME.fullmatch(path.stem)
    if match is None:
        return None
    value = f"{match['year']}-{match['month']}-{match['day']}"
    try:
        date.fromisoformat(value)
    except ValueError:
        return None
    return value


def _inventory(
    root: str | Path, *, freeze_through: str, as_of: str
) -> tuple[set[str], ForwardSourceCoverage]:
    directory = Path(root).expanduser().resolve()
    if not directory.is_dir():
        raise ValueError(f"V5.2 source directory does not exist: {directory}")
    rows: list[tuple[str, int]] = []
    all_dates: set[str] = set()
    new_dates: set[str] = set()
    for path in sorted(directory.rglob("*.csv")):
        day = _partition_date(path)
        if day is None or day > as_of:
            continue
        rows.append((path.relative_to(directory).as_posix(), path.stat().st_size))
        all_dates.add(day)
        if day > freeze_through:
            new_dates.add(day)
    digest = hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return new_dates, ForwardSourceCoverage(
        "",
        max(all_dates) if all_dates else None,
        len(new_dates),
        digest,
    )


def _membership_dates(path: str | Path) -> set[str]:
    dates = set()
    for number, line in enumerate(
        Path(path).expanduser().resolve().read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        payload = json.loads(line)
        day = str(payload.get("decision_date", ""))
        date.fromisoformat(day)
        if day in dates:
            raise ValueError(f"duplicate V5.2 membership date at line {number}")
        dates.add(day)
    return dates


def run_v52_forward_monitor(
    daily_dir: str | Path,
    fund_flow_dir: str | Path,
    chip_dir: str | Path,
    *,
    membership_path: str | Path | None,
    output_dir: str | Path,
    as_of: str | None = None,
    config: V52ForwardConfig | None = None,
    prior_inferential_trials: int = 1218,
) -> V52ForwardReport:
    config = config or V52ForwardConfig()
    config.validate()
    if prior_inferential_trials < 1218:
        raise ValueError("V5.2 cannot discard the 1,218 pre-existing Trials")
    as_of = as_of or datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    date.fromisoformat(as_of)
    if as_of <= config.freeze_through:
        raise ValueError("V5.2 as-of must be after the freeze date")
    inventories: dict[str, set[str]] = {}
    coverage = []
    for source, root in (
        ("qd_daily", daily_dir),
        ("qd_fund_flow", fund_flow_dir),
        ("qd_chip", chip_dir),
    ):
        dates, item = _inventory(root, freeze_through=config.freeze_through, as_of=as_of)
        inventories[source] = dates
        coverage.append(
            ForwardSourceCoverage(
                source,
                item.latest_partition,
                item.new_partitions,
                item.inventory_sha256,
            )
        )
    common = set.intersection(*inventories.values())
    count = len(common)
    if count < config.early_sessions:
        checkpoint = "WAITING"
    elif count < config.preliminary_sessions:
        checkpoint = "EARLY_WARNING"
    elif count < config.decision_sessions:
        checkpoint = "PRELIMINARY"
    else:
        checkpoint = "DECISION_ELIGIBLE"
    membership_ready = True
    blockers: list[str] = []
    if count < config.early_sessions:
        blockers.append("fewer_than_25_new_common_sessions")
    elif membership_path is None:
        membership_ready = False
        blockers.append("forward_membership_not_configured")
    else:
        membership = _membership_dates(membership_path)
        missing = common - membership
        if missing:
            membership_ready = False
            blockers.append("forward_membership_missing_common_dates")
    decision = (
        "WAITING_FOR_DATA"
        if count < config.early_sessions
        else "READY_FOR_FROZEN_FORWARD_RUN"
        if membership_ready
        else "BLOCKED_BY_MEMBERSHIP"
    )
    protocol_payload = {
        "config": asdict(config),
        "frozen_lines": FROZEN_LINES,
        "method_version": V52_VERSION,
    }
    protocol_sha = hashlib.sha256(
        json.dumps(protocol_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    report = V52ForwardReport(
        V52_VERSION,
        as_of,
        protocol_sha,
        config.freeze_through,
        FROZEN_LINES,
        tuple(coverage),
        count,
        max(common) if common else None,
        checkpoint,
        membership_ready,
        0,
        prior_inferential_trials,
        decision,
        tuple(blockers),
    )
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "v5.2-forward-monitor.json").write_text(report.to_json() + "\n", encoding="utf-8")
    for language in ("zh", "en"):
        (output / f"v5.2-forward-monitor.{language}.md").write_text(
            report.to_markdown(language), encoding="utf-8"
        )
    return report
