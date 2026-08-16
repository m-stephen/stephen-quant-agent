from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from itertools import pairwise
from pathlib import Path
from statistics import stdev

from stephen_quant.baseline import (
    StatefulBar,
    StatefulExecutionConfig,
    StatefulExecutionReport,
    TargetAllocation,
    run_stateful_execution,
    write_stateful_execution_report,
)
from stephen_quant.factors import FactorError, build_seed_registry, compute_factor
from stephen_quant.integrity import ExperimentRegistry
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.snapshot import build_selected_files_snapshot_manifest
from stephen_quant.qmt import load_qd_daily_directory, select_qd_daily_files
from stephen_quant.qmt.csv_adapter import _decode

DYNAMIC_BACKTEST_VERSION = "qd-dynamic-stateful-backtest-1.0.0"


@dataclass(frozen=True)
class DynamicBacktestConfig:
    data_start: str
    research_start: str
    research_end: str
    validation_start: str
    validation_end: str
    test_start: str
    test_end: str
    factor_id: str = "mom_120_skip_20"
    factor_version: str = "1.0.0"
    top_k: int = 20
    rebalance_every: int = 5
    cash_reserve: float = 0.02
    maximum_position_weight: float = 0.05
    adv_lookback: int = 20
    max_participation_rate: float = 0.05
    commission_bps: float = 3.0
    sell_tax_bps: float = 5.0
    slippage_bps: float = 5.0
    stale_writeoff_sessions: int = 20
    initial_nav: float = 1_000_000.0
    seed: int = 42


@dataclass(frozen=True)
class DynamicBenchmarkSummary:
    name: str
    source_sha256: str
    periods: int
    total_return: float
    annualized_return: float
    annualized_volatility: float | None
    sharpe: float | None
    max_drawdown: float
    strategy_excess_total_return: float


@dataclass(frozen=True)
class DynamicBacktestReport:
    method_version: str
    snapshot_id: str
    experiment_id: str
    trial_id: str
    trial_number: int
    membership_sha256: str
    factor_key: str
    research_start: str
    research_end: str
    membership_sessions: int
    execution_sessions: int
    unique_members: int
    signal_failures: int
    benchmark: DynamicBenchmarkSummary
    execution: StatefulExecutionReport
    decision: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self) -> str:
        metrics = self.execution.metrics
        return "\n".join(
            (
                "# V1.8.13 dynamic-universe engineering backtest",
                "",
                f"**Decision: {self.decision}**",
                "",
                f"- Experiment: `{self.experiment_id}`",
                f"- Trial: `{self.trial_id}`",
                f"- Snapshot: `{self.snapshot_id}`",
                f"- Membership SHA-256: `{self.membership_sha256}`",
                f"- Factor fixture: `{self.factor_key}`",
                f"- Execution sessions: {self.execution_sessions}",
                f"- Unique dynamic members: {self.unique_members}",
                f"- Signal failures: {self.signal_failures}",
                f"- Strategy net return: {metrics.net_total_return:.6%}",
                f"- Strategy maximum drawdown: {metrics.max_drawdown:.6%}",
                f"- Total cost: {metrics.total_cost:.2f}",
                f"- Blocked orders: {metrics.blocked_orders}",
                f"- Stale position-days: {metrics.stale_position_days}",
                f"- Write-off events: {metrics.writeoff_events}",
                f"- Benchmark: {self.benchmark.name}",
                f"- Benchmark return: {self.benchmark.total_return:.6%}",
                f"- Strategy excess return: {self.benchmark.strategy_excess_total_return:.6%}",
                "",
                "This is an in-research-window engineering result, not independent alpha evidence.",
                "",
            )
        )


