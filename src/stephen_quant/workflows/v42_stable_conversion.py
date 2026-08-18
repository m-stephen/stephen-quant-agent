from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from statistics import mean, median, stdev

from stephen_quant.evaluation import EvaluationObservation
from stephen_quant.falsification import deflated_sharpe_ratio, run_placebo
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import (
    build_composite_snapshot_manifest,
    build_selected_files_snapshot_manifest,
)
from stephen_quant.qmt import QmtDailyBar, load_qd_daily_directory, select_qd_daily_files

from .price_discovery_lab import (
    PriceCandidate,
    _cpcv,
    _execution_memberships,
    _load_memberships,
    _moments,
    _panel,
)
from .v4_ohlcv_platform import SealedRelease, residualize_panel
from .v41_semantic_alpha import (
    UsageScore,
    UsageSpec,
    V41Config,
    _daily_metrics,
    _hash,
    classify_prior_regimes,
    economic_shape,
    evaluate_usage,
    generate_v41_candidates,
)

V42_VERSION = "v4.2-stability-first-conversion-1.0.0"
FROZEN_V41_SHORTLIST = (
    "negative_return_asymmetry_60_10d_pos",
    "limit_proximity_60_10d_neg",
    "limit_proximity_60_20d_neg",
    "limit_exhaustion_60_10d_pos",
    "t1_delayed_feedback_5_1d_neg",
    "gap_fill_pressure_20_10d_neg",
    "limit_exhaustion_60_20d_pos",
    "limit_proximity_60_5d_neg",
    "limit_proximity_5_1d_neg",
    "t1_delayed_feedback_5_5d_neg",
    "gap_fill_pressure_20_5d_neg",
    "overnight_intraday_divergence_5_1d_pos",
)
FROZEN_SHORTLIST_SHA256 = _hash(FROZEN_V41_SHORTLIST)


@dataclass(frozen=True)
class V42Config:
    data_start: str = "2021-01-01"
    selection_year: int = 2023
    shadow_year: int = 2024
    universe_top_n: int = 50
    minimum_cross_section: int = 10
    usages: tuple[str, ...] = ("BUY", "AVOID", "TIMING")
    breadths: tuple[int, ...] = (5, 10, 20)
    regimes: tuple[str, ...] = ("all", "risk_on", "risk_off")
    subwindows: int = 4
    minimum_active_days: int = 60
    minimum_sign_consistency: float = 0.75
    minimum_worst_subwindow_sharpe: float = 0.0
    minimum_breadth_robustness: float = 2 / 3
    regime_increment_required: float = 0.25
    regime_complexity_penalty: float = 0.15
    cost_stress_multiplier: float = 2.0
    seed: int = 42
    capacity_navs: tuple[float, ...] = (
        1_000_000.0,
        3_000_000.0,
        5_000_000.0,
        10_000_000.0,
        20_000_000.0,
    )
    primary_nav: float = 3_000_000.0
    minimum_dsr: float = 0.95
    maximum_placebo_p: float = 0.05
    maximum_pbo: float = 0.20
    minimum_shadow_sharpe: float = 0.50
    maximum_shadow_drawdown: float = 0.25

    def validate(self) -> None:
        if (self.selection_year, self.shadow_year) != (2023, 2024):
            raise ValueError("V4.2 windows are frozen to 2023 selection and 2024 shadow")
        if self.subwindows != 4:
            raise ValueError("V4.2 requires four chronological 2023 subwindows")
        if self.usages != ("BUY", "AVOID", "TIMING"):
            raise ValueError("V4.2 usage identities are frozen")
        if self.regimes != ("all", "risk_on", "risk_off"):
            raise ValueError("V4.2 regime identities are frozen")
        if self.primary_nav not in self.capacity_navs:
            raise ValueError("primary NAV must appear in capacity curve")


@dataclass(frozen=True)
class SubwindowScore:
    index: int
    observations: int
    cumulative_excess_return: float
    excess_sharpe: float
    maximum_drawdown: float


@dataclass(frozen=True)
class StabilityScore:
    candidate_id: str
    spec: UsageSpec
    full_year: UsageScore
    stress_full_year: UsageScore
    subwindows: tuple[SubwindowScore, ...]
    stress_subwindows: tuple[SubwindowScore, ...]
    sign_consistency: float
    median_subwindow_sharpe: float
    worst_subwindow_sharpe: float
    stress_worst_subwindow_sharpe: float
    breadth_robustness: float
    regime_increment: float | None
    preliminary_eligible: bool
    eligible: bool
    objective: float
    rejection_reasons: tuple[str, ...]


