from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from statistics import mean, stdev

from stephen_quant.baseline import BaselineObservation
from stephen_quant.discovery import FactorSchema
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
from stephen_quant.qmt import (
    QdAlternativeConfig,
    QdAlternativeDataset,
    QmtDailyBar,
    QmtDataError,
    build_multisource_factor_observations,
    load_qd_alternative_directory,
    load_qd_daily_directory,
    select_qd_daily_files,
)

from .price_discovery_lab import (
    HORIZONS,
    PriceCandidate,
    YearScore,
    _cpcv,
    _drawdown,
    _execution_memberships,
    _load_memberships,
    _moments,
    _panel,
    _score,
)
from .v4_ohlcv_platform import (
    CandidateCluster,
    SealedRelease,
    cluster_candidates,
    residualize_panel,
)

V41_VERSION = "v4.1-semantic-a-share-alpha-1.0.0"
DAILY_MECHANISMS = {
    "t1_delayed_feedback": (
        "negative_return_with_abnormal_turnover",
        "prior_close_and_amount",
        "T+1 delayed feedback may create next-session reversal after volume-confirmed losses.",
    ),
    "negative_return_asymmetry": (
        "asymmetric_loss_pressure",
        "prior_close",
        "Negative and positive return histories may transmit differently under retail feedback.",
    ),
    "overnight_intraday_divergence": (
        "overnight_intraday_divergence",
        "prior_open_and_close",
        "Overnight information and intraday price pressure can have different persistence.",
    ),
    "gap_fill_pressure": (
        "gap_filling",
        "prior_open_and_close",
        "The interaction between overnight gaps and intraday repair may reveal delayed absorption.",
    ),
    "limit_proximity": (
        "price_limit_proximity",
        "prior_board_rule_and_close",
        "Board-specific price-limit proximity may delay price discovery.",
    ),
    "limit_exhaustion": (
        "price_limit_exhaustion",
        "prior_board_rule_open_and_close",
        "Intraday retreat after approaching an upper limit may identify exhausted attention.",
    ),
}
ALTERNATIVE_MECHANISMS = {
    "auction_strength": (
        "auction",
        "mean(auction_return, {lookback})",
        ("auction_return",),
        ("qd_auction",),
        "opening_auction_demand",
        "same_day_auction_available_0926",
    ),
    "auction_amount_intensity": (
        "auction",
        "mean(auction_amount, {lookback}) / (mean(amount, {lookback}) + 1.0)",
        ("amount", "auction_amount"),
        ("qd_daily", "qd_auction"),
        "opening_auction_liquidity",
        "same_day_auction_and_prior_amount",
    ),
    "fund_flow_intensity": (
        "fund_flow",
        "mean(net_inflow_amount, {lookback}) / (mean(amount, {lookback}) + 1.0)",
        ("amount", "net_inflow_amount"),
        ("qd_daily", "qd_fund_flow"),
        "close_flow_pressure",
        "prior_session_close_flow",
    ),
    "margin_buy_intensity": (
        "margin",
        "mean(margin_financing_buy, {lookback}) / (mean(amount, {lookback}) + 1.0)",
        ("amount", "margin_financing_buy"),
        ("qd_daily", "qd_margin"),
        "margin_financing_demand",
        "prior_session_margin_publication",
    ),
    "margin_balance_change": (
        "margin",
        "period_return(margin_financing_balance, {lookback})",
        ("margin_financing_balance",),
        ("qd_margin",),
        "margin_balance_acceleration",
        "prior_session_margin_publication",
    ),
    "limit_event_persistence": (
        "limit_event",
        "mean(kpl_limit_up_flag, {lookback})",
        ("kpl_limit_up_flag",),
        ("qd_limit_event",),
        "observed_limit_up_persistence",
        "prior_session_limit_event",
    ),
}


@dataclass(frozen=True)
class V41Config:
    data_start: str = "2021-01-01"
    discovery_year: int = 2022
    confirmation_year: int = 2023
    shadow_year: int = 2024
    universe_top_n: int = 50
    minimum_cross_section: int = 10
    lookbacks: tuple[int, ...] = (5, 20, 60)
    alternative_horizons: tuple[int, ...] = (1, 5, 20)
    shortlist_limit: int = 40
    family_quota: int = 4
    usage_candidate_limit: int = 12
    usage_breadths: tuple[int, ...] = (5, 10, 20)
    usages: tuple[str, ...] = ("BUY", "AVOID", "TIMING")
    regime_policies: tuple[str, ...] = ("all", "risk_on", "risk_off")
    minimum_active_days: int = 60
    placebo_repetitions: int = 199
    seed: int = 42
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
    cluster_correlation: float = 0.85
    minimum_dsr: float = 0.95
    maximum_placebo_p: float = 0.05
    maximum_pbo: float = 0.20
    minimum_excess_sharpe: float = 0.50
    maximum_drawdown: float = 0.25
    high_volatility: float = 0.018
    high_correlation: float = 0.45
    liquidity_shock_ratio: float = 1.25
    ingested_at: str = "2026-08-18T00:00:00+08:00"

    def validate(self) -> None:
        if (self.discovery_year, self.confirmation_year, self.shadow_year) != (2022, 2023, 2024):
            raise ValueError("V4.1 windows are frozen to 2022/2023/2024")
        if self.usages != ("BUY", "AVOID", "TIMING"):
            raise ValueError("V4.1 usage identities are frozen")
        if self.regime_policies != ("all", "risk_on", "risk_off"):
            raise ValueError("V4.1 regime policies are frozen")
        if self.primary_nav not in self.capacity_navs:
            raise ValueError("primary NAV must appear in the capacity curve")
        if self.shortlist_limit < self.usage_candidate_limit or self.family_quota < 1:
            raise ValueError("invalid V4.1 search budget")


@dataclass(frozen=True)
class SemanticCandidate:
    candidate_id: str
    event: str
    context: str
    quality: str
    direction: int
    output: str
    family: str
    source_kind: str
    lookback: int
    horizon: int
    formula: str
    required_fields: tuple[str, ...]
    data_sources: tuple[str, ...]
    economic_rationale: str
    fingerprint: str

    def validate(self) -> None:
        if self.direction not in {-1, 1} or self.output != "UNASSIGNED":
            raise ValueError("invalid semantic direction or pre-evaluation output")
        if not all((self.event, self.context, self.quality, self.family, self.formula)):
            raise ValueError("semantic identity fields cannot be empty")
        if len(self.fingerprint) != 64:
            raise ValueError("semantic candidate requires SHA-256 identity")

    def price_proxy(self) -> PriceCandidate:
        return PriceCandidate(
            self.candidate_id,
            self.family,
            self.family,
            self.lookback,
            self.horizon,
            self.direction,
            self.formula,
            self.fingerprint,
        )

    def factor_schema(self) -> FactorSchema:
        horizon = "next_open" if self.horizon == 1 else f"{self.horizon}d"
        schema = FactorSchema(
            schema_id=self.candidate_id,
            version="4.1.0",
            name=self.candidate_id.replace("_", " ").title(),
            event=self.event,
            context=self.context,
            quality=self.quality,
            direction=self.direction,
            output=self.output,
            horizon=horizon,  # type: ignore[arg-type]
            formula=self.formula,
            data_sources=self.data_sources,
            required_fields=self.required_fields,
            availability_lag_days=0,
            economic_rationale=self.economic_rationale,
        )
        schema.validate()
        return schema


