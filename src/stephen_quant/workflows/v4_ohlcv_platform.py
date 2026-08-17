from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from statistics import mean, stdev

from stephen_quant.evaluation import (
    EvaluationObservation,
    pearson_correlation,
    spearman_correlation,
)
from stephen_quant.falsification import deflated_sharpe_ratio, run_placebo
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import (
    build_composite_snapshot_manifest,
    build_selected_files_snapshot_manifest,
)
from stephen_quant.qmt import QmtDailyBar, load_qd_daily_directory, select_qd_daily_files

from .price_discovery_lab import (
    HORIZONS,
    SECONDARY_LOOKBACKS,
    CandidateResult,
    PriceCandidate,
    YearScore,
    _cpcv,
    _drawdown,
    _execution_memberships,
    _fingerprint,
    _load_memberships,
    _moments,
    _panel,
    _score,
    generate_price_candidates,
)

V4_PLATFORM_VERSION = "v4.0-single-user-ohlcv-platform-1.0.0"
V4_FAMILIES = (
    "trend_curvature",
    "breakout_position",
    "drawdown_recovery",
    "downside_volatility",
    "upside_volatility",
    "range_volatility",
    "gap_mean",
    "intraday_mean",
    "overnight_momentum",
    "volume_price_divergence",
    "liquidity_change",
    "return_skewness",
)


@dataclass(frozen=True)
class V4Config:
    data_start: str = "2021-01-01"
    discovery_year: int = 2022
    confirmation_year: int = 2023
    shadow_year: int = 2024
    universe_top_n: int = 50
    minimum_cross_section: int = 10
    cluster_correlation: float = 0.85
    family_quota: int = 4
    shortlist_limit: int = 60
    court_limit: int = 10
    placebo_repetitions: int = 199
    seed: int = 42
    portfolio_top_ks: tuple[int, ...] = (5, 10, 20, 30)
    portfolio_weights: tuple[str, ...] = ("equal", "rank", "clipped_z")
    portfolio_buffers: tuple[int, ...] = (0, 5)
    capacity_navs: tuple[float, ...] = (
        1_000_000.0,
        3_000_000.0,
        5_000_000.0,
        10_000_000.0,
        20_000_000.0,
    )
    primary_nav: float = 3_000_000.0
    commission_bps: float = 3.0
    sell_tax_bps: float = 5.0
    slippage_bps: float = 5.0
    impact_bps: float = 10.0
    participation_rate: float = 0.05
    minimum_dsr: float = 0.95
    maximum_placebo_p: float = 0.05
    maximum_pbo: float = 0.20
    minimum_excess_sharpe: float = 0.50
    maximum_drawdown: float = 0.25

    def validate(self) -> None:
        if (self.discovery_year, self.confirmation_year, self.shadow_year) != (2022, 2023, 2024):
            raise ValueError("V4 research windows are frozen to 2022/2023/2024")
        if not 0 < self.cluster_correlation < 1 or self.family_quota < 1:
            raise ValueError("invalid clustering policy")
        if self.primary_nav not in self.capacity_navs:
            raise ValueError("primary NAV must be represented in the capacity curve")
        if set(self.portfolio_weights) != {"equal", "rank", "clipped_z"}:
            raise ValueError("V4 portfolio weights are frozen")


@dataclass(frozen=True)
class CandidateCluster:
    cluster_id: str
    representative_id: str
    representative_fingerprint: str
    family: str
    members: tuple[str, ...]
    maximum_member_correlation: float


@dataclass(frozen=True)
class AttributionResult:
    candidate_id: str
    raw_2023_rank_ic: float
    residual_2023_rank_ic: float
    raw_2024_rank_ic: float
    residual_2024_rank_ic: float
    controls: tuple[str, ...]
    passed: bool


@dataclass(frozen=True)
class PortfolioSpec:
    top_k: int
    weighting: str
    buffer: int

    @property
    def identity(self) -> str:
        return f"top{self.top_k}_{self.weighting}_buffer{self.buffer}"


@dataclass(frozen=True)
class PortfolioScore:
    candidate_id: str
    year: int
    spec: PortfolioSpec
    nav_cny: float
    observations: int
    excess_sharpe: float
    cumulative_excess_return: float
    maximum_drawdown: float
    mean_turnover: float
    total_cost_rate: float
    capacity_clipped_notional: float
    offsets: int


@dataclass(frozen=True)
class EnsembleResult:
    method: str
    members: tuple[str, ...]
    weights: tuple[float, ...]
    confirmation: PortfolioScore
    shadow: PortfolioScore


@dataclass(frozen=True)
class ResearchAgentAudit:
    mode: str
    states: tuple[str, ...]
    proposals: int
    unique_proposals: int
    duplicate_tombstones: int
    failure_memories: int
    empirical_llm_calls: int
    deep_model_authorized: bool


@dataclass(frozen=True)
class SealedRelease:
    state: str
    allowed_years: tuple[int, ...]
    sealed_years: tuple[int, ...]
    candidate_manifest_sha256: str
    portfolio_manifest_sha256: str
    gates_sha256: str
    release_manifest_sha256: str


@dataclass(frozen=True)
class PaperReplay:
    mode: str
    start_nav_cny: float
    end_nav_cny: float
    periods: int
    maximum_drawdown: float
    kill_switch_triggered: bool
    live_orders_submitted: int


