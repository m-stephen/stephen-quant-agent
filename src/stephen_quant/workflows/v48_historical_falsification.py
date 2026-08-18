from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from statistics import mean

from stephen_quant.evaluation import EvaluationObservation
from stephen_quant.falsification import deflated_sharpe_ratio, run_placebo
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import (
    build_composite_snapshot_manifest,
    build_selected_files_snapshot_manifest,
)
from stephen_quant.qmt import (
    DynamicUniverseConfig,
    QdAlternativeConfig,
    QmtDailyBar,
    build_dynamic_universe,
    build_multisource_factor_observations,
    load_qd_alternative_directory,
    load_qd_daily_directory,
    select_qd_daily_files,
    write_dynamic_universe,
)

from .price_discovery_lab import _execution_memberships, _load_memberships
from .v41_semantic_alpha import UsageEvent, UsageSpec, V41Config, _anchors, evaluate_usage_events
from .v46_orthogonal_search import _ensemble_panel
from .v47_low_turnover_alpha import (
    AUCTION_SCHEMA_ID,
    FLOW_SCHEMA_ID,
    GridEvidence,
    TurnoverAttribution,
    _path,
    _selected_schemas,
    evaluate_buffered_avoid_accounting_events,
    evaluate_buffered_avoid_events,
    v46_trial_sharpes,
)
from .v48_portfolio_report import (
    AccountingSummary,
    IndexComparison,
    compare_index,
    summarize_accounting,
)
from .v48_sealed_alpha_court import (
    FROZEN_CANDIDATE_COMMIT,
    _fingerprint,
    _increment_by_day,
    _moments,
    v47_trial_sharpes,
)

V48_HISTORICAL_VERSION = "v4.8-historical-falsification-1.0.0"
HISTORICAL_START = "2020-01-01"
HISTORICAL_END = "2021-12-31"
HISTORICAL_FUNDAMENTAL_OMISSIONS = (
    "2020-01-02",
    "2020-02-20",
    "2020-02-25",
    "2020-03-16",
    "2020-04-23",
    "2020-06-18",
    "2020-07-08",
    "2020-07-20",
    "2020-08-03",
    "2020-08-04",
    "2020-08-24",
    "2020-11-20",
    "2021-01-29",
    "2021-03-16",
)


@dataclass(frozen=True)
class V48HistoricalConfig:
    data_start: str = "2019-01-01"
    test_start: str = HISTORICAL_START
    test_end: str = HISTORICAL_END
    universe_builder_top_n: int = 300
    universe_top_n: int = 50
    minimum_history_sessions: int = 120
    liquidity_lookback: int = 20
    minimum_mean_amount_cny: float = 20_000_000.0
    horizon: int = 20
    breadth: int = 10
    buffer_ranks: int = 10
    nav: float = 3_000_000.0
    commission_bps: float = 3.0
    sell_tax_bps: float = 5.0
    slippage_bps: float = 5.0
    impact_bps: float = 10.0
    participation_rate: float = 0.05
    minimum_positive_paths: int = 15
    minimum_median_path_sharpe: float = 0.0
    maximum_placebo_p: float = 0.05
    minimum_dsr: float = 0.95
    placebo_repetitions: int = 199
    ingested_at: str = "2026-08-18T00:00:00+08:00"
    seed: int = 42

    def validate(self) -> None:
        if (self.test_start, self.test_end) != (HISTORICAL_START, HISTORICAL_END):
            raise ValueError("historical falsification window is frozen to 2020-2021")
        if (self.horizon, self.breadth, self.buffer_ranks) != (20, 10, 10):
            raise ValueError("historical falsification candidate identity is frozen")
        if (self.universe_builder_top_n, self.universe_top_n) != (300, 50):
            raise ValueError("historical universe construction is frozen")
        if self.nav != 3_000_000.0:
            raise ValueError("historical falsification NAV is frozen at CNY 3 million")