@dataclass(frozen=True)
class DynamicBacktestRun:
    report: DynamicBacktestReport
    output_dir: Path
    report_json_path: Path
    report_markdown_path: Path
    targets_jsonl_path: Path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, content: str) -> str:
    path.write_text(content, encoding="utf-8", newline="\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _read_memberships(path: Path, start: str, end: str) -> list[dict[str, object]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    selected = [row for row in rows if start <= str(row["decision_date"]) <= end]
    dates = [str(row["decision_date"]) for row in selected]
    if not selected or dates != sorted(dates) or len(set(dates)) != len(dates):
        raise ValueError("membership JSONL must contain unique chronological research dates")
    if dates[0] != start or dates[-1] != end:
        raise ValueError("membership JSONL does not cover the declared research boundaries")
    return selected


def _benchmark(
    path: Path,
    report: StatefulExecutionReport,
    *,
    name: str,
) -> DynamicBenchmarkSummary:
    raw = path.read_bytes()
    text, _ = _decode(raw)
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames or not {"日期", "开盘价", "收盘价"} <= set(reader.fieldnames):
        raise ValueError("benchmark must contain 日期, 开盘价, and 收盘价")
    prices: dict[str, tuple[float, float]] = {}
    for row in reader:
        raw_day = (row.get("日期") or "").strip()
        day = f"{raw_day[:4]}-{raw_day[4:6]}-{raw_day[6:8]}" if len(raw_day) == 8 else raw_day
        opening = (row.get("开盘价") or "").strip()
        close = (row.get("收盘价") or "").strip()
        if opening and close:
            prices[day] = (float(opening), float(close))
    returns: list[float] = []
    previous_close = None
    for period in report.periods:
        if period.trade_date not in prices:
            raise ValueError(f"benchmark is missing {period.trade_date}")
        opening, close = prices[period.trade_date]
        returns.append(close / (previous_close if previous_close is not None else opening) - 1)
        previous_close = close
    total = math.prod(1 + value for value in returns) - 1
    annualized = (1 + total) ** (252 / len(returns)) - 1
    volatility = stdev(returns) * math.sqrt(252) if len(returns) > 1 else None
    sharpe = None
    if volatility not in {None, 0.0}:
        sharpe = sum(returns) / len(returns) / stdev(returns) * math.sqrt(252)
    nav = peak = 1.0
    drawdown = 0.0
    for value in returns:
        nav *= 1 + value
        peak = max(peak, nav)
        drawdown = min(drawdown, nav / peak - 1)
    return DynamicBenchmarkSummary(
        name=name,
        source_sha256=hashlib.sha256(raw).hexdigest(),
        periods=len(returns),
        total_return=total,
        annualized_return=annualized,
        annualized_volatility=volatility,
        sharpe=sharpe,
        max_drawdown=drawdown,
        strategy_excess_total_return=report.metrics.net_total_return - total,
    )


def run_dynamic_stateful_backtest(
    daily_dir: str | Path,
    membership_jsonl: str | Path,
    benchmark_csv: str | Path,
    *,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    config: DynamicBacktestConfig,
    code_version: str,
) -> DynamicBacktestRun:
    if not (
        config.data_start <= config.research_start <= config.research_end
        < config.validation_start <= config.validation_end
        < config.test_start <= config.test_end
    ):
        raise ValueError("dynamic backtest date reservations must be strictly ordered")
    if config.top_k < 1 or config.rebalance_every < 1 or config.adv_lookback < 1:
        raise ValueError("dynamic backtest counts must be positive")
    membership_path = Path(membership_jsonl).expanduser().resolve()
    benchmark_path = Path(benchmark_csv).expanduser().resolve()
    daily_root = Path(daily_dir).expanduser().resolve()
    if not membership_path.is_file() or not benchmark_path.is_file():
        raise ValueError("membership and benchmark files must exist")
    memberships = _read_memberships(
        membership_path, config.research_start, config.research_end
    )
    membership_sha = _sha256(membership_path)
    union = tuple(
        sorted({str(item) for row in memberships for item in row["members"]})
    )
    selected_files = select_qd_daily_files(
        daily_root, start_date=config.data_start, end_date=config.research_end
    )
    manifest = build_selected_files_snapshot_manifest(daily_root, selected_files)
    snapshot_id = registry.register_snapshot(
        manifest,
        vendor_version="QD date-partitioned A-share daily CSV / back_ratio",
        notes="V1.8.13 research window only; dynamic membership is separately hashed.",
    )
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            name="qd_v1_8_13_dynamic_stateful_engineering",
            hypothesis=(
                "The frozen rejected momentum fixture can execute end-to-end on the point-in-time "
                "dynamic universe without sparse-panel accounting violations."
            ),
            dataset_snapshot_id=snapshot_id,
            code_version=code_version,
            search_space=json.dumps(
                {"factor": f"{config.factor_id}@{config.factor_version}", "variants": 1},
                separators=(",", ":"),
                sort_keys=True,
            ),
        )
    )
    trial_id, trial_number = registry.create_trial(
        TrialSpec(
            experiment_id=experiment_id,
            model_name="dynamic_stateful_topk_engineering",
            factor_set=f"{config.factor_id}@{config.factor_version}",
            hyperparams=json.dumps(asdict(config), separators=(",", ":"), sort_keys=True),
            seed=config.seed,
            train_start=config.research_start,
            train_end=config.research_end,
            validation_start=config.validation_start,
            validation_end=config.validation_end,
            test_start=config.test_start,
            test_end=config.test_end,
        )
    )

    try:
        dataset = load_qd_daily_directory(
            daily_root,
            start_date=config.data_start,
            end_date=config.research_end,
            instruments=union,
            adjustment="back_ratio",
        )
        by_instrument: dict[str, list[object]] = defaultdict(list)
        bars_by_date: dict[str, dict[str, object]] = defaultdict(dict)
        for bar in dataset.bars:
            by_instrument[bar.instrument].append(bar)
            bars_by_date[bar.trade_date][bar.instrument] = bar
        indexes = {
            instrument: {bar.trade_date: index for index, bar in enumerate(bars)}
            for instrument, bars in by_instrument.items()
        }
        definition = build_seed_registry().get(config.factor_id, config.factor_version)
        factor_data = {
            instrument: {
                field: [getattr(bar, field) for bar in bars]
                for field in definition.required_fields
            }
            for instrument, bars in by_instrument.items()
        }
        factor_availability = {
            instrument: {
                field: [f"{bar.trade_date}T15:01:00+08:00" for bar in bars]
                for field in definition.required_fields
            }
            for instrument, bars in by_instrument.items()
        }
        observation_times = {
            instrument: [f"{bar.trade_date}T15:00:00+08:00" for bar in bars]
            for instrument, bars in by_instrument.items()
        }
        sessions: list[tuple[StatefulBar, ...]] = []
        targets: list[TargetAllocation] = []
        target_audit: list[dict[str, object]] = []
        ever_targeted: set[str] = set()
        signal_failures = 0
        weight = min(
            (1 - config.cash_reserve) / config.top_k,
            config.maximum_position_weight,
        )
        for period_index, (decision_row, next_row) in enumerate(
            pairwise(memberships)
        ):
            decision_date = str(decision_row["decision_date"])
            execution_date = str(next_row["decision_date"])
            members = {str(item) for item in decision_row["members"]}
            rebalance = period_index % config.rebalance_every == 0
            selected: tuple[str, ...] = ()
            candidate_signals = 0
            if rebalance:
                signals: list[tuple[str, float]] = []
                for instrument in sorted(members):
                    as_of_index = indexes[instrument].get(decision_date)
                    if as_of_index is None:
                        signal_failures += 1
                        continue
                    try:
                        signal = compute_factor(
                            definition,
                            factor_data[instrument],
                            factor_availability[instrument],
                            as_of_index=as_of_index,
                            observation_times=observation_times[instrument],
                            decision_at=f"{execution_date}T09:30:00+08:00",
                        )
                    except FactorError:
                        signal_failures += 1
                        continue
                    signals.append((instrument, definition.direction * signal.value))
                candidate_signals = len(signals)
                if len(signals) < config.top_k:
                    raise ValueError(
                        f"{decision_date} has only {len(signals)} valid factor signals"
                    )
                selected = tuple(
                    instrument
                    for instrument, _ in sorted(signals, key=lambda item: (-item[1], item[0]))[
                        : config.top_k
                    ]
                )
                ever_targeted.update(selected)
            forced_exits = tuple(sorted(ever_targeted - members))
            target_weights = {instrument: weight for instrument in selected}

            stateful_bars: list[StatefulBar] = []
            for instrument in sorted(set(selected) | ever_targeted):
                bar = bars_by_date.get(execution_date, {}).get(instrument)
                if bar is None:
                    continue
                bars = by_instrument[instrument]
                execution_index = indexes[instrument][execution_date]
                history = bars[max(0, execution_index - config.adv_lookback) : execution_index]
                if not history:
                    continue
                capacity = (
                    sum(item.amount for item in history) / len(history)
                    * config.max_participation_rate
                )
                stateful_bars.append(
                    StatefulBar(
                        trade_date=execution_date,
                        instrument=instrument,
                        open_price=bar.open,
                        close_price=bar.close,
                        capacity_cny=capacity,
                        capacity_available_at=f"{history[-1].trade_date}T15:01:00+08:00",
                        can_buy_open=bar.can_buy_open,
                        can_sell_open=bar.can_sell_open,
                        tradability_reason=bar.tradability_reason,
                    )
                )
            if not stateful_bars:
                raise ValueError(f"{execution_date} has no executable sparse-panel bars")
            sessions.append(tuple(stateful_bars))
            targets.append(
                TargetAllocation(
                    trade_date=execution_date,
                    decided_at=f"{decision_date}T15:01:00+08:00",
                    weights=target_weights,
                    rebalance=rebalance,
                    forced_exits=forced_exits,
                )
            )
            target_audit.append(
                {
                    "decision_date": decision_date,
                    "execution_date": execution_date,
                    "rebalance": rebalance,
                    "members": len(members),
                    "candidate_signals": candidate_signals,
                    "selected": selected,
                    "forced_exits": forced_exits,
                }
            )

        execution = run_stateful_execution(
            tuple(sessions),
            tuple(targets),
            StatefulExecutionConfig(
                maximum_position_weight=config.maximum_position_weight,
                commission_bps=config.commission_bps,
                sell_tax_bps=config.sell_tax_bps,
                slippage_bps=config.slippage_bps,
                stale_writeoff_sessions=config.stale_writeoff_sessions,
            ),
            initial_nav=config.initial_nav,
        )
        benchmark = _benchmark(benchmark_path, execution, name="沪深300")
        report = DynamicBacktestReport(
            method_version=DYNAMIC_BACKTEST_VERSION,
            snapshot_id=snapshot_id,
            experiment_id=experiment_id,
            trial_id=trial_id,
            trial_number=trial_number,
            membership_sha256=membership_sha,
            factor_key=definition.key,
            research_start=config.research_start,
            research_end=config.research_end,
            membership_sessions=len(memberships),
            execution_sessions=len(sessions),
            unique_members=len(union),
            signal_failures=signal_failures,
            benchmark=benchmark,
            execution=execution,
            decision="ENGINEERING_COMPLETE_NO_ALPHA_CLAIM",
        )
        directory = Path(output_dir).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
        report_json_path = directory / "dynamic-backtest.json"
        report_markdown_path = directory / "dynamic-backtest.md"
        targets_jsonl_path = directory / "dynamic-targets.jsonl"
        report_json_sha = _write(report_json_path, report.to_json() + "\n")
        report_markdown_sha = _write(report_markdown_path, report.to_markdown())
        targets_content = "".join(
            json.dumps(item, sort_keys=True, ensure_ascii=False) + "\n"
            for item in target_audit
        )
        targets_sha = _write(targets_jsonl_path, targets_content)
        execution_artifacts = write_stateful_execution_report(execution, directory)
        audit_path = directory / "qd-data-audit.json"
        audit_sha = _write(audit_path, dataset.audit.to_json() + "\n")
        for kind, path, digest in (
            ("dynamic_backtest_json", report_json_path, report_json_sha),
            ("dynamic_backtest_markdown", report_markdown_path, report_markdown_sha),
            ("dynamic_targets_jsonl", targets_jsonl_path, targets_sha),
            ("stateful_execution_json", execution_artifacts.json_path, execution_artifacts.json_sha256),
            ("stateful_execution_markdown", execution_artifacts.markdown_path, execution_artifacts.markdown_sha256),
            ("qd_data_audit", audit_path, audit_sha),
            ("dynamic_membership_jsonl", membership_path, membership_sha),
        ):
            registry.register_artifact(
                trial_id=trial_id, kind=kind, path=str(path), sha256=digest
            )
        registry.record_trial_result(
            trial_id,
            json.dumps(
                {
                    "status": "accepted_engineering",
                    "decision": report.decision,
                    "metrics": asdict(execution.metrics),
                    "benchmark": asdict(benchmark),
                    "report_path": str(report_json_path),
                },
                separators=(",", ":"),
                sort_keys=True,
                ensure_ascii=False,
            ),
        )
        return DynamicBacktestRun(
            report=report,
            output_dir=directory,
            report_json_path=report_json_path,
            report_markdown_path=report_markdown_path,
            targets_jsonl_path=targets_jsonl_path,
        )
    except Exception as exc:
        registry.record_trial_result(
            trial_id,
            json.dumps(
                {"status": "failed_engineering", "error": str(exc)},
                separators=(",", ":"),
                sort_keys=True,
            ),
        )
        raise