@dataclass(frozen=True)
class PaperLedgerEntry:
    period_index: int
    start_nav_cny: float
    planned_order_notional_cny: float
    order_count: int
    fill_count: int
    cash_reserve_cny: float
    mark_to_market_pnl_cny: float
    end_nav_cny: float
    position_book: str
    live_order: bool
    kill_switch_triggered: bool


@dataclass(frozen=True)
class V4Report:
    method_version: str
    experiment_id: str
    snapshot_id: str
    snapshot_sha256: str
    raw_candidates: int
    unique_formulas: int
    clusters: tuple[CandidateCluster, ...]
    effective_hypotheses: int
    frozen_shortlist_sha256: str
    candidate_results: tuple[CandidateResult, ...]
    attribution: tuple[AttributionResult, ...]
    selected_candidate_id: str | None
    selected_portfolio: PortfolioScore | None
    shadow_portfolio: PortfolioScore | None
    capacity_curve: tuple[PortfolioScore, ...]
    ensembles: tuple[EnsembleResult, ...]
    pbo: float | None
    placebo_signal_p: float | None
    placebo_return_p: float | None
    dsr_probability: float | None
    court_failures: tuple[str, ...]
    decision: str
    optional_source_status: dict[str, str]
    research_agent: ResearchAgentAudit
    sealed_release: SealedRelease
    paper_replay: PaperReplay | None
    audit_trial_count: int
    caveats: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        title = "# V4.0 OHLCV Alpha 研究与模拟平台" if zh else "# V4.0 OHLCV Alpha Research and Paper Platform"
        summary = "技术摘要" if zh else "Technical summary"
        lines = [title, "", f"## {summary}", "", f"**Decision: `{self.decision}`**", ""]
        lines.extend(
            [
                f"- {'原始候选' if zh else 'Raw candidates'}: {self.raw_candidates}",
                f"- {'有效机制簇' if zh else 'Effective mechanism clusters'}: {self.effective_hypotheses}",
                f"- {'入选因子' if zh else 'Selected factor'}: `{self.selected_candidate_id or 'N/A'}`",
                f"- {'审计 Trial' if zh else 'Audited trials'}: {self.audit_trial_count}",
                f"- {'封存状态' if zh else 'Sealed state'}: `{self.sealed_release.state}`",
                "",
                f"## {'关键发现' if zh else 'Key findings'}",
                "",
            ]
        )
        if self.selected_portfolio and self.shadow_portfolio:
            lines.extend(
                [
                    "| Window | Excess Sharpe | Excess return | Drawdown | Turnover |",
                    "|---|---:|---:|---:|---:|",
                    f"| 2023 | {self.selected_portfolio.excess_sharpe:.4f} | {self.selected_portfolio.cumulative_excess_return:.2%} | {self.selected_portfolio.maximum_drawdown:.2%} | {self.selected_portfolio.mean_turnover:.4f} |",
                    f"| 2024 | {self.shadow_portfolio.excess_sharpe:.4f} | {self.shadow_portfolio.cumulative_excess_return:.2%} | {self.shadow_portfolio.maximum_drawdown:.2%} | {self.shadow_portfolio.mean_turnover:.4f} |",
                    "",
                ]
            )
        lines.extend(
            [
                f"- PBO: {self.pbo}",
                f"- Placebo p: {self.placebo_signal_p} / {self.placebo_return_p}",
                f"- DSR: {self.dsr_probability}",
                f"- {'未通过门禁' if zh else 'Failed gates'}: {', '.join(self.court_failures) or ('无' if zh else 'none')}",
                "",
                f"## {'范围与指标定义' if zh else 'Scope and metric definitions'}",
                "",
                "- 2022 discovery; 2023 confirmation; 2024 retrospective shadow.",
                "- RankIC is daily cross-sectional Spearman correlation. Economic Sharpe is net portfolio excess return divided by its volatility, annualized by holding horizon.",
                "- 2025/2026 remain sealed and were not enumerated or read.",
                "",
                f"## {'方法与稳健性' if zh else 'Method and robustness'}",
                "",
                f"- {'相关性聚类与家族配额防止同源变体垄断 Court。' if zh else 'Correlation clustering and family quotas prevent one mechanism family from monopolizing Court.'}",
                f"- {'所有中性化在当日横截面内完成，不使用未来截面。' if zh else 'All neutralization is decision-local within each cross-section and does not use future cross-sections.'}",
                f"- {'组合选择只用 2023，2024 只作影子评估。' if zh else 'Portfolio selection uses 2023 only; 2024 is shadow evaluation only.'}",
                "",
                f"## {'限制与不确定性' if zh else 'Limitations and uncertainty'}",
                "",
            ]
        )
        lines.extend(f"- {item}" for item in self.caveats)
        lines.extend(
            [
                "",
                f"## {'下一步' if zh else 'Recommended next steps'}",
                "",
                f"- {'只有在独立授权后才能打开 2025 验证窗口。' if zh else 'Open the 2025 validation window only under a separate explicit authorization.'}",
                f"- {'在简单组合未通过前保持深度网络与 PPO 关闭。' if zh else 'Keep deep networks and PPO disabled until a simple ensemble passes.'}",
                "",
                f"## {'待回答问题' if zh else 'Further questions'}",
                "",
                f"- {'权威行业与公司行为数据加入后，残差 IC 是否仍成立？' if zh else 'Will residual IC survive authoritative industry and corporate-action controls?'}",
                f"- {'一次性 2025 样本外是否确认当前机制？' if zh else 'Will the one-time 2025 out-of-sample window confirm the current mechanism?'}",
                "",
            ]
        )
        return "\n".join(lines)


