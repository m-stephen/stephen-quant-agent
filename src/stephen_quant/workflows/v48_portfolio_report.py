from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean

from stephen_quant.evaluation import EvaluationObservation
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import (
    build_composite_snapshot_manifest,
    build_selected_files_snapshot_manifest,
)
from stephen_quant.qmt import (
    QdAlternativeConfig,
    QmtDailyBar,
    build_multisource_factor_observations,
    load_qd_alternative_directory,
    load_qd_daily_directory,
    select_qd_daily_files,
)

from .price_discovery_lab import _execution_memberships, _load_memberships
from .v41_semantic_alpha import UsageEvent, UsageSpec, V41Config, _anchors, evaluate_usage_events
from .v46_orthogonal_search import _ensemble_panel
from .v47_low_turnover_alpha import (
    AUCTION_SCHEMA_ID,
    FLOW_SCHEMA_ID,
    BufferedAvoidAccountingEvent,
    _selected_schemas,
    evaluate_buffered_avoid_accounting_events,
)

V48_PORTFOLIO_REPORT_VERSION = "v4.8-frozen-portfolio-report-1.0.0"


@dataclass(frozen=True)
class V48PortfolioReportConfig:
    data_start: str = "2021-01-01"
    report_start: str = "2025-01-01"
    report_end: str = "2026-08-16"
    universe_top_n: int = 50
    horizon: int = 20
    breadth: int = 10
    buffer_ranks: int = 10
    initial_nav: float = 3_000_000.0
    commission_bps: float = 3.0
    sell_tax_bps: float = 5.0
    slippage_bps: float = 5.0
    impact_bps: float = 10.0
    participation_rate: float = 0.05
    ingested_at: str = "2026-08-18T00:00:00+08:00"

    def validate(self) -> None:
        if (self.report_start, self.report_end) != ("2025-01-01", "2026-08-16"):
            raise ValueError("V4.8 portfolio-report window is frozen to 2025 through 2026-08-16")
        if (self.horizon, self.breadth, self.buffer_ranks) != (20, 10, 10):
            raise ValueError("V4.8 portfolio-report candidate identity is frozen")
        if self.initial_nav != 3_000_000.0:
            raise ValueError("V4.8 portfolio-report NAV is frozen at CNY 3 million")


@dataclass(frozen=True)
class AccountingSummary:
    label: str
    event_start: str
    event_end: str
    economic_end: str
    cohort_events: int
    initial_nav_cny: float
    gross_total_return: float
    net_total_return: float
    net_profit_cny: float
    final_nav_cny: float
    annualized_net_return: float
    maximum_drawdown: float
    total_cost_cny: float
    cross_section_benchmark_return: float
    arithmetic_outperformance: float
    existing_model_excess_return: float
    matched_control_net_return: float
    incremental_vs_matched_control: float
    matched_control_final_nav_cny: float
    factor_value_add_cny: float
    mean_turnover: float
    mean_retained_fraction: float
    capacity_clipped_notional_cny: float


@dataclass(frozen=True)
class IndexComparison:
    name: str
    source_sha256: str
    comparison_start: str
    comparison_end: str
    index_sessions: int
    index_price_return: float
    candidate_net_return: float
    candidate_minus_index: float
    candidate_final_nav_cny: float
    index_final_value_cny: float
    value_advantage_cny: float
    coverage_note: str