@dataclass(frozen=True)
class RegimeState:
    decision_date: str
    state: str
    trend: float
    breadth: float
    volatility: float
    average_correlation: float
    liquidity_ratio: float
    information_end_date: str


@dataclass(frozen=True)
class QuantilePoint:
    quantile: int
    mean_return: float


@dataclass(frozen=True)
class RegimeEvidence:
    regime: str
    dates: int
    rank_ic: float | None
    top_excess_return: float | None


@dataclass(frozen=True)
class EconomicShape:
    candidate_id: str
    year: int
    dates: int
    observations: int
    rank_ic: float | None
    quantiles: tuple[QuantilePoint, ...]
    monotonicity: float | None
    top_leg_return: float | None
    bottom_leg_return: float | None
    benchmark_return: float | None
    top_excess_return: float | None
    bottom_excess_return: float | None
    long_short_spread: float | None
    top_decile_absolute_date_contribution_share: float | None
    positive_regime_share: float
    regimes: tuple[RegimeEvidence, ...]
    positive_ic_negative_long_leg: bool


@dataclass(frozen=True)
class SearchScore:
    candidate_id: str
    fingerprint: str
    family: str
    objective: float
    rank_ic_percentile: float
    top_leg_percentile: float
    monotonicity_percentile: float
    regime_percentile: float
    novelty_percentile: float
    concentration_penalty: float
    complexity_penalty: float


@dataclass(frozen=True)
class UsageSpec:
    usage: str
    breadth: int
    regime: str

    @property
    def identity(self) -> str:
        return f"{self.usage.lower()}_breadth{self.breadth}_{self.regime}"


@dataclass(frozen=True)
class UsageScore:
    candidate_id: str
    year: int
    spec: UsageSpec
    nav_cny: float
    active_days: int
    observations: int
    excess_sharpe: float
    cumulative_excess_return: float
    maximum_drawdown: float
    mean_turnover: float
    total_cost_rate: float
    capacity_clipped_notional: float
    objective_after_complexity: float


@dataclass(frozen=True)
class SourceStatus:
    source_kind: str
    status: str
    files: int
    rows: int
    snapshot_sha256: str | None
    availability_policy: str | None


@dataclass(frozen=True)
class V41Report:
    method_version: str
    experiment_id: str
    snapshot_id: str
    snapshot_sha256: str
    proposed_candidates: int
    empirically_evaluated_candidates: int
    effective_hypotheses: int
    source_status: tuple[SourceStatus, ...]
    search_scores: tuple[SearchScore, ...]
    clusters: tuple[CandidateCluster, ...]
    discovery_shapes: tuple[EconomicShape, ...]
    confirmation_shapes: tuple[EconomicShape, ...]
    shadow_shapes: tuple[EconomicShape, ...]
    selected_candidate_id: str | None
    selected_usage: UsageScore | None
    shadow_usage: UsageScore | None
    capacity_curve: tuple[UsageScore, ...]
    pbo: float | None
    placebo_signal_p: float | None
    placebo_return_p: float | None
    dsr_probability: float | None
    court_failures: tuple[str, ...]
    decision: str
    semantic_manifest_sha256: str
    search_manifest_sha256: str
    sealed_release: SealedRelease
    audit_trial_count: int
    caveats: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        lines = [
            "# V4.1 A股语义 Alpha 搜索与经济转换报告" if zh else "# V4.1 A-share Semantic Alpha Search and Economic Conversion",
            "",
            f"**{'结论' if zh else 'Decision'}: `{self.decision}`**",
            "",
            f"- {'候选提案' if zh else 'Candidate proposals'}: {self.proposed_candidates}",
            f"- {'真实评估候选' if zh else 'Empirically evaluated'}: {self.empirically_evaluated_candidates}",
            f"- {'有效机制簇' if zh else 'Effective hypotheses'}: {self.effective_hypotheses}",
            f"- {'审计 Trial' if zh else 'Audited Trials'}: {self.audit_trial_count}",
            f"- {'入选候选' if zh else 'Selected candidate'}: `{self.selected_candidate_id or 'N/A'}`",
            "",
            f"## {'数据来源' if zh else 'Data sources'}",
            "",
            "| Source | Status | Files | Rows |",
            "|---|---|---:|---:|",
        ]
        lines.extend(
            f"| {item.source_kind} | {item.status} | {item.files} | {item.rows} |"
            for item in self.source_status
        )
        lines.extend(["", f"## {'经济转换' if zh else 'Economic conversion'}", ""])
        if self.selected_usage and self.shadow_usage:
            lines.extend(
                [
                    f"- {'用途' if zh else 'Usage'}: `{self.selected_usage.spec.usage}`",
                    f"- {'配置' if zh else 'Frozen mapping'}: `{self.selected_usage.spec.identity}`",
                    "",
                    "| Window | Excess Sharpe | Excess return | Drawdown | Active days |",
                    "|---|---:|---:|---:|---:|",
                    f"| 2023 | {self.selected_usage.excess_sharpe:.4f} | {self.selected_usage.cumulative_excess_return:.2%} | {self.selected_usage.maximum_drawdown:.2%} | {self.selected_usage.active_days} |",
                    f"| 2024 | {self.shadow_usage.excess_sharpe:.4f} | {self.shadow_usage.cumulative_excess_return:.2%} | {self.shadow_usage.maximum_drawdown:.2%} | {self.shadow_usage.active_days} |",
                ]
            )
        lines.extend(
            [
                "",
                f"- PBO: {self.pbo}",
                f"- Placebo p: {self.placebo_signal_p} / {self.placebo_return_p}",
                f"- DSR: {self.dsr_probability}",
                f"- {'失败门禁' if zh else 'Failed gates'}: {', '.join(self.court_failures) or ('无' if zh else 'none')}",
                "",
                f"## {'IC 与多头端诊断' if zh else 'IC-to-long-leg diagnosis'}",
                "",
                "| Candidate | Year | RankIC | Top excess | Bottom excess | Monotonicity | Contradiction |",
                "|---|---:|---:|---:|---:|---:|---|",
            ]
        )
        diagnostic = sorted(
            (*self.confirmation_shapes, *self.shadow_shapes),
            key=lambda item: (item.candidate_id, item.year),
        )[:30]
        for item in diagnostic:
            fmt = lambda value: "N/A" if value is None else f"{value:.6f}"
            lines.append(
                f"| `{item.candidate_id}` | {item.year} | {fmt(item.rank_ic)} | "
                f"{fmt(item.top_excess_return)} | {fmt(item.bottom_excess_return)} | "
                f"{fmt(item.monotonicity)} | {item.positive_ic_negative_long_leg} |"
            )
        lines.extend(["", f"## {'限制' if zh else 'Limitations'}", ""])
        lines.extend(f"- {item}" for item in self.caveats)
        lines.append("")
        return "\n".join(lines)