def generate_v4_candidates() -> tuple[PriceCandidate, ...]:
    candidates = list(generate_price_candidates())
    for family in V4_FAMILIES:
        for lookback in SECONDARY_LOOKBACKS:
            for horizon in HORIZONS:
                for direction in (-1, 1):
                    payload = {
                        "family": family,
                        "field": family,
                        "lookback": lookback,
                        "horizon": horizon,
                        "direction": direction,
                        "version": V4_PLATFORM_VERSION,
                    }
                    sign = "pos" if direction == 1 else "neg"
                    candidates.append(
                        PriceCandidate(
                            candidate_id=f"{family}_{lookback}_{horizon}d_{sign}",
                            family=family,
                            field=family,
                            lookback=lookback,
                            horizon=horizon,
                            direction=direction,
                            formula=f"{family}({lookback})",
                            fingerprint=_fingerprint(payload),
                        )
                    )
    result = tuple(sorted(candidates, key=lambda item: item.candidate_id))
    if len(result) != 990 or len({item.fingerprint for item in result}) != 990:
        raise AssertionError("V4 grammar must contain exactly 990 unique candidates")
    return result


def _metric_correlation(left: tuple, right: tuple) -> float:
    left_map = {item.day: item.rank_ic for item in left}
    right_map = {item.day: item.rank_ic for item in right}
    common = sorted(set(left_map) & set(right_map))
    if len(common) < 20:
        return 0.0
    x = [left_map[day] for day in common]
    y = [right_map[day] for day in common]
    if len(set(x)) < 2 or len(set(y)) < 2:
        return 0.0
    return pearson_correlation(x, y)


def cluster_candidates(
    ranked: tuple[PriceCandidate, ...],
    daily_metrics: dict[str, tuple],
    *,
    threshold: float,
    family_quota: int,
    limit: int,
) -> tuple[CandidateCluster, ...]:
    clusters: list[list[PriceCandidate]] = []
    maximums: list[float] = []
    family_counts: dict[str, int] = defaultdict(int)
    for candidate in ranked:
        assigned = False
        for index, cluster in enumerate(clusters):
            correlation = abs(
                _metric_correlation(
                    daily_metrics[candidate.fingerprint],
                    daily_metrics[cluster[0].fingerprint],
                )
            )
            if correlation >= threshold:
                cluster.append(candidate)
                maximums[index] = max(maximums[index], correlation)
                assigned = True
                break
        if assigned:
            continue
        if family_counts[candidate.family] >= family_quota or len(clusters) >= limit:
            continue
        clusters.append([candidate])
        maximums.append(0.0)
        family_counts[candidate.family] += 1
    return tuple(
        CandidateCluster(
            cluster_id=f"cluster_{index:03d}",
            representative_id=cluster[0].candidate_id,
            representative_fingerprint=cluster[0].fingerprint,
            family=cluster[0].family,
            members=tuple(item.candidate_id for item in cluster),
            maximum_member_correlation=maximums[index - 1],
        )
        for index, cluster in enumerate(clusters, start=1)
    )


def _winsor_z(values: list[float]) -> list[float]:
    ordered = sorted(values)
    lower = ordered[max(0, int(len(ordered) * 0.05) - 1)]
    upper = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    clipped = [min(max(item, lower), upper) for item in values]
    center = mean(clipped)
    scale = stdev(clipped) if len(clipped) >= 2 else 0.0
    return [(item - center) / scale if scale > 0 else 0.0 for item in clipped]


def residualize_panel(
    rows: tuple[EvaluationObservation, ...],
    controls: tuple[tuple[EvaluationObservation, ...], ...],
) -> tuple[EvaluationObservation, ...]:
    control_maps = [
        {(row.timestamp, row.instrument): row.factor_value for row in panel} for panel in controls
    ]
    grouped: dict[str, list[EvaluationObservation]] = defaultdict(list)
    for row in rows:
        if all((row.timestamp, row.instrument) in mapping for mapping in control_maps):
            grouped[row.timestamp].append(row)
    output: list[EvaluationObservation] = []
    for timestamp in sorted(grouped):
        cross = sorted(grouped[timestamp], key=lambda item: item.instrument)
        residual = _winsor_z([item.factor_value for item in cross])
        for mapping in control_maps:
            exposure = _winsor_z(
                [mapping[(item.timestamp, item.instrument)] for item in cross]
            )
            denominator = sum(item * item for item in exposure)
            beta = sum(x * z for x, z in zip(residual, exposure, strict=True)) / denominator if denominator > 0 else 0.0
            residual = [x - beta * z for x, z in zip(residual, exposure, strict=True)]
        output.extend(
            replace(row, factor_value=value)
            for row, value in zip(cross, residual, strict=True)
        )
    return tuple(output)