@dataclass(frozen=True)
class V48PortfolioAccountingReport:
    method_version: str
    experiment_id: str
    trial_id: str
    trial_number: int
    snapshot_id: str
    snapshot_sha256: str
    candidate: str
    evidence_classification: str
    membership_first_decision: str
    membership_last_decision: str
    membership_policy: str
    standard: AccountingSummary
    doubled_cost: AccountingSummary
    standard_by_start_year: tuple[AccountingSummary, ...]
    index_comparisons: tuple[IndexComparison, ...]
    limitations: tuple[tuple[str, str], ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        title = (
            "# V4.8 冻结候选：2025–2026 账户收益与市场基准报告"
            if zh
            else "# V4.8 Frozen Candidate: 2025–2026 Account and Market Benchmark Report"
        )
        standard = self.standard
        lines = [
            title,
            "",
            "## 技术摘要" if zh else "## Technical summary",
            "",
            (
                f"按现有20日错位 cohort 会计口径，300万元在 {standard.event_start} 至 "
                f"{standard.economic_end} 的标准成本净收益为 **{standard.net_total_return:.2%}**，"
                f"净利润 **{standard.net_profit_cny:,.2f} 元**，期末模型净值 "
                f"**{standard.final_nav_cny:,.2f} 元**。相对同股票池、同路径和同成本的匹配对照，"
                f"因子增加 **{standard.incremental_vs_matched_control:.2%}**，约 "
                f"**{standard.factor_value_add_cny:,.2f} 元**。"
                if zh
                else f"Under the existing staggered 20-session cohort accounting, CNY 3 million "
                f"earned **{standard.net_total_return:.2%}** net from {standard.event_start} through "
                f"{standard.economic_end}, equal to **CNY {standard.net_profit_cny:,.2f}**, for a "
                f"model ending value of **CNY {standard.final_nav_cny:,.2f}**. Against the same-universe, "
                f"same-path and same-cost matched control, the factor added "
                f"**{standard.incremental_vs_matched_control:.2%}**, or **CNY {standard.factor_value_add_cny:,.2f}**."
            ),
            "",
            (
                "该数字是冻结候选的模型回测账户收益，不是券商实盘对账单。2025属于已参与选择的开发证据；"
                "2026属于一次性封存证据；拼接结果只能用于账户解释，不能被重新标记为完整样本外收益。"
                if zh
                else "This is model-account performance, not a broker statement. 2025 is consumed "
                "development evidence and 2026 is one-time sealed evidence; the combined curve is "
                "descriptive and cannot be relabelled as wholly out of sample."
            ),
            "",
            (
                f"共同指数区间内，候选跑赢沪深300和中证500分别为 "
                f"**{self.index_comparisons[0].candidate_minus_index:.2%}** 和 "
                f"**{self.index_comparisons[1].candidate_minus_index:.2%}**；但这些差额包含冻结前50股票池的"
                f"风格与选股暴露。更保守的同股票池因子增量是 **{standard.incremental_vs_matched_control:.2%}**，"
                "不应把全部指数跑赢都称为 Alpha。"
                if zh
                else f"Over the common index interval, the candidate beat CSI 300 and CSI 500 by "
                f"**{self.index_comparisons[0].candidate_minus_index:.2%}** and "
                f"**{self.index_comparisons[1].candidate_minus_index:.2%}**, but those gaps include frozen-top-50 "
                f"universe and style exposure. The more conservative same-universe factor increment is "
                f"**{standard.incremental_vs_matched_control:.2%}**; not all index outperformance is alpha."
            ),
            "",
            "## 300万元账户结果" if zh else "## CNY 3 million account result",
            "",
            "| 成本情景 | 净收益率 | 净利润 | 匹配对照 | 因子增量 | 增量金额 | 最大回撤 | 成本 |"
            if zh
            else "| Cost scenario | Net return | Net profit | Matched control | Factor increment | Value add | Max drawdown | Cost |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for label, item in (
            ("标准" if zh else "Standard", self.standard),
            ("2倍" if zh else "2x", self.doubled_cost),
        ):
            lines.append(
                f"| {label} | {item.net_total_return:.2%} | {item.net_profit_cny:,.2f} | "
                f"{item.matched_control_net_return:.2%} | {item.incremental_vs_matched_control:.2%} | "
                f"{item.factor_value_add_cny:,.2f} | "
                f"{item.maximum_drawdown:.2%} | {item.total_cost_cny:,.2f} |"
            )
        lines.extend(
            [
                "",
                "## 分段贡献" if zh else "## Period contribution",
                "",
                (
                    "分段按 cohort 启动年份归类；跨年持有的 cohort 仍归入启动年份。"
                    if zh
                    else "Segments are classified by cohort start year; a cohort that matures in the next year remains in its start-year segment."
                ),
                "",
                "| 启动年份 | 净收益率 | 净利润 | 匹配对照 | 因子增量 | 横截面基准 |"
                if zh
                else "| Start year | Net return | Net profit | Matched control | Factor increment | Cross-section benchmark |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for item in self.standard_by_start_year:
            lines.append(
                f"| {item.label} | {item.net_total_return:.2%} | {item.net_profit_cny:,.2f} | "
                f"{item.matched_control_net_return:.2%} | {item.incremental_vs_matched_control:.2%} | "
                f"{item.cross_section_benchmark_return:.2%} |"
            )
        lines.extend(
            [
                "",
                "## 与市场指数比较" if zh else "## Market-index comparison",
                "",
                (
                    "指数采用价格指数的首日开盘至末日开盘口径。由于本地指数文件只到2026-07-30，"
                    "指数比较自动截断；因子自身全期账户结果仍计算至可成熟 cohort 的2026-08-14。"
                    if zh
                    else "Indexes use first-open to last-open price returns. Local index files stop at 2026-07-30, "
                    "so index comparisons are truncated automatically; the candidate-only account result still includes cohorts maturing through 2026-08-14."
                ),
                "",
                "| 基准 | 同期因子净收益 | 指数收益 | 跑赢 | 因子期末值 | 指数期末值 | 金额优势 |"
                if zh
                else "| Benchmark | Candidate net | Index return | Outperformance | Candidate value | Index value | Value advantage |",
                "|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for item in self.index_comparisons:
            lines.append(
                f"| {item.name} ({item.comparison_start}–{item.comparison_end}) | "
                f"{item.candidate_net_return:.2%} | {item.index_price_return:.2%} | "
                f"{item.candidate_minus_index:.2%} | {item.candidate_final_nav_cny:,.2f} | "
                f"{item.index_final_value_cny:,.2f} | {item.value_advantage_cny:,.2f} |"
            )
        lines.extend(
            [
                "",
                "## 指标定义与方法" if zh else "## Metric definitions and method",
                "",
                (
                    "- 绝对净收益：每个错位 cohort 的资金贡献收益扣除佣金、印花税、滑点和冲击成本后，"
                    "按现有系统口径复合。\n- 横截面基准：同一候选股票池全部合格股票的等权20日收益，不是沪深300。\n"
                    "- 匹配对照：同一股票池、20日错位路径、资金和成本下持有全部合格股票，用于隔离因子筛选增量。\n"
                    "- 指数跑赢：在指数文件实际覆盖的共同区间内，因子净收益率减指数价格收益率。\n"
                    "- 股票池：读取动态 membership 的前50只；2024-12-31之后沿用最后一次已知名单。"
                    if zh
                    else "- Absolute net return compounds each staggered cohort's capital contribution after commission, tax, slippage and impact under the existing system convention.\n"
                    "- The cross-section benchmark is the equal-weight 20-session return of all eligible names in the same candidate universe, not CSI 300.\n"
                    "- The matched control holds all eligible names under the same universe, staggered paths, capital and costs to isolate factor selection value.\n"
                    "- Index outperformance is candidate net return minus index price return over the common covered interval.\n"
                    "- The universe uses the first 50 names in the dynamic membership; after 2024-12-31 the last known membership is carried forward."
                ),
                "",
                "## 限制与稳健性" if zh else "## Limitations and robustness",
                "",
            ]
        )
        lines.extend(f"- {item[0] if zh else item[1]}" for item in self.limitations)
        lines.extend(
            [
                "",
                "## 下一步" if zh else "## Next steps",
                "",
                (
                    "在讨论实盘部署前，应补充每日盯市的状态化NAV复核、更新2025–2026动态股票池、"
                    "补齐8月指数数据，并继续等待2026-08-16之后约25个真正新增交易日完成DSR续验。"
                    if zh
                    else "Before deployment, add a daily marked-to-market stateful NAV reconciliation, refresh the "
                    "2025–2026 universe, complete August index data, and retain the frozen candidate until roughly "
                    "25 genuinely new sessions after 2026-08-16 are available for the DSR continuation."
                ),
                "",
            ]
        )
        return "\n".join(lines)


def _compound(values: list[float]) -> float:
    return math.prod(1 + value for value in values) - 1 if values else 0.0


def _drawdown(values: list[float]) -> float:
    wealth = peak = 1.0
    worst = 0.0
    for value in values:
        wealth *= 1 + value
        peak = max(peak, wealth)
        worst = min(worst, wealth / peak - 1)
    return worst


def summarize_accounting(
    label: str,
    events: tuple[BufferedAvoidAccountingEvent, ...],
    *,
    nav: float,
    clipped: float,
    matched_control: tuple[UsageEvent, ...],
) -> AccountingSummary:
    if not events:
        raise ValueError(f"accounting segment {label} has no events")
    net_values = [item.net_portfolio_return for item in events]
    gross_values = [item.gross_portfolio_return for item in events]
    benchmark_values = [item.benchmark_return for item in events]
    excess_values = [item.excess_return for item in events]
    net = _compound(net_values)
    gross = _compound(gross_values)
    benchmark = _compound(benchmark_values)
    benchmark_by_key = {(item.day, item.offset): item.benchmark_return for item in events}
    if {(item.day, item.offset) for item in matched_control} != set(benchmark_by_key):
        raise ValueError("candidate and matched-control accounting grids differ")
    control_by_key = {
        (item.day, item.offset): item.excess_return + benchmark_by_key[(item.day, item.offset)]
        for item in matched_control
    }
    control = _compound([control_by_key[(item.day, item.offset)] for item in events])
    annualized = (1 + net) ** (252 / len(events)) - 1 if net > -1 else -1.0
    retained = [
        item.retained_instruments / item.selected_instruments
        for item in events
        if item.selected_instruments
    ]
    return AccountingSummary(
        label=label,
        event_start=min(item.day for item in events),
        event_end=max(item.day for item in events),
        economic_end=max(item.end_day for item in events),
        cohort_events=len(events),
        initial_nav_cny=nav,
        gross_total_return=gross,
        net_total_return=net,
        net_profit_cny=nav * net,
        final_nav_cny=nav * (1 + net),
        annualized_net_return=annualized,
        maximum_drawdown=_drawdown(net_values),
        total_cost_cny=nav * sum(item.cost_rate for item in events),
        cross_section_benchmark_return=benchmark,
        arithmetic_outperformance=net - benchmark,
        existing_model_excess_return=_compound(excess_values),
        matched_control_net_return=control,
        incremental_vs_matched_control=net - control,
        matched_control_final_nav_cny=nav * (1 + control),
        factor_value_add_cny=nav * (net - control),
        mean_turnover=mean(item.turnover for item in events),
        mean_retained_fraction=mean(retained) if retained else 0.0,
        capacity_clipped_notional_cny=clipped,
    )


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030", "utf-8"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("index CSV encoding is unsupported")


def compare_index(
    name: str,
    path: str | Path,
    events: tuple[BufferedAvoidAccountingEvent, ...],
    *,
    nav: float,
) -> IndexComparison:
    source = Path(path).expanduser().resolve()
    raw = source.read_bytes()
    reader = csv.DictReader(io.StringIO(_decode(raw), newline=""))
    if not reader.fieldnames or not {"日期", "开盘价"} <= set(reader.fieldnames):
        raise ValueError(f"{name} index file must contain 日期 and 开盘价")
    prices = {}
    for row in reader:
        raw_day = (row.get("日期") or "").strip()
        opening = (row.get("开盘价") or "").strip()
        if len(raw_day) == 8 and opening:
            prices[f"{raw_day[:4]}-{raw_day[4:6]}-{raw_day[6:8]}"] = float(opening)
    if not prices:
        raise ValueError(f"{name} index file contains no usable prices")
    candidate_start = min(item.day for item in events)
    candidate_end = max(item.end_day for item in events)
    covered = sorted(day for day in prices if candidate_start <= day <= candidate_end)
    if len(covered) < 2:
        raise ValueError(f"{name} has insufficient overlap with candidate events")
    start, end = covered[0], covered[-1]
    comparable = tuple(item for item in events if item.day >= start and item.end_day <= end)
    if not comparable:
        raise ValueError(f"{name} has no matured candidate cohorts in its covered interval")
    candidate_return = _compound([item.net_portfolio_return for item in comparable])
    index_return = prices[end] / prices[start] - 1
    candidate_value = nav * (1 + candidate_return)
    index_value = nav * (1 + index_return)
    return IndexComparison(
        name=name,
        source_sha256=hashlib.sha256(raw).hexdigest(),
        comparison_start=start,
        comparison_end=end,
        index_sessions=len(covered),
        index_price_return=index_return,
        candidate_net_return=candidate_return,
        candidate_minus_index=candidate_return - index_return,
        candidate_final_nav_cny=candidate_value,
        index_final_value_cny=index_value,
        value_advantage_cny=candidate_value - index_value,
        coverage_note=(
            f"comparison truncated to index coverage ending {end}; candidate-only accounting continues through {candidate_end}"
        ),
    )


def run_v48_portfolio_report(
    daily_dir: str | Path,
    membership_path: str | Path,
    *,
    auction_dir: str | Path,
    fund_flow_dir: str | Path,
    csi300_csv: str | Path,
    csi500_csv: str | Path,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    config: V48PortfolioReportConfig | None = None,
) -> V48PortfolioAccountingReport:
    config = config or V48PortfolioReportConfig()
    config.validate()
    memberships, membership_sha = _load_memberships(membership_path, config.universe_top_n)
    instruments = tuple(sorted({item for members in memberships.values() for item in members}))
    daily_root = Path(daily_dir).expanduser().resolve()
    files = select_qd_daily_files(
        daily_root, start_date=config.data_start, end_date=config.report_end
    )
    daily_manifest = build_selected_files_snapshot_manifest(daily_root, files)
    daily = load_qd_daily_directory(
        daily_root,
        start_date=config.data_start,
        end_date=config.report_end,
        instruments=instruments,
    )
    alternatives = {}
    hashes = {}
    for kind, source in (("auction", auction_dir), ("fund_flow", fund_flow_dir)):
        dataset = load_qd_alternative_directory(
            source,
            QdAlternativeConfig(
                source_kind=kind,  # type: ignore[arg-type]
                start_date=config.data_start,
                end_date=config.report_end,
                ingested_at=config.ingested_at,
                instruments=instruments,
            ),
        )
        alternatives[kind] = dataset.observations
        hashes[kind] = dataset.audit.source_sha256
    index_hashes = {}
    for key, source in (("csi300", csi300_csv), ("csi500", csi500_csv)):
        index_hashes[key] = hashlib.sha256(
            Path(source).expanduser().resolve().read_bytes()
        ).hexdigest()
    composite = build_composite_snapshot_manifest(
        {
            "qd_daily": daily_manifest.snapshot_sha256,
            "dynamic_universe": membership_sha,
            **hashes,
            **index_hashes,
        }
    )
    snapshot_id = registry.register_snapshot(
        composite,
        vendor_version=V48_PORTFOLIO_REPORT_VERSION,
        notes="frozen-candidate descriptive account and market benchmark accounting",
    )
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            "V4.8 frozen candidate portfolio accounting supplement",
            "Explain absolute CNY account performance without modifying or selecting the candidate.",
            snapshot_id,
            code_version,
            json.dumps(
                {"version": V48_PORTFOLIO_REPORT_VERSION, "config": asdict(config)}, sort_keys=True
            ),
        )
    )
    trial_id, trial_number = registry.create_trial(
        TrialSpec(
            experiment_id,
            "v4.8_frozen_portfolio_accounting_supplement",
            "flow_auction_ensemble_buffer10",
            json.dumps({"report_only": True, "inferential_trial_delta": 0}, sort_keys=True),
            42,
            "2022-01-01",
            "2024-12-31",
            "2025-01-01",
            "2025-12-31",
            "2026-01-01",
            "2026-08-16",
        )
    )
    calendar = tuple(sorted({item.trade_date for item in daily.bars}))
    bars: dict[str, dict[str, QmtDailyBar]] = defaultdict(dict)
    for bar in daily.bars:
        bars[bar.instrument][bar.trade_date] = bar
    execution_members = _execution_memberships(memberships, calendar)
    anchors = tuple(
        row
        for year in (2025, 2026)
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
        for year in (2025, 2026)
        for row in _ensemble_panel(
            (
                tuple(
                    item
                    for item in raw_panels[FLOW_SCHEMA_ID]
                    if item.timestamp.startswith(f"{year}-")
                ),
                tuple(
                    item
                    for item in raw_panels[AUCTION_SCHEMA_ID]
                    if item.timestamp.startswith(f"{year}-")
                ),
            ),
            year=year,
        )
    )
    ensemble = tuple(
        item for item in ensemble if config.report_start <= item.timestamp[:10] <= config.report_end
    )
    if not ensemble:
        raise ValueError("V4.8 portfolio report produced no frozen-candidate rows")
    accounting = []
    controls = []
    clipped_values = []
    for multiplier in (1.0, 2.0):
        usage = V41Config(
            primary_nav=config.initial_nav,
            commission_bps=config.commission_bps * multiplier,
            sell_tax_bps=config.sell_tax_bps * multiplier,
            slippage_bps=config.slippage_bps * multiplier,
            impact_bps=config.impact_bps * multiplier,
            participation_rate=config.participation_rate,
            ingested_at=config.ingested_at,
        )
        events, clipped = evaluate_buffered_avoid_accounting_events(
            ensemble,
            breadth=config.breadth,
            buffer_ranks=config.buffer_ranks,
            horizon=config.horizon,
            nav=config.initial_nav,
            bars=bars,
            calendar=calendar,
            config=usage,
        )
        control, _ = evaluate_usage_events(
            ensemble,
            ensemble,
            UsageSpec("AVOID", 0, "all"),
            horizon=config.horizon,
            nav=config.initial_nav,
            bars=bars,
            calendar=calendar,
            regimes={},
            config=usage,
        )
        accounting.append(events)
        controls.append(control)
        clipped_values.append(clipped)
    standard = summarize_accounting(
        "2025-2026",
        accounting[0],
        nav=config.initial_nav,
        clipped=clipped_values[0],
        matched_control=controls[0],
    )
    doubled = summarize_accounting(
        "2025-2026",
        accounting[1],
        nav=config.initial_nav,
        clipped=clipped_values[1],
        matched_control=controls[1],
    )
    yearly = tuple(
        summarize_accounting(
            str(year),
            tuple(item for item in accounting[0] if item.day.startswith(f"{year}-")),
            nav=config.initial_nav,
            clipped=0.0,
            matched_control=tuple(item for item in controls[0] if item.day.startswith(f"{year}-")),
        )
        for year in (2025, 2026)
    )
    comparisons = (
        compare_index("沪深300 / CSI 300", csi300_csv, accounting[0], nav=config.initial_nav),
        compare_index("中证500 / CSI 500", csi500_csv, accounting[0], nav=config.initial_nav),
    )
    limitations = (
        (
            "2025是重复使用的开发证据；只有2026是一次性封存证据，因此组合账户曲线并非完整样本外结果。",
            "2025 is reused development evidence; only 2026 was one-time sealed, so the combined account curve is not wholly out of sample.",
        ),
        (
            "membership artifact 截止2024-12-31，随后向前沿用至2025–2026；这是冻结股票池测试，不是实时更新股票池。",
            "The membership artifact ends on 2024-12-31 and is carried forward through 2025-2026; this is a frozen-universe test, not a refreshed live universe.",
        ),
        (
            "绝对收益沿用重叠 cohort 资金贡献口径，尚未经过独立的每日券商净值对账。",
            "Absolute return uses the existing overlapping-cohort contribution convention, not an independently reconciled daily broker NAV.",
        ),
        (
            "沪深300和中证500文件截止2026-07-30，因此指数跑赢幅度只报告到该日。",
            "CSI 300 and CSI 500 files end on 2026-07-30, so index outperformance is reported only through that date.",
        ),
        (
            "指数比较使用价格指数，因此不包含现金分红。",
            "Index comparisons use price indexes and therefore exclude cash dividends.",
        ),
        (
            "标准成本下平均93.73%的持仓来自缓冲保留；结果大量反映首次筛选和低换手滞回，而不是每日信号持续更新。",
            "At standard cost, 93.73% of positions were retained by the buffer on average; the result largely reflects initial selection and low-turnover hysteresis rather than continuously refreshed daily signals.",
        ),
        (
            "本报告从2025连续运行并把缓冲持仓带入2026；V4.8封存审计在2026年重新初始化，因此两份报告的2026增量口径不相同。",
            "This report runs continuously from 2025 and carries buffered holdings into 2026; the V4.8 sealed audit reinitialized in 2026, so their 2026 increment figures are not the same accounting path.",
        ),
        (
            "相对指数的跑赢包含冻结前50股票池的市场风格暴露；只有同股票池匹配对照增量更接近因子本身贡献。",
            "Outperformance versus market indexes includes the frozen top-50 universe's style exposure; only the same-universe matched-control increment is close to the factor's isolated contribution.",
        ),
        (
            "候选仍未通过冻结 Alpha Court：DSR 0.933929 低于0.95。",
            "The candidate still fails the frozen Alpha Court because DSR 0.933929 is below 0.95.",
        ),
    )
    report = V48PortfolioAccountingReport(
        V48_PORTFOLIO_REPORT_VERSION,
        experiment_id,
        trial_id,
        trial_number,
        snapshot_id,
        composite.snapshot_sha256,
        "equal percentile rank(flow_price_divergence_5_20d, auction_strength_5_20d); AVOID bottom 10; buffer 10",
        "2025 consumed development + 2026 one-time sealed; descriptive combined accounting only",
        min(memberships),
        max(memberships),
        "top 50 daily membership through 2024-12-31; last known membership carried forward",
        standard,
        doubled,
        yearly,
        comparisons,
        limitations,
    )
    registry.record_trial_result(trial_id, report.to_json())
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "v4.8-portfolio-report.json").write_text(report.to_json() + "\n", encoding="utf-8")
    (output / "v4.8-portfolio-report.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (output / "v4.8-portfolio-report.en.md").write_text(report.to_markdown("en"), encoding="utf-8")
    return report