@dataclass(frozen=True)
class AblationSummary:
    candidate_id: str
    raw_rank_ic_2023: float | None
    residual_rank_ic_2023: float | None
    selected_mapping_sharpe_2023: float
    unconditional_mapping_sharpe_2023: float
    stressed_mapping_sharpe_2023: float
    shadow_mapping_sharpe_2024: float
    diagnosis: str


@dataclass(frozen=True)
class V42Report:
    method_version: str
    experiment_id: str
    snapshot_id: str
    snapshot_sha256: str
    shortlist_sha256: str
    shortlist: tuple[str, ...]
    mapping_trials: int
    stability_scores: tuple[StabilityScore, ...]
    selected_candidate_id: str
    selected_spec: UsageSpec
    selected_was_eligible: bool
    selected_2023: UsageScore
    selected_stress_2023: UsageScore
    shadow_2024: UsageScore
    capacity_curve: tuple[UsageScore, ...]
    ablation: AblationSummary
    candidate_pbo: float | None
    placebo_signal_p: float
    placebo_return_p: float
    dsr_probability: float
    court_failures: tuple[str, ...]
    decision: str
    audit_trial_count: int
    sealed_release: SealedRelease
    caveats: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        lines = [
            "# V4.2 经济转换稳定性报告" if zh else "# V4.2 Economic Conversion Stability Report",
            "",
            f"**{'结论' if zh else 'Decision'}: `{self.decision}`**",
            "",
            f"- {'冻结候选' if zh else 'Frozen candidates'}: {len(self.shortlist)}",
            f"- {'映射 Trial' if zh else 'Mapping Trials'}: {self.mapping_trials}",
            f"- {'总审计 Trial' if zh else 'Total audited Trials'}: {self.audit_trial_count}",
            f"- {'入选候选' if zh else 'Selected candidate'}: `{self.selected_candidate_id}`",
            f"- {'映射' if zh else 'Mapping'}: `{self.selected_spec.identity}`",
            f"- {'稳定性合格' if zh else 'Stability eligible'}: {self.selected_was_eligible}",
            "",
            "| Window | Excess Sharpe | Excess return | Drawdown |",
            "|---|---:|---:|---:|",
            f"| 2023 | {self.selected_2023.excess_sharpe:.4f} | {self.selected_2023.cumulative_excess_return:.2%} | {self.selected_2023.maximum_drawdown:.2%} |",
            f"| 2023 cost x2 | {self.selected_stress_2023.excess_sharpe:.4f} | {self.selected_stress_2023.cumulative_excess_return:.2%} | {self.selected_stress_2023.maximum_drawdown:.2%} |",
            f"| 2024 shadow | {self.shadow_2024.excess_sharpe:.4f} | {self.shadow_2024.cumulative_excess_return:.2%} | {self.shadow_2024.maximum_drawdown:.2%} |",
            "",
            f"- PBO: {self.candidate_pbo}",
            f"- Placebo p: {self.placebo_signal_p} / {self.placebo_return_p}",
            f"- DSR: {self.dsr_probability}",
            f"- {'失败门禁' if zh else 'Failed gates'}: {', '.join(self.court_failures) or ('无' if zh else 'none')}",
            "",
            f"## {'消融诊断' if zh else 'Ablation diagnosis'}",
            "",
            f"- {self.ablation.diagnosis}",
            f"- Raw/Residual RankIC: {self.ablation.raw_rank_ic_2023} / {self.ablation.residual_rank_ic_2023}",
            f"- Unconditional/Selected Sharpe: {self.ablation.unconditional_mapping_sharpe_2023:.4f} / {self.ablation.selected_mapping_sharpe_2023:.4f}",
            "",
            f"## {'前十名稳定性分数' if zh else 'Top ten stability scores'}",
            "",
            "| Candidate | Mapping | Eligible | Sign | Worst | Objective |",
            "|---|---|---|---:|---:|---:|",
        ]
        for item in self.stability_scores[:10]:
            lines.append(
                f"| `{item.candidate_id}` | `{item.spec.identity}` | {item.eligible} | "
                f"{item.sign_consistency:.2f} | {item.worst_subwindow_sharpe:.4f} | {item.objective:.4f} |"
            )
        lines.extend(["", f"## {'限制' if zh else 'Limitations'}", ""])
        lines.extend(f"- {item}" for item in self.caveats)
        return "\n".join(lines) + "\n"