def _hash(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def generate_v41_candidates(config: V41Config | None = None) -> tuple[SemanticCandidate, ...]:
    config = config or V41Config()
    config.validate()
    result: list[SemanticCandidate] = []
    for family, (event, quality, rationale) in DAILY_MECHANISMS.items():
        for lookback in config.lookbacks:
            for horizon in HORIZONS:
                for direction in (-1, 1):
                    sign = "pos" if direction == 1 else "neg"
                    identity = {
                        "event": event,
                        "context": "all_prior_information_states",
                        "quality": quality,
                        "direction": direction,
                        "output": "UNASSIGNED",
                        "family": family,
                        "source_kind": "daily",
                        "lookback": lookback,
                        "horizon": horizon,
                        "version": V41_VERSION,
                    }
                    result.append(
                        SemanticCandidate(
                            f"{family}_{lookback}_{horizon}d_{sign}",
                            event,
                            "all_prior_information_states",
                            quality,
                            direction,
                            "UNASSIGNED",
                            family,
                            "daily",
                            lookback,
                            horizon,
                            f"{family}({lookback})",
                            ("open", "close", "amount"),
                            ("qd_daily",),
                            rationale,
                            _hash(identity),
                        )
                    )
    for family, (
        source_kind,
        template,
        required_fields,
        data_sources,
        event,
        quality,
    ) in ALTERNATIVE_MECHANISMS.items():
        for lookback in config.lookbacks:
            for horizon in config.alternative_horizons:
                for direction in (-1, 1):
                    sign = "pos" if direction == 1 else "neg"
                    formula = template.format(lookback=lookback)
                    identity = {
                        "event": event,
                        "context": "all_prior_information_states",
                        "quality": quality,
                        "direction": direction,
                        "output": "UNASSIGNED",
                        "family": family,
                        "source_kind": source_kind,
                        "lookback": lookback,
                        "horizon": horizon,
                        "formula": formula,
                        "version": V41_VERSION,
                    }
                    result.append(
                        SemanticCandidate(
                            f"{family}_{lookback}_{horizon}d_{sign}",
                            event,
                            "all_prior_information_states",
                            quality,
                            direction,
                            "UNASSIGNED",
                            family,
                            source_kind,
                            lookback,
                            horizon,
                            formula,
                            tuple(sorted(required_fields)),
                            tuple(data_sources),
                            f"{event} may contain incremental information under A-share trading constraints.",
                            _hash(identity),
                        )
                    )
    ordered = tuple(sorted(result, key=lambda item: item.candidate_id))
    for item in ordered:
        item.validate()
        if item.source_kind != "daily":
            item.factor_schema()
    if len(ordered) != 288 or len({item.fingerprint for item in ordered}) != 288:
        raise AssertionError("V4.1 semantic grammar must contain 288 unique candidates")
    return ordered


def classify_prior_regimes(
    *,
    calendar: tuple[str, ...],
    bars: dict[str, dict[str, QmtDailyBar]],
    execution_members: dict[str, tuple[str, ...]],
    config: V41Config,
) -> dict[str, RegimeState]:
    daily_returns: dict[str, dict[str, float]] = defaultdict(dict)
    market_return: dict[str, float] = {}
    breadth: dict[str, float] = {}
    total_amount: dict[str, float] = {}
    for index, day in enumerate(calendar):
        if index == 0:
            continue
        prior = calendar[index - 1]
        values: list[float] = []
        amounts: list[float] = []
        for instrument in execution_members.get(day, ()):
            series = bars.get(instrument, {})
            if day not in series or prior not in series or series[prior].close <= 0:
                continue
            value = series[day].close / series[prior].close - 1
            if math.isfinite(value):
                daily_returns[day][instrument] = value
                values.append(value)
                amounts.append(max(series[day].amount, 0.0))
        if values:
            market_return[day] = mean(values)
            breadth[day] = sum(value > 0 for value in values) / len(values)
            total_amount[day] = sum(amounts)
    states: dict[str, RegimeState] = {}
    for index, day in enumerate(calendar):
        if index < 21:
            continue
        history = calendar[index - 20 : index]
        if any(item not in market_return for item in history):
            continue
        market = [market_return[item] for item in history]
        trend = mean(market)
        vol = stdev(market) if len(market) >= 2 else 0.0
        breadth_value = mean(breadth[item] for item in history)
        correlations: list[float] = []
        members = execution_members.get(day, ())
        for instrument in members:
            values = [daily_returns[item].get(instrument) for item in history]
            if any(value is None for value in values):
                continue
            vector = [float(value) for value in values if value is not None]
            if len(set(vector)) < 2 or len(set(market)) < 2:
                continue
            correlations.append(pearson_correlation(vector, market))
        average_correlation = mean(correlations) if correlations else 0.0
        base_amounts = [total_amount[item] for item in history[:-1] if total_amount[item] > 0]
        liquidity_ratio = (
            total_amount[history[-1]] / mean(base_amounts)
            if base_amounts and total_amount[history[-1]] > 0
            else 1.0
        )
        if liquidity_ratio >= config.liquidity_shock_ratio:
            state = "liquidity_shock"
        elif trend < 0 and (
            vol >= config.high_volatility or average_correlation >= config.high_correlation
        ):
            state = "risk_off"
        elif trend >= 0 and breadth_value >= 0.5 and average_correlation < config.high_correlation:
            state = "risk_on"
        else:
            state = "mixed"
        states[day] = RegimeState(
            day,
            state,
            trend,
            breadth_value,
            vol,
            average_correlation,
            liquidity_ratio,
            history[-1],
        )
    return states


def economic_shape(
    candidate_id: str,
    rows: tuple[EvaluationObservation, ...],
    *,
    year: int,
    regimes: dict[str, RegimeState],
    quantiles: int = 10,
) -> EconomicShape:
    grouped: dict[str, list[EvaluationObservation]] = defaultdict(list)
    for row in rows:
        grouped[row.timestamp[:10]].append(row)
    quantile_daily: dict[int, list[float]] = defaultdict(list)
    rank_ics: list[float] = []
    daily_spreads: list[float] = []
    regime_panels: dict[str, list[tuple[float, float]]] = defaultdict(list)
    regime_dates: dict[str, set[str]] = defaultdict(set)
    observations = 0
    dates = 0
    for day in sorted(grouped):
        cross = sorted(grouped[day], key=lambda item: (item.factor_value, item.instrument))
        if len(cross) < quantiles or len({item.factor_value for item in cross}) < 2:
            continue
        signals = [item.factor_value for item in cross]
        returns = [item.forward_return for item in cross]
        rank_ics.append(spearman_correlation(signals, returns))
        buckets: dict[int, list[float]] = defaultdict(list)
        for index, item in enumerate(cross):
            bucket = min(index * quantiles // len(cross), quantiles - 1) + 1
            buckets[bucket].append(item.forward_return)
        if len(buckets) != quantiles:
            continue
        means = {key: mean(value) for key, value in buckets.items()}
        for key, value in means.items():
            quantile_daily[key].append(value)
        daily_spreads.append(means[quantiles] - means[1])
        state = regimes.get(day)
        regime_name = state.state if state else "unclassified"
        regime_panels[regime_name].extend(zip(signals, returns, strict=True))
        regime_dates[regime_name].add(day)
        observations += len(cross)
        dates += 1
    if not dates:
        return EconomicShape(
            candidate_id,
            year,
            0,
            0,
            None,
            (),
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            0.0,
            (),
            False,
        )
    points = tuple(
        QuantilePoint(index, mean(quantile_daily[index])) for index in range(1, quantiles + 1)
    )
    values = [item.mean_return for item in points]
    monotonicity = spearman_correlation(list(range(1, quantiles + 1)), values)
    benchmark = mean(values)
    absolute = sorted((abs(value) for value in daily_spreads), reverse=True)
    tail = max(1, math.ceil(len(absolute) * 0.10))
    concentration = sum(absolute[:tail]) / sum(absolute) if sum(absolute) else 0.0
    regime_evidence: list[RegimeEvidence] = []
    for name, panel in sorted(regime_panels.items()):
        if len(panel) < 10:
            continue
        signals = [item[0] for item in panel]
        returns = [item[1] for item in panel]
        rank_ic = spearman_correlation(signals, returns) if len(set(signals)) >= 2 else None
        ordered = sorted(panel)
        bucket = max(1, len(ordered) // 5)
        top_excess = mean(item[1] for item in ordered[-bucket:]) - mean(returns)
        regime_evidence.append(
            RegimeEvidence(name, len(regime_dates[name]), rank_ic, top_excess)
        )
    positive = sum(
        item.rank_ic is not None
        and item.rank_ic > 0
        and item.top_excess_return is not None
        and item.top_excess_return > 0
        for item in regime_evidence
    )
    rank_ic = mean(rank_ics)
    top = values[-1]
    bottom = values[0]
    return EconomicShape(
        candidate_id,
        year,
        dates,
        observations,
        rank_ic,
        points,
        monotonicity,
        top,
        bottom,
        benchmark,
        top - benchmark,
        bottom - benchmark,
        top - bottom,
        concentration,
        positive / len(regime_evidence) if regime_evidence else 0.0,
        tuple(regime_evidence),
        rank_ic > 0 and top - benchmark <= 0,
    )


def _percentiles(values: dict[str, float]) -> dict[str, float]:
    """Return tie-aware ascending percentile scores without identity-based fake edges."""
    distinct = sorted(set(values.values()))
    denominator = max(len(distinct) - 1, 1)
    ranks = {value: index / denominator for index, value in enumerate(distinct)}
    return {key: ranks[value] for key, value in values.items()}


def multi_objective_scores(
    candidates: tuple[SemanticCandidate, ...],
    shapes: dict[str, EconomicShape],
) -> tuple[SearchScore, ...]:
    valid = [item for item in candidates if shapes[item.fingerprint].rank_ic is not None]
    rank_ic = {
        item.fingerprint: (
            shapes[item.fingerprint].rank_ic
            if shapes[item.fingerprint].rank_ic is not None
            else -1.0
        )
        for item in valid
    }
    top = {
        item.fingerprint: (
            shapes[item.fingerprint].top_excess_return
            if shapes[item.fingerprint].top_excess_return is not None
            else -1.0
        )
        for item in valid
    }
    monotonicity = {
        item.fingerprint: (
            shapes[item.fingerprint].monotonicity
            if shapes[item.fingerprint].monotonicity is not None
            else -1.0
        )
        for item in valid
    }
    regime = {item.fingerprint: shapes[item.fingerprint].positive_regime_share for item in valid}
    concentration = {
        item.fingerprint: shapes[item.fingerprint].top_decile_absolute_date_contribution_share or 1.0
        for item in valid
    }
    complexity = {
        item.fingerprint: math.log1p(item.lookback) + (0.75 if item.source_kind != "daily" else 0.0)
        for item in valid
    }
    family_size: dict[str, int] = defaultdict(int)
    for item in valid:
        family_size[item.family] += 1
    novelty_raw = {item.fingerprint: 1 / family_size[item.family] for item in valid}
    ranks = {
        "rank": _percentiles(rank_ic),
        "top": _percentiles(top),
        "mono": _percentiles(monotonicity),
        "regime": _percentiles(regime),
        "novelty": _percentiles(novelty_raw),
        "concentration": _percentiles(concentration),
        "complexity": _percentiles(complexity),
    }
    result = []
    for item in valid:
        key = item.fingerprint
        objective = (
            0.25 * ranks["rank"][key]
            + 0.25 * ranks["top"][key]
            + 0.15 * ranks["mono"][key]
            + 0.15 * ranks["regime"][key]
            + 0.10 * ranks["novelty"][key]
            - 0.05 * ranks["concentration"][key]
            - 0.05 * ranks["complexity"][key]
        )
        result.append(
            SearchScore(
                item.candidate_id,
                key,
                item.family,
                objective,
                ranks["rank"][key],
                ranks["top"][key],
                ranks["mono"][key],
                ranks["regime"][key],
                ranks["novelty"][key],
                ranks["concentration"][key],
                ranks["complexity"][key],
            )
        )
    return tuple(sorted(result, key=lambda item: (item.objective, item.fingerprint), reverse=True))


def _anchors(
    *,
    year: int,
    horizon: int,
    calendar: tuple[str, ...],
    bars: dict[str, dict[str, QmtDailyBar]],
    execution_members: dict[str, tuple[str, ...]],
    adv_lookback: int = 20,
) -> tuple[BaselineObservation, ...]:
    positions = {day: index for index, day in enumerate(calendar)}
    rows: list[BaselineObservation] = []
    for day in calendar:
        if not f"{year}-01-01" <= day <= f"{year}-12-31":
            continue
        index = positions[day]
        if index < adv_lookback or index + horizon >= len(calendar):
            continue
        history_days = calendar[index - adv_lookback : index]
        prior = history_days[-1]
        end_day = calendar[index + horizon]
        for instrument in execution_members.get(day, ()):
            series = bars.get(instrument, {})
            if any(item not in series for item in (*history_days, day, end_day)):
                continue
            execution, end = series[day], series[end_day]
            if execution.open <= 0 or end.open <= 0:
                continue
            adv = mean(series[item].amount for item in history_days)
            if adv <= 0:
                continue
            rows.append(
                BaselineObservation(
                    instrument,
                    0.0,
                    f"{prior}T15:00:00+08:00",
                    f"{prior}T15:01:00+08:00",
                    adv,
                    f"{prior}T15:01:00+08:00",
                    f"{day}T09:30:00+08:00",
                    f"{end_day}T09:30:00+08:00",
                    end.open / execution.open - 1,
                    execution.can_buy_open,
                    end.can_sell_open,
                    execution.tradability_reason,
                    execution.can_buy_open and end.can_sell_open,
                )
            )
    return tuple(rows)


def _alternative_panel(
    candidate: SemanticCandidate,
    *,
    year: int,
    daily_bars: tuple[QmtDailyBar, ...],
    dataset: QdAlternativeDataset,
    anchors: tuple[BaselineObservation, ...],
) -> tuple[tuple[EvaluationObservation, ...], tuple]:
    definition = candidate.factor_schema().compile()
    built = build_multisource_factor_observations(
        daily_bars,
        {candidate.source_kind: dataset.observations},
        definition,
        anchors,
    )
    rows = tuple(
        EvaluationObservation(
            timestamp=row.execution_at,
            instrument=row.instrument,
            factor_value=candidate.direction * row.signal,
            factor_available_at=row.signal_available_at,
            label_start_at=row.execution_at,
            label_end_at=row.return_end_at,
            forward_return=row.forward_return,
            horizon=f"{candidate.horizon}d",
            subperiod=str(year),
            regime="unspecified",
        )
        for row in built
        if row.eligible
    )
    return rows, _daily_metrics(rows)


def _daily_metrics(rows: tuple[EvaluationObservation, ...]) -> tuple:
    from .price_discovery_lab import _DailyMetric

    grouped: dict[str, list[EvaluationObservation]] = defaultdict(list)
    for row in rows:
        grouped[row.timestamp[:10]].append(row)
    metrics = []
    for day in sorted(grouped):
        cross = sorted(grouped[day], key=lambda item: (item.factor_value, item.instrument))
        if len(cross) < 3 or len({item.factor_value for item in cross}) < 2:
            continue
        returns = [item.forward_return for item in cross]
        bucket = max(1, len(cross) // 5)
        metrics.append(
            _DailyMetric(
                day,
                spearman_correlation([item.factor_value for item in cross], returns),
                mean(item.forward_return for item in cross[-bucket:])
                - mean(item.forward_return for item in cross[:bucket]),
                mean(item.forward_return for item in cross[-bucket:]) - mean(returns),
                len(cross),
            )
        )
    return tuple(metrics)


def _mirror_panel(
    rows: tuple[EvaluationObservation, ...],
) -> tuple[EvaluationObservation, ...]:
    return tuple(replace(row, factor_value=-row.factor_value) for row in rows)


def evaluate_usage(
    candidate_id: str,
    rows: tuple[EvaluationObservation, ...],
    base_rows: tuple[EvaluationObservation, ...],
    spec: UsageSpec,
    *,
    year: int,
    horizon: int,
    nav: float,
    bars: dict[str, dict[str, QmtDailyBar]],
    calendar: tuple[str, ...],
    regimes: dict[str, RegimeState],
    config: V41Config,
) -> tuple[UsageScore, tuple[float, ...]]:
    grouped: dict[str, list[EvaluationObservation]] = defaultdict(list)
    base_grouped: dict[str, list[EvaluationObservation]] = defaultdict(list)
    for row in rows:
        grouped[row.timestamp[:10]].append(row)
    for row in base_rows:
        base_grouped[row.timestamp[:10]].append(row)
    positions = {day: index for index, day in enumerate(calendar)}
    events: list[tuple[str, float, float, float, bool]] = []
    clipped = 0.0
    cost_rate = (
        config.commission_bps * 2
        + config.sell_tax_bps
        + config.slippage_bps * 2
        + config.impact_bps * 2
    ) / 10_000
    dates = sorted(set(grouped) & set(base_grouped))
    for offset in range(horizon):
        previous: dict[str, float] = {}
        for day in dates[offset::horizon]:
            cross = sorted(grouped[day], key=lambda item: (item.factor_value, item.instrument))
            if len(cross) <= spec.breadth or day not in positions or positions[day] == 0:
                continue
            benchmark = mean(item.forward_return for item in cross) / horizon
            active = spec.regime == "all" or regimes.get(day, RegimeState(day, "unclassified", 0, 0, 0, 0, 1, day)).state == spec.regime
            selected: list[EvaluationObservation] = []
            raw_weights: dict[str, float] = {}
            if active and spec.usage == "BUY":
                selected = list(reversed(cross[-spec.breadth :]))
                raw_weights = {item.instrument: 1 / len(selected) for item in selected}
            elif active and spec.usage == "AVOID":
                selected = cross[spec.breadth :]
                raw_weights = {item.instrument: 1 / len(selected) for item in selected}
            elif active and spec.usage == "TIMING":
                timing = {item.instrument: item.factor_value for item in cross}
                threshold = sorted(timing.values())[len(timing) // 2]
                base = sorted(
                    base_grouped[day],
                    key=lambda item: (item.factor_value, item.instrument),
                    reverse=True,
                )[: spec.breadth]
                selected = [item for item in base if timing.get(item.instrument, -math.inf) >= threshold]
                raw_weights = {item.instrument: 1 / spec.breadth for item in selected}
            elif active:
                raise ValueError(f"unknown V4.1 usage: {spec.usage}")
            executed: dict[str, float] = {}
            prior_day = calendar[positions[day] - 1]
            by_id = {item.instrument: item for item in cross}
            for instrument, weight in raw_weights.items():
                series = bars.get(instrument, {})
                capacity = series[prior_day].amount * config.participation_rate if prior_day in series else 0.0
                desired = nav / horizon * weight
                actual = min(desired, capacity)
                clipped += desired - actual
                executed[instrument] = actual / nav
            turnover = 0.5 * sum(
                abs(executed.get(name, 0.0) - previous.get(name, 0.0))
                for name in set(executed) | set(previous)
            )
            cost = turnover * cost_rate
            portfolio_return = sum(
                weight * by_id[instrument].forward_return
                for instrument, weight in executed.items()
                if instrument in by_id
            )
            events.append((day, portfolio_return - benchmark - cost, turnover, cost, active))
            previous = executed
    ordered = sorted(events, key=lambda item: item[0])
    returns = [item[1] for item in ordered]
    sharpe = (
        mean(returns) / stdev(returns) * math.sqrt(252)
        if len(returns) >= 2 and stdev(returns) > 0
        else float("-inf")
    )
    complexity = 0.15 if spec.regime != "all" else 0.0
    score = UsageScore(
        candidate_id,
        year,
        spec,
        nav,
        sum(item[4] for item in ordered),
        len(returns),
        sharpe,
        math.prod(1 + item for item in returns) - 1 if returns else -1.0,
        _drawdown(returns),
        mean(item[2] for item in ordered) if ordered else 0.0,
        sum(item[3] for item in ordered),
        clipped,
        sharpe - complexity,
    )
    return score, tuple(returns)


def _load_sources(
    optional_paths: dict[str, str],
    *,
    instruments: tuple[str, ...],
    config: V41Config,
) -> tuple[dict[str, QdAlternativeDataset], tuple[SourceStatus, ...]]:
    key_to_kind = {
        "qd_auction_dir": "auction",
        "qd_fund_flow_dir": "fund_flow",
        "qd_margin_dir": "margin",
        "qd_limit_event_dir": "limit_event",
    }
    datasets: dict[str, QdAlternativeDataset] = {}
    statuses: list[SourceStatus] = []
    for key, kind in key_to_kind.items():
        path = optional_paths.get(key)
        if not path or not Path(path).is_dir():
            statuses.append(SourceStatus(kind, "not_configured", 0, 0, None, None))
            continue
        try:
            dataset = load_qd_alternative_directory(
                path,
                QdAlternativeConfig(
                    source_kind=kind,  # type: ignore[arg-type]
                    start_date=config.data_start,
                    end_date=f"{config.shadow_year}-12-31",
                    ingested_at=config.ingested_at,
                    instruments=instruments,
                ),
            )
        except QmtDataError as exc:
            statuses.append(
                SourceStatus(kind, f"rejected:{type(exc).__name__}", 0, 0, None, str(exc))
            )
            continue
        datasets[kind] = dataset
        statuses.append(
            SourceStatus(
                kind,
                "loaded_point_in_time",
                dataset.audit.source_files,
                dataset.audit.rows,
                dataset.audit.source_sha256,
                dataset.audit.availability_policy,
            )
        )
    return datasets, tuple(statuses)


def run_v41_semantic_alpha(
    daily_dir: str | Path,
    membership_path: str | Path,
    *,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    optional_paths: dict[str, str],
    config: V41Config | None = None,
) -> V41Report:
    config = config or V41Config()
    config.validate()
    candidates = generate_v41_candidates(config)
    memberships, membership_sha = _load_memberships(membership_path, config.universe_top_n)
    instruments = tuple(sorted({item for members in memberships.values() for item in members}))
    root = Path(daily_dir).expanduser().resolve()
    files = select_qd_daily_files(
        root, start_date=config.data_start, end_date=f"{config.shadow_year}-12-31"
    )
    daily_manifest = build_selected_files_snapshot_manifest(root, files)
    daily_dataset = load_qd_daily_directory(
        root,
        start_date=config.data_start,
        end_date=f"{config.shadow_year}-12-31",
        instruments=instruments,
    )
    alternative, source_status = _load_sources(
        optional_paths, instruments=instruments, config=config
    )
    components = {
        "qd_daily": daily_manifest.snapshot_sha256,
        "dynamic_universe": membership_sha,
        **{
            f"qd_{kind}": dataset.audit.source_sha256
            for kind, dataset in sorted(alternative.items())
        },
    }
    composite = build_composite_snapshot_manifest(components)
    snapshot_id = registry.register_snapshot(
        composite, vendor_version="V4.1 frozen semantic A-share snapshot", notes="2025/2026 sealed"
    )
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            "V4.1 semantic A-share alpha search",
            "A-share trading constraints and economic-use separation may repair the IC-to-long-only conversion gap.",
            snapshot_id,
            code_version,
            json.dumps(
                {"version": V41_VERSION, "candidate_manifest": _hash([item.fingerprint for item in candidates])},
                sort_keys=True,
            ),
        )
    )
    calendar = tuple(sorted({bar.trade_date for bar in daily_dataset.bars}))
    bars: dict[str, dict[str, QmtDailyBar]] = defaultdict(dict)
    for bar in daily_dataset.bars:
        bars[bar.instrument][bar.trade_date] = bar
    execution_members = _execution_memberships(memberships, calendar)
    regimes = classify_prior_regimes(
        calendar=calendar, bars=bars, execution_members=execution_members, config=config
    )
    controls: dict[tuple[int, int], tuple[tuple[EvaluationObservation, ...], ...]] = {}
    control_cache: dict[tuple[str, str, int, str, str], float | None] = {}
    for horizon in HORIZONS:
        for year in (2022, 2023, 2024):
            panels = []
            for family, field in (
                ("ohlc_return", "close"),
                ("volatility", "volatility"),
                ("amihud", "amihud"),
                ("price_level", "close"),
            ):
                control = PriceCandidate(
                    f"v41_control_{family}_20_{horizon}",
                    family,
                    field,
                    20,
                    horizon,
                    1,
                    f"{family}(20)",
                    _hash({"control": family, "horizon": horizon, "version": V41_VERSION}),
                )
                panel, _ = _panel(
                    control,
                    year=year,
                    calendar=calendar,
                    bars=bars,
                    execution_members=execution_members,
                    minimum_cross_section=config.minimum_cross_section,
                    signal_cache=control_cache,
                )
                panels.append(panel)
            controls[(horizon, year)] = tuple(panels)
    anchors = {
        (horizon, year): _anchors(
            year=year,
            horizon=horizon,
            calendar=calendar,
            bars=bars,
            execution_members=execution_members,
        )
        for horizon in config.alternative_horizons
        for year in (2022, 2023, 2024)
    }
    by_fingerprint = {item.fingerprint: item for item in candidates}
    residual_panels: dict[tuple[str, int], tuple[EvaluationObservation, ...]] = {}
    discovery_daily: dict[str, tuple] = {}
    discovery_scores: dict[str, YearScore] = {}
    discovery_shapes: dict[str, EconomicShape] = {}
    trial_ids: dict[str, str] = {}
    evaluated: list[SemanticCandidate] = []
    signal_cache: dict[tuple[str, str, int, str, str], float | None] = {}
    direction_panel_cache: dict[
        tuple[str, str, int, int], tuple[EvaluationObservation, ...]
    ] = {}
    for candidate in candidates:
        trial_id, _ = registry.create_trial(
            TrialSpec(
                experiment_id,
                "v4.1_semantic_candidate",
                candidate.candidate_id,
                json.dumps(asdict(candidate), sort_keys=True, separators=(",", ":")),
                config.seed,
                "2022-01-01",
                "2022-12-31",
                "2023-01-01",
                "2023-12-31",
                "2024-01-01",
                "2024-12-31",
            )
        )
        trial_ids[candidate.fingerprint] = trial_id
        if candidate.source_kind != "daily" and candidate.source_kind not in alternative:
            registry.record_trial_result(
                trial_id,
                json.dumps({"status": "DATA_NOT_RESEARCH_READY"}, sort_keys=True),
            )
            continue
        panel_key = (
            candidate.source_kind,
            candidate.family,
            candidate.lookback,
            candidate.horizon,
        )
        base_panel = direction_panel_cache.get(panel_key)
        if base_panel is None:
            positive = replace(candidate, direction=1)
            if candidate.source_kind == "daily":
                base_panel, _metrics = _panel(
                    positive.price_proxy(),
                    year=2022,
                    calendar=calendar,
                    bars=bars,
                    execution_members=execution_members,
                    minimum_cross_section=config.minimum_cross_section,
                    signal_cache=signal_cache,
                )
            else:
                base_panel, _metrics = _alternative_panel(
                    positive,
                    year=2022,
                    daily_bars=daily_dataset.bars,
                    dataset=alternative[candidate.source_kind],
                    anchors=anchors[(candidate.horizon, 2022)],
                )
            direction_panel_cache[panel_key] = base_panel
        panel = base_panel if candidate.direction == 1 else _mirror_panel(base_panel)
        if candidate.direction == 1:
            direction_panel_cache.pop(panel_key, None)
        if not panel:
            registry.record_trial_result(
                trial_id,
                json.dumps({"status": "NO_VALID_PANEL"}, sort_keys=True),
            )
            continue
        residual = residualize_panel(panel, controls[(candidate.horizon, 2022)])
        residual_metrics = _daily_metrics(residual)
        discovery_daily[candidate.fingerprint] = residual_metrics
        discovery_scores[candidate.fingerprint] = _score(2022, residual_metrics)
        discovery_shapes[candidate.fingerprint] = economic_shape(
            candidate.candidate_id, residual, year=2022, regimes=regimes
        )
        evaluated.append(candidate)
    scores = multi_objective_scores(tuple(evaluated), discovery_shapes)
    ranked_candidates = tuple(by_fingerprint[item.fingerprint].price_proxy() for item in scores)
    all_clusters = cluster_candidates(
        ranked_candidates,
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
    representatives = tuple(by_fingerprint[item.representative_fingerprint] for item in clusters)
    confirmation_shapes: list[EconomicShape] = []
    shadow_shapes: list[EconomicShape] = []
    for candidate in representatives:
        for year in (2023, 2024):
            if candidate.source_kind == "daily":
                panel, _ = _panel(
                    candidate.price_proxy(),
                    year=year,
                    calendar=calendar,
                    bars=bars,
                    execution_members=execution_members,
                    minimum_cross_section=config.minimum_cross_section,
                    signal_cache=signal_cache,
                )
            else:
                panel, _ = _alternative_panel(
                    candidate,
                    year=year,
                    daily_bars=daily_dataset.bars,
                    dataset=alternative[candidate.source_kind],
                    anchors=anchors[(candidate.horizon, year)],
                )
            residual = residualize_panel(panel, controls[(candidate.horizon, year)])
            residual_panels[(candidate.fingerprint, year)] = residual
            shape = economic_shape(candidate.candidate_id, residual, year=year, regimes=regimes)
            (confirmation_shapes if year == 2023 else shadow_shapes).append(shape)
        registry.record_trial_result(
            trial_ids[candidate.fingerprint],
            json.dumps(
                {
                    "status": "ORTHOGONAL_REPRESENTATIVE",
                    "discovery_shape": asdict(discovery_shapes[candidate.fingerprint]),
                    "search_score": asdict(next(item for item in scores if item.fingerprint == candidate.fingerprint)),
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
    for candidate in evaluated:
        if candidate not in representatives:
            search_score = next(
                (item for item in scores if item.fingerprint == candidate.fingerprint), None
            )
            registry.record_trial_result(
                trial_ids[candidate.fingerprint],
                json.dumps(
                    {
                        "status": (
                            "DISCOVERY_REJECT"
                            if search_score is not None
                            else "INSUFFICIENT_EVIDENCE"
                        ),
                        "discovery_shape": asdict(discovery_shapes[candidate.fingerprint]),
                        "search_score": asdict(search_score) if search_score else None,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
    usage_candidates = representatives[: config.usage_candidate_limit]
    base_panels: dict[tuple[int, int], tuple[EvaluationObservation, ...]] = {}
    for horizon in HORIZONS:
        base = PriceCandidate(
            f"v41_slow_reversal_120_{horizon}",
            "ohlc_return",
            "close",
            120,
            horizon,
            -1,
            "return(close,120)",
            _hash({"base": "slow_reversal", "horizon": horizon, "version": V41_VERSION}),
        )
        for year in (2023, 2024):
            panel, _ = _panel(
                base,
                year=year,
                calendar=calendar,
                bars=bars,
                execution_members=execution_members,
                minimum_cross_section=config.minimum_cross_section,
                signal_cache=signal_cache,
            )
            base_panels[(horizon, year)] = residualize_panel(panel, controls[(horizon, year)])
    usage_grid: list[tuple[SemanticCandidate, UsageScore, tuple[float, ...]]] = []
    for candidate in usage_candidates:
        panel = residual_panels[(candidate.fingerprint, 2023)]
        for usage in config.usages:
            for breadth in config.usage_breadths:
                for regime in config.regime_policies:
                    spec = UsageSpec(usage, breadth, regime)
                    trial_id, _ = registry.create_trial(
                        TrialSpec(
                            experiment_id,
                            "v4.1_usage_mapping",
                            candidate.candidate_id,
                            json.dumps(asdict(spec), sort_keys=True),
                            config.seed,
                            "2022-01-01",
                            "2022-12-31",
                            "2023-01-01",
                            "2023-12-31",
                            "2024-01-01",
                            "2024-12-31",
                        )
                    )
                    usage_score, returns = evaluate_usage(
                        candidate.candidate_id,
                        panel,
                        base_panels[(candidate.horizon, 2023)],
                        spec,
                        year=2023,
                        horizon=candidate.horizon,
                        nav=config.primary_nav,
                        bars=bars,
                        calendar=calendar,
                        regimes=regimes,
                        config=config,
                    )
                    registry.record_trial_result(
                        trial_id,
                        json.dumps(asdict(usage_score), sort_keys=True, separators=(",", ":")),
                    )
                    if usage_score.active_days >= config.minimum_active_days:
                        usage_grid.append((candidate, usage_score, returns))
    selected_candidate: SemanticCandidate | None = None
    selected_usage: UsageScore | None = None
    shadow_usage: UsageScore | None = None
    capacity_curve: list[UsageScore] = []
    if usage_grid:
        selected_candidate, selected_usage, _ = max(
            usage_grid,
            key=lambda item: (
                item[1].objective_after_complexity,
                item[0].fingerprint,
                item[1].spec.identity,
            ),
        )
        shadow_usage, _selected_returns = evaluate_usage(
            selected_candidate.candidate_id,
            residual_panels[(selected_candidate.fingerprint, 2024)],
            base_panels[(selected_candidate.horizon, 2024)],
            selected_usage.spec,
            year=2024,
            horizon=selected_candidate.horizon,
            nav=config.primary_nav,
            bars=bars,
            calendar=calendar,
            regimes=regimes,
            config=config,
        )
        for nav in config.capacity_navs:
            trial_id, _ = registry.create_trial(
                TrialSpec(
                    experiment_id,
                    "v4.1_capacity",
                    selected_candidate.candidate_id,
                    json.dumps({"spec": asdict(selected_usage.spec), "nav": nav}, sort_keys=True),
                    config.seed,
                    "2022-01-01",
                    "2022-12-31",
                    "2023-01-01",
                    "2023-12-31",
                    "2024-01-01",
                    "2024-12-31",
                )
            )
            score, _ = evaluate_usage(
                selected_candidate.candidate_id,
                residual_panels[(selected_candidate.fingerprint, 2024)],
                base_panels[(selected_candidate.horizon, 2024)],
                selected_usage.spec,
                year=2024,
                horizon=selected_candidate.horizon,
                nav=nav,
                bars=bars,
                calendar=calendar,
                regimes=regimes,
                config=config,
            )
            capacity_curve.append(score)
            registry.record_trial_result(
                trial_id, json.dumps(asdict(score), sort_keys=True, separators=(",", ":"))
            )
    pbo = None
    placebo_signal = None
    placebo_return = None
    dsr = None
    failures: list[str] = []
    if selected_candidate and selected_usage and shadow_usage:
        cpcv_candidates = tuple(item.price_proxy() for item in usage_candidates)
        cpcv_daily = {item.fingerprint: discovery_daily[item.fingerprint] for item in usage_candidates}
        cpcv = _cpcv(
            cpcv_candidates,
            cpcv_daily,
            6,
            3,
            calendar=calendar,
            snapshot_id=snapshot_id,
            experiment_id=experiment_id,
            trial_id=trial_ids[selected_candidate.fingerprint],
            code_version=code_version,
        )
        pbo = cpcv.pbo
        combined = residual_panels[(selected_candidate.fingerprint, 2023)] + residual_panels[(selected_candidate.fingerprint, 2024)]
        placebo_signal = run_placebo(
            combined,
            horizon=f"{selected_candidate.horizon}d",
            direction=1,
            method="signal_shuffle",
            seed=config.seed,
            repetitions=config.placebo_repetitions,
            min_cross_section=config.minimum_cross_section,
        ).empirical_p_value
        placebo_return = run_placebo(
            combined,
            horizon=f"{selected_candidate.horizon}d",
            direction=1,
            method="return_permutation",
            seed=config.seed,
            repetitions=config.placebo_repetitions,
            min_cross_section=config.minimum_cross_section,
        ).empirical_p_value
        trial_sharpes = [
            discovery_scores[item.fingerprint].spread_sharpe or 0.0 for item in evaluated
        ]
        winner = [item.top_bottom for item in discovery_daily[selected_candidate.fingerprint]]
        skew, kurtosis = _moments(winner)
        dsr = deflated_sharpe_ratio(
            observed_sharpe=discovery_scores[selected_candidate.fingerprint].spread_sharpe or 0.0,
            trial_sharpes=trial_sharpes,
            recorded_trial_count=len(candidates),
            observations=len(winner),
            skewness=skew,
            excess_kurtosis=kurtosis,
        ).probability
        if pbo is not None and pbo > config.maximum_pbo:
            failures.append("pbo")
        if placebo_signal > config.maximum_placebo_p or placebo_return > config.maximum_placebo_p:
            failures.append("placebo")
        if dsr < config.minimum_dsr:
            failures.append("dsr")
        if selected_usage.excess_sharpe < config.minimum_excess_sharpe:
            failures.append("confirmation_sharpe")
        if shadow_usage.excess_sharpe < config.minimum_excess_sharpe:
            failures.append("shadow_sharpe")
        if selected_usage.maximum_drawdown < -config.maximum_drawdown:
            failures.append("confirmation_drawdown")
        if shadow_usage.maximum_drawdown < -config.maximum_drawdown:
            failures.append("shadow_drawdown")
    else:
        failures.append("no_economic_usage")
    decision = "COURT_PASS" if not failures else "NO_DEPLOYABLE_ALPHA"
    semantic_manifest = _hash([asdict(item) for item in candidates])
    search_manifest = _hash([asdict(item) for item in scores])
    gates = _hash(
        {
            "minimum_dsr": config.minimum_dsr,
            "maximum_placebo_p": config.maximum_placebo_p,
            "maximum_pbo": config.maximum_pbo,
            "minimum_excess_sharpe": config.minimum_excess_sharpe,
            "maximum_drawdown": config.maximum_drawdown,
        }
    )
    portfolio = _hash(asdict(selected_usage.spec) if selected_usage else {"status": "none"})
    release_payload = {
        "state": "SEALED",
        "semantic": semantic_manifest,
        "search": search_manifest,
        "portfolio": portfolio,
        "gates": gates,
        "allowed": [2022, 2023, 2024],
        "sealed": [2025, 2026],
    }
    sealed = SealedRelease(
        "SEALED",
        (2022, 2023, 2024),
        (2025, 2026),
        semantic_manifest,
        portfolio,
        gates,
        _hash(release_payload),
    )
    report = V41Report(
        V41_VERSION,
        experiment_id,
        snapshot_id,
        composite.snapshot_sha256,
        len(candidates),
        len(evaluated),
        len(all_clusters),
        source_status,
        scores,
        clusters,
        tuple(discovery_shapes[item.fingerprint] for item in evaluated),
        tuple(confirmation_shapes),
        tuple(shadow_shapes),
        selected_candidate.candidate_id if selected_candidate else None,
        selected_usage,
        shadow_usage,
        tuple(capacity_curve),
        pbo,
        placebo_signal,
        placebo_return,
        dsr,
        tuple(failures),
        decision,
        semantic_manifest,
        search_manifest,
        sealed,
        registry.trial_count(experiment_id),
        (
            "2022-2024 were inspected in prior project versions and remain retrospective evidence.",
            "2024 diagnoses mechanism failure but cannot reselect the candidate or usage mapping.",
            "Auction data are usable at 09:30 only when the adapter proves 09:26 availability; close-derived alternatives are lagged to the next session.",
            "Static board-code price limits do not identify historical ST status or IPO no-limit days and are research proxies.",
            "2025/2026 remain sealed and were neither enumerated nor read.",
        ),
    )
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "v4.1-report.json").write_text(report.to_json(), encoding="utf-8")
    (destination / "v4.1-report.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (destination / "v4.1-report.en.md").write_text(report.to_markdown("en"), encoding="utf-8")
    (destination / "v4.1-sealed-manifest.json").write_text(
        json.dumps(asdict(sealed), indent=2, sort_keys=True), encoding="utf-8"
    )
    memory_lines = [
        json.dumps(
            {
                "candidate_id": item.candidate_id,
                "fingerprint": item.fingerprint,
                "family": item.family,
                "objective": item.objective,
                "decision": (
                    "SHORTLIST" if item.fingerprint in {cluster.representative_fingerprint for cluster in clusters} else "NEGATIVE_MEMORY"
                ),
                "empirical_trial_recorded": True,
            },
            sort_keys=True,
        )
        for item in scores
    ]
    (destination / "v4.1-search-memory.jsonl").write_text(
        "\n".join(memory_lines) + ("\n" if memory_lines else ""), encoding="utf-8"
    )
    return report