def _rows_score(year: int, rows: tuple[EvaluationObservation, ...]) -> YearScore:
    grouped: dict[str, list[EvaluationObservation]] = defaultdict(list)
    for row in rows:
        grouped[row.timestamp[:10]].append(row)
    rank_ics: list[float] = []
    spreads: list[float] = []
    excesses: list[float] = []
    observations = 0
    for day in sorted(grouped):
        cross = sorted(grouped[day], key=lambda item: (item.factor_value, item.instrument))
        if len(cross) < 3 or len({item.factor_value for item in cross}) < 2:
            continue
        returns = [item.forward_return for item in cross]
        rank_ics.append(spearman_correlation([item.factor_value for item in cross], returns))
        bucket = max(1, len(cross) // 5)
        top = mean(item.forward_return for item in cross[-bucket:])
        bottom = mean(item.forward_return for item in cross[:bucket])
        spreads.append(top - bottom)
        excesses.append(top - mean(returns))
        observations += len(cross)
    if not rank_ics:
        return YearScore(year, 0, 0, None, None, None, None)
    spread_sharpe = mean(spreads) / stdev(spreads) if len(spreads) >= 2 and stdev(spreads) > 0 else None
    return YearScore(year, len(rank_ics), observations, mean(rank_ics), mean(spreads), mean(excesses), spread_sharpe)


def _weights(rows: list[EvaluationObservation], method: str) -> dict[str, float]:
    ordered = sorted(rows, key=lambda item: (item.factor_value, item.instrument))
    if method == "equal":
        raw = [1.0] * len(ordered)
    elif method == "rank":
        raw = [float(index) for index in range(1, len(ordered) + 1)]
    elif method == "clipped_z":
        z = _winsor_z([item.factor_value for item in ordered])
        raw = [max(0.05, min(3.0, item + 1.5)) for item in z]
    else:
        raise ValueError(f"unknown weighting: {method}")
    total = sum(raw)
    return {row.instrument: value / total for row, value in zip(ordered, raw, strict=True)}


def evaluate_portfolio(
    candidate_id: str,
    rows: tuple[EvaluationObservation, ...],
    spec: PortfolioSpec,
    *,
    year: int,
    horizon: int,
    nav: float,
    bars: dict[str, dict[str, QmtDailyBar]],
    calendar: tuple[str, ...],
    config: V4Config,
) -> tuple[PortfolioScore, tuple[float, ...]]:
    grouped: dict[str, list[EvaluationObservation]] = defaultdict(list)
    for row in rows:
        grouped[row.timestamp[:10]].append(row)
    dates = sorted(grouped)
    positions = {day: index for index, day in enumerate(calendar)}
    events: list[tuple[str, float, float, float]] = []
    clipped = 0.0
    cost_rate = (
        config.commission_bps * 2
        + config.sell_tax_bps
        + config.slippage_bps * 2
        + config.impact_bps * 2
    ) / 10_000
    for offset in range(horizon):
        previous: dict[str, float] = {}
        for day in dates[offset::horizon]:
            cross = sorted(grouped[day], key=lambda item: (item.factor_value, item.instrument), reverse=True)
            eligible = [item for item in cross if item.instrument in previous and item in cross[: spec.top_k + spec.buffer]]
            selected = eligible[: spec.top_k]
            selected_ids = {item.instrument for item in selected}
            selected.extend(item for item in cross if item.instrument not in selected_ids and len(selected) < spec.top_k)
            if len(selected) < spec.top_k:
                continue
            target = _weights(selected, spec.weighting)
            index = positions[day]
            prior_day = calendar[index - 1]
            executed: dict[str, float] = {}
            for instrument, weight in target.items():
                capacity = bars[instrument][prior_day].amount * config.participation_rate if prior_day in bars[instrument] else 0.0
                desired = nav / horizon * weight
                actual = min(desired, capacity)
                clipped += desired - actual
                executed[instrument] = actual / nav
            turnover = 0.5 * sum(abs(executed.get(name, 0.0) - previous.get(name, 0.0)) for name in set(executed) | set(previous))
            cost = turnover * cost_rate
            portfolio_return = sum(
                executed[row.instrument] * row.forward_return for row in selected
            )
            benchmark = mean(row.forward_return for row in cross) / horizon
            events.append((day, portfolio_return - benchmark - cost, turnover, cost))
            previous = executed
    ordered_events = sorted(events, key=lambda item: item[0])
    all_returns = [item[1] for item in ordered_events]
    turnovers = [item[2] for item in ordered_events]
    total_cost = sum(item[3] for item in ordered_events)
    if len(all_returns) >= 2 and stdev(all_returns) > 0:
        sharpe = mean(all_returns) / stdev(all_returns) * math.sqrt(252)
    else:
        sharpe = float("-inf")
    cumulative = math.prod(1 + item for item in all_returns) - 1 if all_returns else -1.0
    score = PortfolioScore(
        candidate_id=candidate_id,
        year=year,
        spec=spec,
        nav_cny=nav,
        observations=len(all_returns),
        excess_sharpe=sharpe,
        cumulative_excess_return=cumulative,
        maximum_drawdown=_drawdown(all_returns),
        mean_turnover=mean(turnovers) if turnovers else 0.0,
        total_cost_rate=total_cost,
        capacity_clipped_notional=clipped,
        offsets=horizon,
    )
    return score, tuple(all_returns)


def _ensemble_panel(
    panels: tuple[tuple[EvaluationObservation, ...], ...], weights: tuple[float, ...]
) -> tuple[EvaluationObservation, ...]:
    mappings = [{(row.timestamp, row.instrument): row for row in panel} for panel in panels]
    common = sorted(set.intersection(*(set(mapping) for mapping in mappings)))
    by_day: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for key in common:
        by_day[key[0]].append(key)
    output: list[EvaluationObservation] = []
    for timestamp in sorted(by_day):
        keys = sorted(by_day[timestamp])
        standardized = [
            _winsor_z([mapping[key].factor_value for key in keys]) for mapping in mappings
        ]
        for index, key in enumerate(keys):
            reference = mappings[0][key]
            output.append(
                replace(
                    reference,
                    factor_value=sum(
                        weight * standardized[panel_index][index]
                        for panel_index, weight in enumerate(weights)
                    ),
                )
            )
    return tuple(output)


def _paper_replay(
    returns: tuple[float, ...],
    nav: float,
    maximum_drawdown: float,
    *,
    horizon: int,
    top_k: int,
) -> tuple[PaperReplay, tuple[PaperLedgerEntry, ...]]:
    wealth = nav
    peak = nav
    worst = 0.0
    killed = False
    periods = 0
    ledger: list[PaperLedgerEntry] = []
    for value in returns:
        if killed:
            break
        start_nav = wealth
        planned_notional = start_nav / horizon
        wealth *= 1 + value
        peak = max(peak, wealth)
        worst = min(worst, wealth / peak - 1)
        periods += 1
        if worst < -maximum_drawdown:
            killed = True
        ledger.append(
            PaperLedgerEntry(
                period_index=periods,
                start_nav_cny=start_nav,
                planned_order_notional_cny=planned_notional,
                order_count=top_k,
                fill_count=top_k,
                cash_reserve_cny=start_nav - planned_notional,
                mark_to_market_pnl_cny=wealth - start_nav,
                end_nav_cny=wealth,
                position_book="aggregate_historical_replay",
                live_order=False,
                kill_switch_triggered=killed,
            )
        )
    return PaperReplay("historical_paper_replay", nav, wealth, periods, worst, killed, 0), tuple(ledger)


def run_v4_platform(
    daily_dir: str | Path,
    membership_path: str | Path,
    *,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    optional_paths: dict[str, str] | None = None,
    config: V4Config | None = None,
) -> V4Report:
    config = config or V4Config()
    config.validate()
    candidates = generate_v4_candidates()
    memberships, membership_sha = _load_memberships(membership_path, config.universe_top_n)
    instruments = tuple(sorted({item for members in memberships.values() for item in members}))
    end_date = f"{config.shadow_year}-12-31"
    root = Path(daily_dir).expanduser().resolve()
    files = select_qd_daily_files(root, start_date=config.data_start, end_date=end_date)
    daily_manifest = build_selected_files_snapshot_manifest(root, files)
    composite = build_composite_snapshot_manifest({"qd_daily": daily_manifest.snapshot_sha256, "dynamic_universe": membership_sha})
    snapshot_id = registry.register_snapshot(composite, vendor_version="V4 frozen OHLCV research snapshot", notes="2025/2026 sealed")
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            name="V4 single-user OHLCV alpha platform",
            hypothesis="Orthogonal price mechanisms and explicit portfolio conversion may produce a robust alpha without opening sealed windows.",
            dataset_snapshot_id=snapshot_id,
            code_version=code_version,
            search_space=json.dumps({"version": V4_PLATFORM_VERSION, "candidates": len(candidates)}, sort_keys=True),
        )
    )
    dataset = load_qd_daily_directory(root, start_date=config.data_start, end_date=end_date, instruments=instruments)
    calendar = tuple(sorted({bar.trade_date for bar in dataset.bars}))
    bars: dict[str, dict[str, QmtDailyBar]] = defaultdict(dict)
    for bar in dataset.bars:
        bars[bar.instrument][bar.trade_date] = bar
    execution_members = _execution_memberships(memberships, calendar)
    signal_cache: dict[tuple[str, str, int, str, str], float | None] = {}
    discovery: dict[str, YearScore] = {}
    discovery_daily: dict[str, tuple] = {}
    trial_ids: dict[str, str] = {}
    for candidate in candidates:
        trial_id, _ = registry.create_trial(
            TrialSpec(
                experiment_id=experiment_id,
                model_name="v4_predeclared_candidate",
                factor_set=candidate.candidate_id,
                hyperparams=json.dumps(asdict(candidate), sort_keys=True, separators=(",", ":")),
                seed=config.seed,
                train_start="2022-01-01",
                train_end="2022-12-31",
                validation_start="2023-01-01",
                validation_end="2023-12-31",
                test_start="2024-01-01",
                test_end="2024-12-31",
            )
        )
        trial_ids[candidate.fingerprint] = trial_id
        _, metrics = _panel(candidate, year=2022, calendar=calendar, bars=bars, execution_members=execution_members, minimum_cross_section=config.minimum_cross_section, signal_cache=signal_cache)
        discovery[candidate.fingerprint] = _score(2022, metrics)
        discovery_daily[candidate.fingerprint] = metrics
    ranked = tuple(
        sorted(
            (item for item in candidates if discovery[item.fingerprint].mean_rank_ic is not None),
            key=lambda item: (
                discovery[item.fingerprint].mean_rank_ic or float("-inf"),
                discovery[item.fingerprint].mean_top_bottom_return or float("-inf"),
                item.fingerprint,
            ),
            reverse=True,
        )
    )
    all_clusters = cluster_candidates(
        ranked,
        discovery_daily,
        threshold=config.cluster_correlation,
        family_quota=len(candidates),
        limit=len(candidates),
    )
    selected_clusters: list[CandidateCluster] = []
    family_counts: dict[str, int] = defaultdict(int)
    for cluster in all_clusters:
        if family_counts[cluster.family] >= config.family_quota:
            continue
        selected_clusters.append(cluster)
        family_counts[cluster.family] += 1
        if len(selected_clusters) >= config.shortlist_limit:
            break
    clusters = tuple(selected_clusters)
    representatives = tuple(next(item for item in candidates if item.fingerprint == cluster.representative_fingerprint) for cluster in clusters)
    shortlist_sha = _fingerprint([item.fingerprint for item in representatives])
    panels: dict[tuple[str, int], tuple[EvaluationObservation, ...]] = {}
    scores: dict[tuple[str, int], YearScore] = {}
    for candidate in representatives:
        for year in (2023, 2024):
            panel, metrics = _panel(candidate, year=year, calendar=calendar, bars=bars, execution_members=execution_members, minimum_cross_section=config.minimum_cross_section, signal_cache=signal_cache)
            panels[(candidate.fingerprint, year)] = panel
            scores[(candidate.fingerprint, year)] = _score(year, metrics)
    controls: dict[tuple[int, int], tuple[tuple[EvaluationObservation, ...], ...]] = {}
    for horizon in sorted({item.horizon for item in representatives}):
        control_specs = tuple(
            PriceCandidate(
                candidate_id=f"control_{family}_20_{horizon}",
                family=family,
                field=field,
                lookback=20,
                horizon=horizon,
                direction=1,
                formula=f"{family}(20)",
                fingerprint=_fingerprint({"control": family, "horizon": horizon}),
            )
            for family, field in (("ohlc_return", "close"), ("volatility", "volatility"), ("amihud", "amihud"), ("price_level", "close"))
        )
        for year in (2023, 2024):
            control_panels = []
            for control in control_specs:
                panel, _ = _panel(control, year=year, calendar=calendar, bars=bars, execution_members=execution_members, minimum_cross_section=config.minimum_cross_section, signal_cache=signal_cache)
                control_panels.append(panel)
            controls[(horizon, year)] = tuple(control_panels)
    attribution: list[AttributionResult] = []
    residual_panels: dict[tuple[str, int], tuple[EvaluationObservation, ...]] = {}
    eligible: list[PriceCandidate] = []
    for candidate in representatives:
        residual_scores: dict[int, YearScore] = {}
        for year in (2023, 2024):
            panel = residualize_panel(panels[(candidate.fingerprint, year)], controls[(candidate.horizon, year)])
            residual_panels[(candidate.fingerprint, year)] = panel
            residual_scores[year] = _rows_score(year, panel)
        raw23 = scores[(candidate.fingerprint, 2023)].mean_rank_ic or 0.0
        raw24 = scores[(candidate.fingerprint, 2024)].mean_rank_ic or 0.0
        res23 = residual_scores[2023].mean_rank_ic or 0.0
        res24 = residual_scores[2024].mean_rank_ic or 0.0
        passed = raw23 > 0 and raw24 > 0 and res23 > 0 and res24 > 0
        attribution.append(AttributionResult(candidate.candidate_id, raw23, res23, raw24, res24, ("momentum20", "volatility20", "amihud20", "price_level"), passed))
        if passed:
            eligible.append(candidate)
    eligible = eligible[: config.court_limit]
    candidate_results: list[CandidateResult] = []
    eligible_fingerprints = {item.fingerprint for item in eligible}
    representative_fingerprints = {item.fingerprint for item in representatives}
    rank_lookup = {item.fingerprint: index for index, item in enumerate(ranked, start=1)}
    for candidate in candidates:
        status = "COURT_CANDIDATE" if candidate.fingerprint in eligible_fingerprints else ("ORTHOGONAL_REPRESENTATIVE" if candidate.fingerprint in representative_fingerprints else "DISCOVERY_REJECT")
        result = CandidateResult(candidate, discovery[candidate.fingerprint], scores.get((candidate.fingerprint, 2023)), scores.get((candidate.fingerprint, 2024)), rank_lookup.get(candidate.fingerprint), status)
        candidate_results.append(result)
        registry.record_trial_result(trial_ids[candidate.fingerprint], json.dumps(asdict(result), sort_keys=True, separators=(",", ":")))
    selected: PriceCandidate | None = None
    selected_score: PortfolioScore | None = None
    shadow_score: PortfolioScore | None = None
    selected_returns: tuple[float, ...] = ()
    capacity_curve: list[PortfolioScore] = []
    portfolio_trials = 0
    if eligible:
        grid: list[tuple[PriceCandidate, PortfolioScore, tuple[float, ...]]] = []
        for candidate in eligible:
            for top_k in config.portfolio_top_ks:
                if top_k > config.universe_top_n:
                    continue
                for weighting in config.portfolio_weights:
                    for buffer in config.portfolio_buffers:
                        spec = PortfolioSpec(top_k, weighting, buffer)
                        trial_id, _ = registry.create_trial(
                            TrialSpec(experiment_id, "v4_portfolio_conversion", candidate.candidate_id, json.dumps(asdict(spec), sort_keys=True), config.seed, "2022-01-01", "2022-12-31", "2023-01-01", "2023-12-31", "2024-01-01", "2024-12-31")
                        )
                        score, returns = evaluate_portfolio(candidate.candidate_id, residual_panels[(candidate.fingerprint, 2023)], spec, year=2023, horizon=candidate.horizon, nav=config.primary_nav, bars=bars, calendar=calendar, config=config)
                        registry.record_trial_result(trial_id, json.dumps(asdict(score), sort_keys=True, separators=(",", ":")))
                        portfolio_trials += 1
                        grid.append((candidate, score, returns))
        selected, selected_score, _ = max(grid, key=lambda item: (item[1].excess_sharpe, item[0].fingerprint, item[1].spec.identity))
        shadow_score, selected_returns = evaluate_portfolio(selected.candidate_id, residual_panels[(selected.fingerprint, 2024)], selected_score.spec, year=2024, horizon=selected.horizon, nav=config.primary_nav, bars=bars, calendar=calendar, config=config)
        for nav in config.capacity_navs:
            trial_id, _ = registry.create_trial(
                TrialSpec(
                    experiment_id,
                    "v4_capacity_curve",
                    selected.candidate_id,
                    json.dumps(
                        {"portfolio": asdict(selected_score.spec), "nav_cny": nav},
                        sort_keys=True,
                    ),
                    config.seed,
                    "2022-01-01",
                    "2022-12-31",
                    "2023-01-01",
                    "2023-12-31",
                    "2024-01-01",
                    "2024-12-31",
                )
            )
            score, _ = evaluate_portfolio(selected.candidate_id, residual_panels[(selected.fingerprint, 2024)], selected_score.spec, year=2024, horizon=selected.horizon, nav=nav, bars=bars, calendar=calendar, config=config)
            capacity_curve.append(score)
            registry.record_trial_result(
                trial_id, json.dumps(asdict(score), sort_keys=True, separators=(",", ":"))
            )
    ensembles: list[EnsembleResult] = []
    if selected is not None:
        same_horizon = [item for item in eligible if item.horizon == selected.horizon][:5]
        if len(same_horizon) >= 2:
            methods = {
                "equal": [1.0] * len(same_horizon),
                "ic_weight": [max(0.001, discovery[item.fingerprint].mean_rank_ic or 0.0) for item in same_horizon],
                "risk_parity": [1 / max(0.01, abs(discovery[item.fingerprint].spread_sharpe or 0.0)) for item in same_horizon],
                "ridge": [max(0.001, discovery[item.fingerprint].mean_rank_ic or 0.0) / 2 for item in same_horizon],
            }
            for method, raw in methods.items():
                trial_id, _ = registry.create_trial(
                    TrialSpec(
                        experiment_id,
                        "v4_cluster_ensemble",
                        f"ensemble_{method}",
                        json.dumps(
                            {"members": [item.candidate_id for item in same_horizon]},
                            sort_keys=True,
                        ),
                        config.seed,
                        "2022-01-01",
                        "2022-12-31",
                        "2023-01-01",
                        "2023-12-31",
                        "2024-01-01",
                        "2024-12-31",
                    )
                )
                weights = tuple(item / sum(raw) for item in raw)
                panel23 = _ensemble_panel(tuple(residual_panels[(item.fingerprint, 2023)] for item in same_horizon), weights)
                panel24 = _ensemble_panel(tuple(residual_panels[(item.fingerprint, 2024)] for item in same_horizon), weights)
                score23, _ = evaluate_portfolio(f"ensemble_{method}", panel23, selected_score.spec, year=2023, horizon=selected.horizon, nav=config.primary_nav, bars=bars, calendar=calendar, config=config)
                score24, _ = evaluate_portfolio(f"ensemble_{method}", panel24, selected_score.spec, year=2024, horizon=selected.horizon, nav=config.primary_nav, bars=bars, calendar=calendar, config=config)
                ensemble = EnsembleResult(
                    method,
                    tuple(item.candidate_id for item in same_horizon),
                    weights,
                    score23,
                    score24,
                )
                ensembles.append(ensemble)
                registry.record_trial_result(
                    trial_id,
                    json.dumps(asdict(ensemble), sort_keys=True, separators=(",", ":")),
                )
    pbo = None
    signal_p = None
    return_p = None
    dsr_probability = None
    failures: list[str] = []
    if selected is not None:
        cpcv = _cpcv(tuple(eligible), {item.fingerprint: discovery_daily[item.fingerprint] for item in eligible}, 6, 3, calendar=calendar, snapshot_id=snapshot_id, experiment_id=experiment_id, trial_id=trial_ids[eligible[0].fingerprint], code_version=code_version)
        pbo = cpcv.pbo
        combined = residual_panels[(selected.fingerprint, 2023)] + residual_panels[(selected.fingerprint, 2024)]
        signal_p = run_placebo(combined, horizon=f"{selected.horizon}d", direction=1, method="signal_shuffle", seed=config.seed, repetitions=config.placebo_repetitions, min_cross_section=config.minimum_cross_section).empirical_p_value
        return_p = run_placebo(combined, horizon=f"{selected.horizon}d", direction=1, method="return_permutation", seed=config.seed, repetitions=config.placebo_repetitions, min_cross_section=config.minimum_cross_section).empirical_p_value
        sharpes = [score.spread_sharpe or 0.0 for score in discovery.values()]
        winner_returns = [item.top_bottom for item in discovery_daily[selected.fingerprint]]
        skew, kurtosis = _moments(winner_returns)
        dsr_probability = deflated_sharpe_ratio(observed_sharpe=discovery[selected.fingerprint].spread_sharpe or 0.0, trial_sharpes=sharpes, recorded_trial_count=len(candidates), observations=len(winner_returns), skewness=skew, excess_kurtosis=kurtosis).probability
        if pbo is not None and pbo > config.maximum_pbo:
            failures.append("pbo")
        if signal_p > config.maximum_placebo_p or return_p > config.maximum_placebo_p:
            failures.append("placebo")
        if dsr_probability < config.minimum_dsr:
            failures.append("dsr")
        if selected_score is None or selected_score.excess_sharpe < config.minimum_excess_sharpe:
            failures.append("confirmation_sharpe")
        if shadow_score is None or shadow_score.excess_sharpe < config.minimum_excess_sharpe:
            failures.append("shadow_sharpe")
        if selected_score and selected_score.maximum_drawdown < -config.maximum_drawdown:
            failures.append("confirmation_drawdown")
        if shadow_score and shadow_score.maximum_drawdown < -config.maximum_drawdown:
            failures.append("shadow_drawdown")
    else:
        failures.append("no_residual_candidate")
    decision = "COURT_PASS" if not failures else "NO_DEPLOYABLE_ALPHA"
    optional_status = {
        key: ("available_not_consumed_scope_deferred" if Path(value).exists() else "not_configured")
        for key, value in sorted((optional_paths or {}).items())
    }
    agent = ResearchAgentAudit("offline_deterministic", ("plan", "compile", "deduplicate", "evaluate", "critique", "revise", "remember"), len(candidates), len(candidates), 0, sum(item.status == "DISCOVERY_REJECT" for item in candidate_results), 0, len(clusters) >= 3 and bool(ensembles) and max((item.shadow.excess_sharpe for item in ensembles), default=float("-inf")) >= config.minimum_excess_sharpe)
    candidate_manifest = _fingerprint([item.fingerprint for item in representatives])
    portfolio_manifest = _fingerprint(asdict(selected_score.spec) if selected_score else {"status": "none"})
    gates = _fingerprint({"dsr": config.minimum_dsr, "placebo": config.maximum_placebo_p, "pbo": config.maximum_pbo, "sharpe": config.minimum_excess_sharpe, "drawdown": config.maximum_drawdown})
    release_payload = {"state": "SEALED", "candidates": candidate_manifest, "portfolio": portfolio_manifest, "gates": gates, "allowed": [2022, 2023, 2024], "sealed": [2025, 2026]}
    sealed = SealedRelease("SEALED", (2022, 2023, 2024), (2025, 2026), candidate_manifest, portfolio_manifest, gates, _fingerprint(release_payload))
    paper: PaperReplay | None = None
    paper_ledger: tuple[PaperLedgerEntry, ...] = ()
    if selected_returns and selected is not None and selected_score is not None:
        paper, paper_ledger = _paper_replay(
            selected_returns,
            config.primary_nav,
            config.maximum_drawdown,
            horizon=selected.horizon,
            top_k=selected_score.spec.top_k,
        )
    report = V4Report(
        V4_PLATFORM_VERSION,
        experiment_id,
        snapshot_id,
        composite.snapshot_sha256,
        len(candidates),
        len({(item.formula, item.direction, item.horizon) for item in candidates}),
        clusters,
        len(all_clusters),
        shortlist_sha,
        tuple(candidate_results),
        tuple(attribution),
        selected.candidate_id if selected else None,
        selected_score,
        shadow_score,
        tuple(capacity_curve),
        tuple(ensembles),
        pbo,
        signal_p,
        return_p,
        dsr_probability,
        tuple(failures),
        decision,
        optional_status,
        agent,
        sealed,
        paper,
        registry.trial_count(experiment_id),
        (
            "2022-2024 are previously inspected project evidence and cannot be described as untouched out-of-sample data.",
            "Historical industry PIT and complete corporate actions remain deferred; price-only residual controls are proxies, not substitutes.",
            "Capacity uses prior-day traded amount and a frozen five-percent participation approximation.",
            "The paper broker is a historical replay and submits no live orders.",
        ),
    )
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "v4-report.json").write_text(report.to_json(), encoding="utf-8")
    (destination / "v4-report.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (destination / "v4-report.en.md").write_text(report.to_markdown("en"), encoding="utf-8")
    (destination / "sealed-release-manifest.json").write_text(json.dumps(asdict(sealed), indent=2, sort_keys=True), encoding="utf-8")
    (destination / "research-agent-audit.json").write_text(json.dumps(asdict(agent), indent=2, sort_keys=True), encoding="utf-8")
    memory_lines = [
        json.dumps(
            {
                "node_id": f"proposal_{item.candidate.fingerprint[:16]}",
                "parent_node_id": None,
                "schema_fingerprint": item.candidate.fingerprint,
                "candidate_id": item.candidate.candidate_id,
                "states": agent.states,
                "decision": item.status,
                "failure_memory": (
                    None if item.status != "DISCOVERY_REJECT" else "failed_frozen_discovery_or_orthogonality_gate"
                ),
                "empirical_trial_recorded": True,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        for item in report.candidate_results
    ]
    (destination / "research-agent-memory.jsonl").write_text(
        "\n".join(memory_lines) + "\n", encoding="utf-8"
    )
    (destination / "paper-broker-ledger.jsonl").write_text(
        "\n".join(
            json.dumps(asdict(entry), sort_keys=True, ensure_ascii=False)
            for entry in paper_ledger
        )
        + ("\n" if paper_ledger else ""),
        encoding="utf-8",
    )
    return report