def _drawdown(returns: list[float]) -> float:
    nav = peak = 1.0
    worst = 0.0
    for value in returns:
        nav *= 1 + value
        peak = max(peak, nav)
        worst = min(worst, nav / peak - 1)
    return worst


def _sharpe(returns: list[float]) -> float:
    if len(returns) < 2:
        return float("-inf")
    dispersion = stdev(returns)
    return mean(returns) / dispersion * math.sqrt(252) if dispersion > 0 else float("-inf")


def chronological_subwindows(
    returns: tuple[float, ...], count: int = 4
) -> tuple[SubwindowScore, ...]:
    if count < 1:
        raise ValueError("subwindow count must be positive")
    result = []
    for index in range(count):
        start = len(returns) * index // count
        end = len(returns) * (index + 1) // count
        segment = list(returns[start:end])
        result.append(
            SubwindowScore(
                index + 1,
                len(segment),
                math.prod(1 + item for item in segment) - 1 if segment else -1.0,
                _sharpe(segment),
                _drawdown(segment),
            )
        )
    return tuple(result)


def _initial_stability(
    candidate_id: str,
    spec: UsageSpec,
    score: UsageScore,
    returns: tuple[float, ...],
    stress_score: UsageScore,
    stress_returns: tuple[float, ...],
    config: V42Config,
) -> StabilityScore:
    windows = chronological_subwindows(returns, config.subwindows)
    stress_windows = chronological_subwindows(stress_returns, config.subwindows)
    finite = [item.excess_sharpe for item in windows if math.isfinite(item.excess_sharpe)]
    stressed = [
        item.excess_sharpe for item in stress_windows if math.isfinite(item.excess_sharpe)
    ]
    median_sharpe = median(finite) if finite else float("-inf")
    worst = min(finite) if finite else float("-inf")
    stress_worst = min(stressed) if stressed else float("-inf")
    sign = sum(item.cumulative_excess_return > 0 for item in windows) / len(windows)
    reasons = []
    if score.active_days < config.minimum_active_days:
        reasons.append("insufficient_active_days")
    if sign < config.minimum_sign_consistency:
        reasons.append("subwindow_sign_instability")
    if worst <= config.minimum_worst_subwindow_sharpe:
        reasons.append("negative_worst_subwindow")
    if stress_worst <= config.minimum_worst_subwindow_sharpe:
        reasons.append("cost_stress_failure")
    objective = (
        0.30 * median_sharpe
        + 0.25 * worst
        + 0.15 * score.excess_sharpe
        + 0.15 * sign
        + 0.10 * stress_worst
        + 0.05 * score.maximum_drawdown
    )
    return StabilityScore(
        candidate_id,
        spec,
        score,
        stress_score,
        windows,
        stress_windows,
        sign,
        median_sharpe,
        worst,
        stress_worst,
        0.0,
        None,
        not reasons,
        False,
        objective,
        tuple(reasons),
    )


def finalize_stability_scores(
    scores: tuple[StabilityScore, ...], config: V42Config
) -> tuple[StabilityScore, ...]:
    by_key = {
        (item.candidate_id, item.spec.usage, item.spec.breadth, item.spec.regime): item
        for item in scores
    }
    output = []
    for item in scores:
        neighbours = [
            by_key[(item.candidate_id, item.spec.usage, breadth, item.spec.regime)]
            for breadth in config.breadths
        ]
        robustness = sum(entry.preliminary_eligible for entry in neighbours) / len(neighbours)
        reasons = list(item.rejection_reasons)
        if robustness < config.minimum_breadth_robustness:
            reasons.append("breadth_fragility")
        increment = None
        objective = item.objective
        if item.spec.regime != "all":
            unconditional = by_key[
                (item.candidate_id, item.spec.usage, item.spec.breadth, "all")
            ]
            increment = item.objective - unconditional.objective
            objective -= config.regime_complexity_penalty
            if (
                increment < config.regime_increment_required
                or item.worst_subwindow_sharpe <= unconditional.worst_subwindow_sharpe
            ):
                reasons.append("regime_increment_not_proven")
        output.append(
            replace(
                item,
                breadth_robustness=robustness,
                regime_increment=increment,
                eligible=not reasons,
                objective=objective,
                rejection_reasons=tuple(reasons),
            )
        )
    return tuple(
        sorted(
            output,
            key=lambda item: (item.eligible, item.objective, item.candidate_id, item.spec.identity),
            reverse=True,
        )
    )