@dataclass(frozen=True)
class V48HistoricalReport:
    method_version: str
    candidate_fingerprint: str
    candidate_commit: str
    evidence_classification: str
    experiment_id: str
    snapshot_id: str
    snapshot_sha256: str
    trial_ids: tuple[str, ...]
    recorded_trial_count: int
    universe_source_sha256: str
    membership_sha256: str
    universe_sessions: int
    universe_unique_members: int
    omitted_universe_dates: tuple[str, ...]
    common_source_sessions: int
    standard_account: AccountingSummary
    doubled_account: AccountingSummary
    standard_by_year: tuple[AccountingSummary, ...]
    standard_path: GridEvidence
    doubled_path: GridEvidence
    index_comparisons: tuple[IndexComparison, ...]
    signal_placebo_p: float
    return_placebo_p: float
    dsr_probability: float
    dsr_skewness: float
    dsr_excess_kurtosis: float
    gate_failures: tuple[str, ...]
    decision: str
    limitations: tuple[tuple[str, str], ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        standard = self.standard_account
        lines = [
            "# 冻结疑似 Alpha：2020–2021 回溯证伪" if zh else "# Frozen Suspected Alpha: 2020–2021 Historical Falsification",
            "",
            "## 技术摘要" if zh else "## Technical summary",
            "",
            (
                f"冻结候选在2020–2021标准成本下取得 **{standard.net_total_return:.2%}** 净收益，"
                f"300万元对应 **{standard.net_profit_cny:,.2f}元**；相对同股票池匹配对照的因子增量为 "
                f"**{standard.incremental_vs_matched_control:.2%}**（**{standard.factor_value_add_cny:,.2f}元**）。"
                if zh
                else f"The frozen candidate earned **{standard.net_total_return:.2%}** net in 2020–2021, "
                f"or **CNY {standard.net_profit_cny:,.2f}** on CNY 3 million. Its same-universe matched-control "
                f"increment was **{standard.incremental_vs_matched_control:.2%}** "
                f"(**CNY {standard.factor_value_add_cny:,.2f}**)."
            ),
            "",
            (
                f"结论为 `{self.decision}`。这是发现候选之后进行的反向时间压力测试，不是新的前向样本外 Alpha Court；"
                "任何结果都不得用于修改候选。"
                if zh
                else f"Decision: `{self.decision}`. This is a backward temporal stress test performed after discovery, "
                "not a new forward out-of-sample Alpha Court; no result may be used to modify the candidate."
            ),
            "",
            "## 冻结身份与数据范围" if zh else "## Frozen identity and scope",
            "",
            f"- {'候选指纹' if zh else 'Candidate fingerprint'}: `{self.candidate_fingerprint}`",
            f"- {'测试窗口' if zh else 'Test window'}: {HISTORICAL_START} — {HISTORICAL_END}",
            f"- {'三源共同交易日' if zh else 'Common source sessions'}: {self.common_source_sessions}",
            f"- {'时点股票池决策日' if zh else 'Point-in-time universe sessions'}: {self.universe_sessions}",
            f"- {'隔离的基本面缺口日' if zh else 'Quarantined fundamental dates'}: {len(self.omitted_universe_dates)}",
            "- 股票池规则：原V1.8.11规则重建每日前300名流动性股票，候选只取前50名。" if zh else "- Universe: rebuild the daily top-300 liquidity universe under the original V1.8.11 rules; the candidate uses the first 50 names.",
            "",
            "## 300万元账户与成本压力" if zh else "## CNY 3 million account and cost stress",
            "",
            "| 成本 | 净收益 | 净利润 | 匹配对照 | 因子增量 | 增量金额 | 最大回撤 |" if zh else "| Cost | Net return | Net profit | Matched control | Factor increment | Value add | Max drawdown |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for label, item in (("标准" if zh else "Standard", self.standard_account), ("2倍" if zh else "2x", self.doubled_account)):
            lines.append(
                f"| {label} | {item.net_total_return:.2%} | {item.net_profit_cny:,.2f} | "
                f"{item.matched_control_net_return:.2%} | {item.incremental_vs_matched_control:.2%} | "
                f"{item.factor_value_add_cny:,.2f} | {item.maximum_drawdown:.2%} |"
            )
        lines.extend([
            "",
            "## 年度一致性" if zh else "## Cross-year consistency",
            "",
            "| 年份 | 净收益 | 匹配对照 | 因子增量 | 横截面基准 |" if zh else "| Year | Net return | Matched control | Factor increment | Cross-section benchmark |",
            "|---|---:|---:|---:|---:|",
        ])
        for item in self.standard_by_year:
            lines.append(
                f"| {item.label} | {item.net_total_return:.2%} | {item.matched_control_net_return:.2%} | "
                f"{item.incremental_vs_matched_control:.2%} | {item.cross_section_benchmark_return:.2%} |"
            )
        lines.extend([
            "",
            "## 路径与统计证伪" if zh else "## Path and statistical falsification",
            "",
            "| 成本 | 超额收益 | 因子增量 | 正收益路径 | 中位路径Sharpe |" if zh else "| Cost | Excess return | Factor increment | Positive paths | Median path Sharpe |",
            "|---|---:|---:|---:|---:|",
        ])
        for label, item in (("1x", self.standard_path), ("2x", self.doubled_path)):
            lines.append(
                f"| {label} | {item.combined.portfolio_excess_return:.2%} | "
                f"{item.combined.incremental_return:.2%} | {item.combined.positive_return_paths}/20 | "
                f"{item.combined.median_sharpe:.4f} |"
            )
        lines.extend([
            "",
            f"- {'Placebo p值（信号/收益）' if zh else 'Placebo p-values (signal/return)'}: {self.signal_placebo_p:.6g} / {self.return_placebo_p:.6g}",
            f"- DSR: {self.dsr_probability:.6g}",
            f"- {'DSR偏度/超额峰度' if zh else 'DSR skew/excess kurtosis'}: {self.dsr_skewness:.6g} / {self.dsr_excess_kurtosis:.6g}",
            f"- {'失败门禁' if zh else 'Failed gates'}: {', '.join(self.gate_failures) or ('无' if zh else 'none')}",
            "",
            "## 市场指数比较" if zh else "## Market-index comparison",
            "",
            "| 基准 | 候选同期净收益 | 指数价格收益 | 跑赢 | 金额优势 |" if zh else "| Benchmark | Candidate net | Index price return | Outperformance | Value advantage |",
            "|---|---:|---:|---:|---:|",
        ])
        for item in self.index_comparisons:
            lines.append(
                f"| {item.name} ({item.comparison_start}–{item.comparison_end}) | {item.candidate_net_return:.2%} | "
                f"{item.index_price_return:.2%} | {item.candidate_minus_index:.2%} | {item.value_advantage_cny:,.2f} |"
            )
        lines.extend(["", "## 限制、不确定性与稳健性" if zh else "## Limitations, uncertainty and robustness", ""])
        lines.extend(f"- {item[0] if zh else item[1]}" for item in self.limitations)
        lines.extend([
            "",
            "## 建议的下一步" if zh else "## Recommended next steps",
            "",
            (
                "保留本结果作为只追加的历史证伪证据。无论通过或失败，均不得回到2020–2021调参；正式判断继续等待2026-08-16之后至少25个新交易日。"
                if zh
                else "Retain this result as append-only historical falsification evidence. Whether it passes or fails, do not tune on 2020–2021; the official decision still waits for at least 25 new sessions after 2026-08-16."
            ),
            "",
            "## 仍需回答的问题" if zh else "## Further questions",
            "",
            (
                "每日盯市券商净值复核是否会显著改变重叠cohort口径的绝对收益？2020–2021历史基本面快照的供应商修订策略是否完全可证明？"
                if zh
                else "Would a broker-style daily marked NAV materially change the overlapping-cohort absolute return? Is the vendor revision policy for the 2020–2021 fundamental snapshots fully provable?"
            ),
            "",
        ])
        return "\n".join(lines)


def _grid_evidence(
    events: tuple[UsageEvent, ...],
    controls: tuple[UsageEvent, ...],
    *,
    multiplier: float,
    clipped: float,
    trial_id: str,
    trial_number: int,
) -> GridEvidence:
    combined = _path(2020, events, controls, 20)
    years = tuple(
        _path(
            year,
            tuple(item for item in events if item.day.startswith(f"{year}-")),
            tuple(item for item in controls if item.day.startswith(f"{year}-")),
            20,
        )
        for year in (2020, 2021)
    )
    attribution = TurnoverAttribution(
        mean(item.turnover for item in events),
        sum(item.cost_rate for item in events),
        math.prod(1 + item.excess_return + item.cost_rate for item in events) - 1,
        math.prod(1 + item.excess_return for item in events) - 1,
    )
    return GridEvidence(
        "flow_auction_ensemble",
        10,
        multiplier,
        combined,
        years,
        attribution,
        clipped,
        trial_id,
        trial_number,
    )


def _trial(
    registry: ExperimentRegistry,
    experiment_id: str,
    multiplier: float,
    fingerprint: str,
    seed: int,
) -> tuple[str, int]:
    return registry.create_trial(
        TrialSpec(
            experiment_id,
            "v4.8_frozen_historical_falsification",
            fingerprint,
            json.dumps({"cost_multiplier": multiplier, "candidate_frozen": True}, sort_keys=True),
            seed,
            "2022-01-01",
            "2024-12-31",
            "2025-01-01",
            "2026-08-16",
            HISTORICAL_START,
            HISTORICAL_END,
        )
    )


def run_v48_historical_falsification(
    daily_dir: str | Path,
    fundamental_dir: str | Path,
    *,
    auction_dir: str | Path,
    fund_flow_dir: str | Path,
    csi300_csv: str | Path,
    csi500_csv: str | Path,
    registry: ExperimentRegistry,
    v46_registry: ExperimentRegistry,
    v47_registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    config: V48HistoricalConfig | None = None,
    prior_inferential_trials: int = 1103,
) -> V48HistoricalReport:
    config = config or V48HistoricalConfig()
    config.validate()
    fingerprint = _fingerprint()
    prior_sharpes = (*v46_trial_sharpes(v46_registry), *v47_trial_sharpes(v47_registry))
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    universe = build_dynamic_universe(
        daily_dir,
        fundamental_dir,
        DynamicUniverseConfig(
            research_start=config.test_start,
            research_end=config.test_end,
            top_n=config.universe_builder_top_n,
            minimum_history_sessions=config.minimum_history_sessions,
            liquidity_lookback=config.liquidity_lookback,
            minimum_mean_amount_cny=config.minimum_mean_amount_cny,
            allowed_missing_fundamental_dates=HISTORICAL_FUNDAMENTAL_OMISSIONS,
        ),
    )
    universe_artifacts = write_dynamic_universe(universe, output / "historical-dynamic-universe")
    memberships, membership_sha = _load_memberships(
        universe_artifacts.membership_jsonl_path, config.universe_top_n
    )
    instruments = tuple(sorted({item for members in memberships.values() for item in members}))
    daily_root = Path(daily_dir).expanduser().resolve()
    files = select_qd_daily_files(daily_root, start_date=config.data_start, end_date=config.test_end)
    daily_manifest = build_selected_files_snapshot_manifest(daily_root, files)
    daily = load_qd_daily_directory(
        daily_root,
        start_date=config.data_start,
        end_date=config.test_end,
        instruments=instruments,
    )
    alternatives = {}
    hashes = {}
    alternative_dates = {}
    for kind, source in (("auction", auction_dir), ("fund_flow", fund_flow_dir)):
        dataset = load_qd_alternative_directory(
            source,
            QdAlternativeConfig(
                source_kind=kind,  # type: ignore[arg-type]
                start_date=config.data_start,
                end_date=config.test_end,
                ingested_at=config.ingested_at,
                instruments=instruments,
            ),
        )
        alternatives[kind] = dataset.observations
        hashes[kind] = dataset.audit.source_sha256
        alternative_dates[kind] = {item.effective_at[:10] for item in dataset.observations}
    index_hashes = {
        key: hashlib.sha256(Path(source).expanduser().resolve().read_bytes()).hexdigest()
        for key, source in (("csi300", csi300_csv), ("csi500", csi500_csv))
    }
    composite = build_composite_snapshot_manifest(
        {
            "qd_daily": daily_manifest.snapshot_sha256,
            "historical_universe_source": universe.source_snapshot_sha256,
            "historical_membership": membership_sha,
            **hashes,
            **index_hashes,
        }
    )
    snapshot_id = registry.register_snapshot(
        composite,
        vendor_version=V48_HISTORICAL_VERSION,
        notes="frozen-candidate 2020-2021 backward temporal falsification",
    )
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            "V4.8 frozen candidate historical falsification",
            "The unchanged candidate should replicate in 2020-2021 without backward-filled membership.",
            snapshot_id,
            code_version,
            json.dumps(
                {"version": V48_HISTORICAL_VERSION, "config": asdict(config), "fingerprint": fingerprint},
                sort_keys=True,
            ),
        )
    )
    calendar = tuple(sorted({item.trade_date for item in daily.bars}))
    bars: dict[str, dict[str, QmtDailyBar]] = defaultdict(dict)
    for bar in daily.bars:
        bars[bar.instrument][bar.trade_date] = bar
    execution_members = _execution_memberships(memberships, calendar)
    anchors = tuple(
        row
        for year in (2020, 2021)
        for row in _anchors(
            year=year,
            horizon=config.horizon,
            calendar=calendar,
            bars=bars,
            execution_members=execution_members,
        )
    )
    flow_schema, auction_schema = _selected_schemas()
    raw_panels = {}
    for schema, source_kind in ((flow_schema, "fund_flow"), (auction_schema, "auction")):
        built = build_multisource_factor_observations(
            daily.bars,
            {f"qd_{source_kind}": alternatives[source_kind]},
            schema.compile(),
            anchors,
        )
        raw_panels[schema.schema_id] = tuple(
            EvaluationObservation(
                timestamp=row.execution_at,
                instrument=row.instrument,
                factor_value=schema.direction * row.signal,
                factor_available_at=row.signal_available_at,
                label_start_at=row.execution_at,
                label_end_at=row.return_end_at,
                forward_return=row.forward_return,
                horizon="20d",
                subperiod=row.execution_at[:4],
                regime="unspecified",
            )
            for row in built
            if row.eligible
        )
    ensemble = tuple(
        row
        for year in (2020, 2021)
        for row in _ensemble_panel(
            (
                tuple(item for item in raw_panels[FLOW_SCHEMA_ID] if item.timestamp.startswith(f"{year}-")),
                tuple(item for item in raw_panels[AUCTION_SCHEMA_ID] if item.timestamp.startswith(f"{year}-")),
            ),
            year=year,
        )
    )
    ensemble = tuple(
        item for item in ensemble if config.test_start <= item.timestamp[:10] <= config.test_end
    )
    common_source_dates = (
        {day for day in calendar if config.test_start <= day <= config.test_end}
        & alternative_dates["auction"]
        & alternative_dates["fund_flow"]
    )
    if len(common_source_dates) < 400 or len({item.timestamp[:10] for item in ensemble}) < 400:
        raise ValueError("historical falsification has insufficient common dated observations")
    base_usage = V41Config(
        primary_nav=config.nav,
        commission_bps=config.commission_bps,
        sell_tax_bps=config.sell_tax_bps,
        slippage_bps=config.slippage_bps,
        impact_bps=config.impact_bps,
        participation_rate=config.participation_rate,
        ingested_at=config.ingested_at,
    )
    accounting_sets = []
    control_sets = []
    evidence = []
    trial_ids = []
    clipped_values = []
    for multiplier in (1.0, 2.0):
        usage = replace(
            base_usage,
            commission_bps=config.commission_bps * multiplier,
            sell_tax_bps=config.sell_tax_bps * multiplier,
            slippage_bps=config.slippage_bps * multiplier,
            impact_bps=config.impact_bps * multiplier,
        )
        accounting, clipped = evaluate_buffered_avoid_accounting_events(
            ensemble,
            breadth=config.breadth,
            buffer_ranks=config.buffer_ranks,
            horizon=config.horizon,
            nav=config.nav,
            bars=bars,
            calendar=calendar,
            config=usage,
        )
        events, _ = evaluate_buffered_avoid_events(
            ensemble,
            breadth=config.breadth,
            buffer_ranks=config.buffer_ranks,
            horizon=config.horizon,
            nav=config.nav,
            bars=bars,
            calendar=calendar,
            config=usage,
        )
        controls, _ = evaluate_usage_events(
            ensemble,
            ensemble,
            UsageSpec("AVOID", 0, "all"),
            horizon=config.horizon,
            nav=config.nav,
            bars=bars,
            calendar=calendar,
            regimes={},
            config=usage,
        )
        trial_id, trial_number = _trial(registry, experiment_id, multiplier, fingerprint, config.seed)
        item = _grid_evidence(
            events,
            controls,
            multiplier=multiplier,
            clipped=clipped,
            trial_id=trial_id,
            trial_number=trial_number,
        )
        registry.record_trial_result(trial_id, json.dumps(asdict(item), sort_keys=True))
        accounting_sets.append(accounting)
        control_sets.append(controls)
        evidence.append(item)
        trial_ids.append(trial_id)
        clipped_values.append(clipped)
    if registry.global_trial_count() != 2:
        raise AssertionError("historical falsification must record exactly two Trials")
    standard_account = summarize_accounting(
        "2020-2021",
        accounting_sets[0],
        nav=config.nav,
        clipped=clipped_values[0],
        matched_control=control_sets[0],
    )
    doubled_account = summarize_accounting(
        "2020-2021",
        accounting_sets[1],
        nav=config.nav,
        clipped=clipped_values[1],
        matched_control=control_sets[1],
    )
    yearly = tuple(
        summarize_accounting(
            str(year),
            tuple(item for item in accounting_sets[0] if item.day.startswith(f"{year}-")),
            nav=config.nav,
            clipped=0.0,
            matched_control=tuple(item for item in control_sets[0] if item.day.startswith(f"{year}-")),
        )
        for year in (2020, 2021)
    )
    comparisons = (
        compare_index("沪深300 / CSI 300", csi300_csv, accounting_sets[0], nav=config.nav),
        compare_index("中证500 / CSI 500", csi500_csv, accounting_sets[0], nav=config.nav),
    )
    signal_placebo = run_placebo(
        ensemble,
        horizon="20d",
        direction=1,
        method="signal_shuffle",
        seed=config.seed,
        repetitions=config.placebo_repetitions,
        min_cross_section=10,
    )
    return_placebo = run_placebo(
        ensemble,
        horizon="20d",
        direction=1,
        method="return_permutation",
        seed=config.seed,
        repetitions=config.placebo_repetitions,
        min_cross_section=10,
    )
    increment = _increment_by_day(
        tuple(
            UsageEvent(
                item.day,
                item.offset,
                item.excess_return,
                item.turnover,
                item.cost_rate,
                True,
            )
            for item in accounting_sets[0]
        ),
        control_sets[0],
    )
    incremental_series = tuple(increment[day] for day in sorted(increment))
    skewness, excess_kurtosis = _moments(incremental_series)
    raw_sharpe = evidence[0].combined.incremental_daily_sharpe / math.sqrt(252)
    recorded_trials = prior_inferential_trials + registry.global_trial_count()
    dsr = deflated_sharpe_ratio(
        observed_sharpe=raw_sharpe,
        trial_sharpes=(*prior_sharpes, raw_sharpe),
        recorded_trial_count=recorded_trials,
        observations=len({item.timestamp[:10] for item in ensemble}),
        skewness=skewness,
        excess_kurtosis=excess_kurtosis,
    )
    failures = []
    for label, item in (("standard", evidence[0]), ("double_cost", evidence[1])):
        path = item.combined
        if path.portfolio_excess_return <= 0 or path.incremental_return <= 0:
            failures.append(f"{label}_return")
        if path.positive_return_paths < config.minimum_positive_paths:
            failures.append(f"{label}_path_count")
        if path.median_sharpe < config.minimum_median_path_sharpe:
            failures.append(f"{label}_median_path_sharpe")
        if any(year.portfolio_excess_return <= 0 or year.incremental_return <= 0 for year in item.years):
            failures.append(f"{label}_cross_year")
    if signal_placebo.empirical_p_value > config.maximum_placebo_p:
        failures.append("signal_placebo")
    if return_placebo.empirical_p_value > config.maximum_placebo_p:
        failures.append("return_placebo")
    if dsr.probability < config.minimum_dsr:
        failures.append("deflated_sharpe_ratio")
    limitations = (
        (
            "这是发现候选之后的反向时间检验；可用于证伪和机制讨论，但不能替代真正的前向样本外证据。",
            "This backward temporal test occurs after candidate discovery; it can falsify and inform mechanism discussion but cannot replace genuine forward out-of-sample evidence.",
        ),
        (
            "2020–2021股票池由同日基本面和历史流动性按原规则重建，没有使用2022名单倒灌。",
            "The 2020–2021 universe is rebuilt from same-day fundamentals and trailing liquidity under the original rules; no 2022 membership is backfilled.",
        ),
        (
            "14个基本面分区为空或缺少上市日期，已整日隔离为无新股票池决策；系统继续使用此前已知名单，未填充缺失字段。",
            "Fourteen fundamental partitions are empty or lack listing dates and are quarantined as no-new-universe-decision days; the system retains the prior known membership without filling missing fields.",
        ),
        (
            "绝对收益沿用重叠cohort资金贡献口径，不是经过券商逐日盯市核对的实盘净值。",
            "Absolute return uses the overlapping-cohort contribution convention rather than a broker-reconciled daily marked NAV.",
        ),
        (
            "指数为价格指数，不含现金分红；相对指数的跑赢包含股票池风格暴露。",
            "The benchmarks are price indexes without cash dividends; index outperformance includes universe style exposure.",
        ),
        (
            "本轮只运行冻结候选和2个预声明成本场景，没有搜索替代因子或调节参数。",
            "This run evaluates only the frozen candidate and two predeclared cost scenarios; no replacement factor or parameter search is performed.",
        ),
    )
    report = V48HistoricalReport(
        V48_HISTORICAL_VERSION,
        fingerprint,
        FROZEN_CANDIDATE_COMMIT,
        "post-discovery backward temporal falsification; append-only and never a forward Alpha Court",
        experiment_id,
        snapshot_id,
        composite.snapshot_sha256,
        tuple(trial_ids),
        recorded_trials,
        universe.source_snapshot_sha256,
        membership_sha,
        universe.sessions,
        universe.unique_members,
        universe.omitted_fundamental_dates,
        len(common_source_dates),
        standard_account,
        doubled_account,
        yearly,
        evidence[0],
        evidence[1],
        comparisons,
        signal_placebo.empirical_p_value,
        return_placebo.empirical_p_value,
        dsr.probability,
        skewness,
        excess_kurtosis,
        tuple(failures),
        "PASS_HISTORICAL_FALSIFICATION" if not failures else "FAIL_HISTORICAL_FALSIFICATION",
        limitations,
    )
    (output / "v4.8-historical-falsification.json").write_text(report.to_json() + "\n", encoding="utf-8")
    (output / "v4.8-historical-falsification.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (output / "v4.8-historical-falsification.en.md").write_text(report.to_markdown("en"), encoding="utf-8")
    return report