def select_stable_mapping(scores: tuple[StabilityScore, ...]) -> StabilityScore:
    if not scores:
        raise ValueError("no V4.2 mapping scores")
    eligible = [item for item in scores if item.eligible]
    return max(
        eligible or list(scores),
        key=lambda item: (item.objective, item.candidate_id, item.spec.identity),
    )


def _controls(
    *,
    year: int,
    horizon: int,
    calendar: tuple[str, ...],
    bars: dict[str, dict[str, QmtDailyBar]],
    members: dict[str, tuple[str, ...]],
    minimum_cross_section: int,
    cache: dict,
) -> tuple[tuple[EvaluationObservation, ...], ...]:
    panels = []
    for family, field in (
        ("ohlc_return", "close"),
        ("volatility", "volatility"),
        ("amihud", "amihud"),
        ("price_level", "close"),
    ):
        control = PriceCandidate(
            f"v42_control_{family}_20_{horizon}",
            family,
            field,
            20,
            horizon,
            1,
            f"{family}(20)",
            _hash({"control": family, "horizon": horizon, "version": V42_VERSION}),
        )
        panel, _ = _panel(
            control,
            year=year,
            calendar=calendar,
            bars=bars,
            execution_members=members,
            minimum_cross_section=minimum_cross_section,
            signal_cache=cache,
        )
        panels.append(panel)
    return tuple(panels)


def _base_panel(
    *,
    year: int,
    horizon: int,
    calendar: tuple[str, ...],
    bars: dict[str, dict[str, QmtDailyBar]],
    members: dict[str, tuple[str, ...]],
    controls: tuple[tuple[EvaluationObservation, ...], ...],
    minimum_cross_section: int,
    cache: dict,
) -> tuple[EvaluationObservation, ...]:
    base = PriceCandidate(
        f"v42_slow_reversal_120_{horizon}",
        "ohlc_return",
        "close",
        120,
        horizon,
        -1,
        "return(close,120)",
        _hash({"base": "slow_reversal", "horizon": horizon, "version": V42_VERSION}),
    )
    panel, _ = _panel(
        base,
        year=year,
        calendar=calendar,
        bars=bars,
        execution_members=members,
        minimum_cross_section=minimum_cross_section,
        signal_cache=cache,
    )
    return residualize_panel(panel, controls)


def _trial(
    registry: ExperimentRegistry,
    experiment_id: str,
    stage: str,
    candidate_id: str,
    parameters: object,
    seed: int,
) -> str:
    trial_id, _ = registry.create_trial(
        TrialSpec(
            experiment_id,
            stage,
            candidate_id,
            json.dumps(parameters, sort_keys=True, separators=(",", ":")),
            seed,
            "2022-01-01",
            "2022-12-31",
            "2023-01-01",
            "2023-12-31",
            "2024-01-01",
            "2024-12-31",
        )
    )
    return trial_id


def run_v42_stable_conversion(
    daily_dir: str | Path,
    membership_path: str | Path,
    *,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    config: V42Config | None = None,
) -> V42Report:
    config = config or V42Config()
    config.validate()
    candidate_map = {item.candidate_id: item for item in generate_v41_candidates()}
    if any(item not in candidate_map for item in FROZEN_V41_SHORTLIST):
        raise ValueError("frozen V4.1 shortlist is not reproducible")
    shortlist = tuple(candidate_map[item] for item in FROZEN_V41_SHORTLIST)
    memberships, membership_sha = _load_memberships(membership_path, config.universe_top_n)
    instruments = tuple(sorted({item for values in memberships.values() for item in values}))
    root = Path(daily_dir).expanduser().resolve()
    files = select_qd_daily_files(
        root, start_date=config.data_start, end_date=f"{config.shadow_year}-12-31"
    )
    daily_manifest = build_selected_files_snapshot_manifest(root, files)
    dataset = load_qd_daily_directory(
        root,
        start_date=config.data_start,
        end_date=f"{config.shadow_year}-12-31",
        instruments=instruments,
    )
    composite = build_composite_snapshot_manifest(
        {"qd_daily": daily_manifest.snapshot_sha256, "dynamic_universe": membership_sha}
    )
    snapshot_id = registry.register_snapshot(
        composite, vendor_version="V4.2 frozen conversion snapshot", notes="2025/2026 sealed"
    )
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            "V4.2 stability-first economic conversion",
            "Within-2023 stability can prevent a maximum-Sharpe regime wrapper from winning.",
            snapshot_id,
            code_version,
            json.dumps(
                {
                    "version": V42_VERSION,
                    "shortlist_sha256": FROZEN_SHORTLIST_SHA256,
                    "config": asdict(config),
                },
                sort_keys=True,
            ),
        )
    )
    calendar = tuple(sorted({item.trade_date for item in dataset.bars}))
    bars: dict[str, dict[str, QmtDailyBar]] = defaultdict(dict)
    for bar in dataset.bars:
        bars[bar.instrument][bar.trade_date] = bar
    execution_members = _execution_memberships(memberships, calendar)
    regimes = classify_prior_regimes(
        calendar=calendar,
        bars=bars,
        execution_members=execution_members,
        config=V41Config(),
    )
    signal_cache: dict = {}
    horizons = tuple(sorted({item.horizon for item in shortlist}))
    controls_2023 = {
        horizon: _controls(
            year=2023,
            horizon=horizon,
            calendar=calendar,
            bars=bars,
            members=execution_members,
            minimum_cross_section=config.minimum_cross_section,
            cache=signal_cache,
        )
        for horizon in horizons
    }
    base_2023 = {
        horizon: _base_panel(
            year=2023,
            horizon=horizon,
            calendar=calendar,
            bars=bars,
            members=execution_members,
            controls=controls_2023[horizon],
            minimum_cross_section=config.minimum_cross_section,
            cache=signal_cache,
        )
        for horizon in horizons
    }
    raw_2023: dict[str, tuple[EvaluationObservation, ...]] = {}
    residual_2023: dict[str, tuple[EvaluationObservation, ...]] = {}
    daily_2023: dict[str, tuple] = {}
    for candidate in shortlist:
        trial_id = _trial(
            registry, experiment_id, "v4.2_frozen_candidate", candidate.candidate_id, asdict(candidate), config.seed
        )
        raw, _ = _panel(
            candidate.price_proxy(),
            year=2023,
            calendar=calendar,
            bars=bars,
            execution_members=execution_members,
            minimum_cross_section=config.minimum_cross_section,
            signal_cache=signal_cache,
        )
        residual = residualize_panel(raw, controls_2023[candidate.horizon])
        raw_2023[candidate.candidate_id] = raw
        residual_2023[candidate.candidate_id] = residual
        daily_2023[candidate.fingerprint] = _daily_metrics(residual)
        registry.record_trial_result(
            trial_id,
            json.dumps(
                {"status": "FROZEN_SHORTLIST", "rows": len(residual)}, sort_keys=True
            ),
        )

    stressed_v41 = replace(
        V41Config(),
        commission_bps=V41Config().commission_bps * config.cost_stress_multiplier,
        sell_tax_bps=V41Config().sell_tax_bps * config.cost_stress_multiplier,
        slippage_bps=V41Config().slippage_bps * config.cost_stress_multiplier,
        impact_bps=V41Config().impact_bps * config.cost_stress_multiplier,
    )
    raw_scores: list[StabilityScore] = []
    returns_by_identity: dict[tuple[str, str], tuple[float, ...]] = {}
    mapping_trials = 0
    for candidate in shortlist:
        panel = residual_2023[candidate.candidate_id]
        for usage in config.usages:
            for breadth in config.breadths:
                for regime in config.regimes:
                    spec = UsageSpec(usage, breadth, regime)
                    trial_id = _trial(
                        registry,
                        experiment_id,
                        "v4.2_stability_mapping",
                        candidate.candidate_id,
                        asdict(spec),
                        config.seed,
                    )
                    score, returns = evaluate_usage(
                        candidate.candidate_id,
                        panel,
                        base_2023[candidate.horizon],
                        spec,
                        year=2023,
                        horizon=candidate.horizon,
                        nav=config.primary_nav,
                        bars=bars,
                        calendar=calendar,
                        regimes=regimes,
                        config=V41Config(),
                    )
                    stress_trial = _trial(
                        registry,
                        experiment_id,
                        "v4.2_cost_stress",
                        candidate.candidate_id,
                        {"spec": asdict(spec), "multiplier": config.cost_stress_multiplier},
                        config.seed,
                    )
                    stress_score, stress_returns = evaluate_usage(
                        candidate.candidate_id,
                        panel,
                        base_2023[candidate.horizon],
                        spec,
                        year=2023,
                        horizon=candidate.horizon,
                        nav=config.primary_nav,
                        bars=bars,
                        calendar=calendar,
                        regimes=regimes,
                        config=stressed_v41,
                    )
                    initial = _initial_stability(
                        candidate.candidate_id,
                        spec,
                        score,
                        returns,
                        stress_score,
                        stress_returns,
                        config,
                    )
                    raw_scores.append(initial)
                    returns_by_identity[(candidate.candidate_id, spec.identity)] = returns
                    registry.record_trial_result(
                        trial_id, json.dumps(asdict(initial), sort_keys=True, separators=(",", ":"))
                    )
                    registry.record_trial_result(
                        stress_trial,
                        json.dumps(asdict(stress_score), sort_keys=True, separators=(",", ":")),
                    )
                    mapping_trials += 2
    scores = finalize_stability_scores(tuple(raw_scores), config)
    selected = select_stable_mapping(scores)
    selected_candidate = candidate_map[selected.candidate_id]

    controls_2024 = _controls(
        year=2024,
        horizon=selected_candidate.horizon,
        calendar=calendar,
        bars=bars,
        members=execution_members,
        minimum_cross_section=config.minimum_cross_section,
        cache=signal_cache,
    )
    base_2024 = _base_panel(
        year=2024,
        horizon=selected_candidate.horizon,
        calendar=calendar,
        bars=bars,
        members=execution_members,
        controls=controls_2024,
        minimum_cross_section=config.minimum_cross_section,
        cache=signal_cache,
    )
    raw_shadow, _ = _panel(
        selected_candidate.price_proxy(),
        year=2024,
        calendar=calendar,
        bars=bars,
        execution_members=execution_members,
        minimum_cross_section=config.minimum_cross_section,
        signal_cache=signal_cache,
    )
    residual_shadow = residualize_panel(raw_shadow, controls_2024)
    shadow, _ = evaluate_usage(
        selected.candidate_id,
        residual_shadow,
        base_2024,
        selected.spec,
        year=2024,
        horizon=selected_candidate.horizon,
        nav=config.primary_nav,
        bars=bars,
        calendar=calendar,
        regimes=regimes,
        config=V41Config(),
    )
    shadow_trial = _trial(
        registry,
        experiment_id,
        "v4.2_frozen_shadow",
        selected.candidate_id,
        asdict(selected.spec),
        config.seed,
    )
    registry.record_trial_result(
        shadow_trial, json.dumps(asdict(shadow), sort_keys=True, separators=(",", ":"))
    )
    capacity = []
    for nav in config.capacity_navs:
        trial_id = _trial(
            registry,
            experiment_id,
            "v4.2_capacity",
            selected.candidate_id,
            {"spec": asdict(selected.spec), "nav": nav},
            config.seed,
        )
        result, _ = evaluate_usage(
            selected.candidate_id,
            residual_shadow,
            base_2024,
            selected.spec,
            year=2024,
            horizon=selected_candidate.horizon,
            nav=nav,
            bars=bars,
            calendar=calendar,
            regimes=regimes,
            config=V41Config(),
        )
        capacity.append(result)
        registry.record_trial_result(
            trial_id, json.dumps(asdict(result), sort_keys=True, separators=(",", ":"))
        )

    all_candidates = tuple(item.price_proxy() for item in shortlist)
    cpcv = _cpcv(
        all_candidates,
        daily_2023,
        6,
        3,
        calendar=calendar,
        snapshot_id=snapshot_id,
        experiment_id=experiment_id,
        trial_id=shadow_trial,
        code_version=code_version,
    )
    combined = residual_2023[selected.candidate_id] + residual_shadow
    placebo_signal = run_placebo(
        combined,
        horizon=f"{selected_candidate.horizon}d",
        direction=1,
        method="signal_shuffle",
        seed=config.seed,
        repetitions=199,
        min_cross_section=config.minimum_cross_section,
    ).empirical_p_value
    placebo_return = run_placebo(
        combined,
        horizon=f"{selected_candidate.horizon}d",
        direction=1,
        method="return_permutation",
        seed=config.seed,
        repetitions=199,
        min_cross_section=config.minimum_cross_section,
    ).empirical_p_value
    trial_sharpes = [item.full_year.excess_sharpe for item in scores]
    selected_returns = returns_by_identity[(selected.candidate_id, selected.spec.identity)]
    skew, kurtosis = _moments(list(selected_returns))
    dsr = deflated_sharpe_ratio(
        observed_sharpe=selected.full_year.excess_sharpe,
        trial_sharpes=trial_sharpes,
        recorded_trial_count=mapping_trials,
        observations=len(selected_returns),
        skewness=skew,
        excess_kurtosis=kurtosis,
    ).probability
    unconditional = next(
        item
        for item in scores
        if item.candidate_id == selected.candidate_id
        and item.spec.usage == selected.spec.usage
        and item.spec.breadth == selected.spec.breadth
        and item.spec.regime == "all"
    )
    raw_shape = economic_shape(
        selected.candidate_id,
        raw_2023[selected.candidate_id],
        year=2023,
        regimes=regimes,
    )
    residual_shape = economic_shape(
        selected.candidate_id,
        residual_2023[selected.candidate_id],
        year=2023,
        regimes=regimes,
    )
    diagnosis = (
        "regime_wrapper_instability"
        if selected.spec.regime != "all" and shadow.excess_sharpe < 0
        else "economic_mapping_instability"
        if shadow.excess_sharpe < 0
        else "conversion_survived_shadow"
    )
    ablation = AblationSummary(
        selected.candidate_id,
        raw_shape.rank_ic,
        residual_shape.rank_ic,
        selected.full_year.excess_sharpe,
        unconditional.full_year.excess_sharpe,
        selected.stress_full_year.excess_sharpe,
        shadow.excess_sharpe,
        diagnosis,
    )
    failures = []
    if not selected.eligible:
        failures.append("selection_stability")
    if cpcv.pbo is None or cpcv.pbo > config.maximum_pbo:
        failures.append("pbo")
    if placebo_signal > config.maximum_placebo_p or placebo_return > config.maximum_placebo_p:
        failures.append("placebo")
    if dsr < config.minimum_dsr:
        failures.append("dsr")
    if shadow.excess_sharpe < config.minimum_shadow_sharpe:
        failures.append("shadow_sharpe")
    if shadow.maximum_drawdown < -config.maximum_shadow_drawdown:
        failures.append("shadow_drawdown")
    decision = "COURT_PASS" if not failures else "NO_DEPLOYABLE_ALPHA"
    gates_sha = _hash(
        {
            "stability": asdict(config),
            "shortlist": FROZEN_SHORTLIST_SHA256,
            "failures": failures,
        }
    )
    portfolio_sha = _hash(asdict(selected.spec))
    sealed = SealedRelease(
        "SEALED",
        (2022, 2023, 2024),
        (2025, 2026),
        FROZEN_SHORTLIST_SHA256,
        portfolio_sha,
        gates_sha,
        _hash(
            {
                "snapshot": composite.snapshot_sha256,
                "shortlist": FROZEN_SHORTLIST_SHA256,
                "portfolio": portfolio_sha,
                "gates": gates_sha,
            }
        ),
    )
    report = V42Report(
        V42_VERSION,
        experiment_id,
        snapshot_id,
        composite.snapshot_sha256,
        FROZEN_SHORTLIST_SHA256,
        FROZEN_V41_SHORTLIST,
        mapping_trials,
        scores,
        selected.candidate_id,
        selected.spec,
        selected.eligible,
        selected.full_year,
        selected.stress_full_year,
        shadow,
        tuple(capacity),
        ablation,
        cpcv.pbo,
        placebo_signal,
        placebo_return,
        dsr,
        tuple(failures),
        decision,
        registry.trial_count(experiment_id),
        sealed,
        (
            "The V4.1 shortlist is frozen; V4.2 does not add candidates.",
            "2023 alone selects the conversion. 2024 is evaluated only after selection.",
            "2022-2024 remain retrospective because earlier project versions inspected them.",
            "Price-limit signals use board/date rules but lack historical ST and listing-session metadata in the current daily source; proxy quality is explicit.",
            "2025/2026 remain sealed and are not enumerated or read.",
        ),
    )
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "v4.2-report.json").write_text(report.to_json(), encoding="utf-8")
    (destination / "v4.2-report.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (destination / "v4.2-report.en.md").write_text(report.to_markdown("en"), encoding="utf-8")
    (destination / "v4.2-sealed-manifest.json").write_text(
        json.dumps(asdict(sealed), indent=2, sort_keys=True), encoding="utf-8"
    )
    return report
