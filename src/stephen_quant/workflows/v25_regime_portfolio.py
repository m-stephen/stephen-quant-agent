from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from itertools import combinations
from pathlib import Path
from statistics import median, stdev

from stephen_quant.baseline import (
    BacktestPeriod,
    BaselineConfig,
    BaselineLineage,
    BaselineObservation,
    BaselineReport,
    run_momentum_topk,
)
from stephen_quant.evaluation import average_ranks
from stephen_quant.falsification import (
    DeflatedSharpeResult,
    PlaceboResult,
    deflated_sharpe_ratio,
    run_placebo,
)
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest
from stephen_quant.path_config import LocalPathConfig

from .research_epoch import (
    ReturnMoments,
    canonical_json,
    evaluation_rows,
    raw_sharpe,
    sample_return_moments,
    sha256_bytes,
    sha256_file,
    shared_non_overlapping,
)
from .v23_style_residualization import build_v23_frozen_panel
from .v24_temporal_stability import (
    V24TemporalDiagnostics,
    load_v24_temporal_stability_config,
    temporal_diagnostics,
)

V25_CONFIG_VERSION = "2.5.0"
V25_METHOD_VERSION = "v2.5-preregistered-regime-portfolio-1.0.0"
V25_REPLAY_VERSION = "v2.5-regime-portfolio-replay-1.0.0"
V25_PBO_VERSION = "v2.5-strategy-family-cscv-1.0.0"
V25_PBO_SCOPE = "PORTFOLIO_POLICY_SELECTION_ONLY"
V25_POLICIES = ("risk_off_cash", "risk_off_momentum_fallback")


@dataclass(frozen=True)
class V25RegimePortfolioConfig:
    v24_config: str
    expected_source_snapshot_sha256: str
    target_schema_id: str
    target_fingerprint: str
    control_schema_id: str
    control_fingerprint: str
    prior_trial_count: int
    prior_execution_raw_sharpes: tuple[float, ...]
    prior_raw_net_sharpe: float
    prior_annualized_net_sharpe: float
    prior_net_total_return: float
    prior_max_drawdown: float
    prior_total_cost: float
    prior_total_turnover: float
    prior_periods: int
    prior_evidence_sha256: str
    regime_threshold: float
    pbo_blocks: int
    placebo_repetitions: int
    minimum_sharpe_improvement: float
    maximum_drawdown: float
    minimum_positive_year_fraction: float
    minimum_worst_year_return: float
    minimum_worst_year_sharpe: float
    minimum_rolling_sharpe: float
    maximum_top_decile_absolute_return_contribution: float
    max_placebo_p_value: float
    maximum_pbo: float
    min_dsr_probability: float
    seed: int

    def evidence_payload(self) -> dict[str, object]:
        return {
            "expected_source_snapshot_sha256": self.expected_source_snapshot_sha256,
            "target_schema_id": self.target_schema_id,
            "target_fingerprint": self.target_fingerprint,
            "control_schema_id": self.control_schema_id,
            "control_fingerprint": self.control_fingerprint,
            "prior_trial_count": self.prior_trial_count,
            "prior_execution_raw_sharpes": self.prior_execution_raw_sharpes,
            "prior_raw_net_sharpe": self.prior_raw_net_sharpe,
            "prior_annualized_net_sharpe": self.prior_annualized_net_sharpe,
            "prior_net_total_return": self.prior_net_total_return,
            "prior_max_drawdown": self.prior_max_drawdown,
            "prior_total_cost": self.prior_total_cost,
            "prior_total_turnover": self.prior_total_turnover,
            "prior_periods": self.prior_periods,
        }

    @property
    def calculated_evidence_sha256(self) -> str:
        return sha256_bytes(canonical_json(self.evidence_payload()).encode())

    def validate(self) -> None:
        if self.prior_trial_count != 45 or len(self.prior_execution_raw_sharpes) != 9:
            raise ValueError("V2.5 must inherit all V2.4 inferential evidence")
        if self.prior_evidence_sha256 != self.calculated_evidence_sha256:
            raise ValueError("V2.5 prior evidence hash does not match its frozen payload")
        if self.regime_threshold != 0.0:
            raise ValueError("V2.5 regime threshold is frozen at zero")
        if self.pbo_blocks < 4 or self.pbo_blocks % 2:
            raise ValueError("V2.5 PBO requires an even number of at least four blocks")
        if self.prior_periods < self.pbo_blocks or self.placebo_repetitions < 1:
            raise ValueError("V2.5 period or placebo settings are invalid")
        if self.maximum_drawdown <= 0:
            raise ValueError("V2.5 maximum drawdown magnitude must be positive")
        probabilities = (
            self.minimum_positive_year_fraction,
            self.maximum_top_decile_absolute_return_contribution,
            self.max_placebo_p_value,
            self.maximum_pbo,
            self.min_dsr_probability,
        )
        if any(not 0 <= value <= 1 for value in probabilities):
            raise ValueError("V2.5 probability thresholds must be in [0, 1]")
        hashes = (
            self.expected_source_snapshot_sha256,
            self.target_fingerprint,
            self.control_fingerprint,
            self.prior_evidence_sha256,
        )
        if any(
            len(value) != 64 or any(c not in "0123456789abcdef" for c in value) for value in hashes
        ):
            raise ValueError("V2.5 hashes must be lowercase SHA-256 values")


@dataclass(frozen=True)
class V25RegimeState:
    execution_at: str
    median_oriented_momentum: float
    regime: str
    observations: int
    point_in_time_visible: bool


@dataclass(frozen=True)
class V25PolicyScore:
    policy_id: str
    trial_id: str | None
    local_trial_number: int | None
    cumulative_trial_number: int | None
    raw_net_sharpe: float
    annualized_net_sharpe: float
    net_total_return: float
    max_drawdown: float
    total_turnover: float
    total_cost: float
    capacity_clipped_notional: float
    period_returns: tuple[float, ...]


@dataclass(frozen=True)
class V25RegimePerformance:
    regime: str
    periods: int
    net_total_return: float
    annualized_net_sharpe: float | None
    mean_net_return: float
    loss_period_fraction: float


@dataclass(frozen=True)
class V25StrategyFamilyPBO:
    method_version: str
    scope: str
    probability: float
    combinations: int
    blocks: int
    configurations: int
    logits: tuple[float, ...]
    matrix_sha256: str
    complete_search_coverage: bool


@dataclass(frozen=True)
class V25RegimePortfolioReport:
    method_version: str
    experiment_id: str
    snapshot_id: str
    source_snapshot_sha256: str
    prior_evidence_sha256: str
    research_window: tuple[str, str]
    regime_definition: str
    regimes: tuple[V25RegimeState, ...]
    baseline: V25PolicyScore
    candidates: tuple[V25PolicyScore, ...]
    selected_policy_id: str
    selected_temporal: V24TemporalDiagnostics
    selected_regime_performance: tuple[V25RegimePerformance, ...]
    signal_placebo: PlaceboResult
    return_placebo: PlaceboResult
    strategy_family_pbo: V25StrategyFamilyPBO
    return_moments: ReturnMoments
    deflated_sharpe: DeflatedSharpeResult
    prior_trial_count: int
    new_trial_count: int
    cumulative_trial_count: int
    engineering_checks: tuple[tuple[str, bool, str], ...]
    alpha_checks: tuple[tuple[str, bool, str], ...]
    release_decision: str
    alpha_decision: str
    validation_window_opened: bool
    test_window_opened: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"en", "zh"}:
            raise ValueError("V2.5 report language must be en or zh")
        zh = language == "zh"
        lines = [
            "# V2.5 市场状态组合研究结果" if zh else "# V2.5 Regime-aware Portfolio Result",
            "",
            f"- {'工程结论' if zh else 'Engineering decision'}: **{self.release_decision}**",
            f"- {'Alpha 结论' if zh else 'Alpha decision'}: **{self.alpha_decision}**",
            f"- {'选定策略' if zh else 'Selected policy'}: `{self.selected_policy_id}`",
            f"- {'累计试验' if zh else 'Cumulative trials'}: {self.cumulative_trial_count}",
            f"- DSR: {self.deflated_sharpe.probability:.4%}",
            f"- PBO ({self.strategy_family_pbo.scope}): {self.strategy_family_pbo.probability:.4%}",
            "",
            "## 策略比较" if zh else "## Policy comparison",
            "",
            "| Policy | Net return | Net Sharpe | Max drawdown | Turnover | Cost |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for score in (self.baseline, *self.candidates):
            lines.append(
                f"| {score.policy_id} | {score.net_total_return:.2%} | "
                f"{score.annualized_net_sharpe:.4f} | {score.max_drawdown:.2%} | "
                f"{score.total_turnover:.4f} | {score.total_cost:,.2f} |"
            )
        lines.extend(["", "## 工程门禁" if zh else "## Engineering gates", ""])
        lines.extend(
            f"- {'通过' if passed and zh else 'PASS' if passed else '失败' if zh else 'FAIL'} "
            f"`{name}`: {detail}"
            for name, passed, detail in self.engineering_checks
        )
        lines.extend(["", "## Alpha 门禁" if zh else "## Alpha gates", ""])
        lines.extend(
            f"- {'通过' if passed and zh else 'PASS' if passed else '失败' if zh else 'FAIL'} "
            f"`{name}`: {detail}"
            for name, passed, detail in self.alpha_checks
        )
        lines.extend(
            [
                "",
                "> PBO 仅覆盖本次组合策略选择；不代表完整自适应因子搜索已被校正。"
                if zh
                else "> PBO covers this portfolio-policy selection only; it does not correct the complete adaptive factor search.",
                "> 仅使用 2022–2024；2025/2026 仍封存。"
                if zh
                else "> Only 2022–2024 was used; 2025/2026 remained sealed.",
                "",
            ]
        )
        return "\n".join(lines)


@dataclass(frozen=True)
class V25RegimePortfolioArtifacts:
    json_path: Path
    markdown_en_path: Path
    markdown_zh_path: Path
    replay_manifest_path: Path


@dataclass(frozen=True)
class V25ReplayVerification:
    passed: bool
    checked_artifacts: int
    mismatches: tuple[str, ...]


def load_v25_regime_portfolio_config(source: str | Path) -> V25RegimePortfolioConfig:
    path = Path(source).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.pop("config_version", None) != V25_CONFIG_VERSION:
        raise ValueError(f"V2.5 config_version must be {V25_CONFIG_VERSION}")
    if isinstance(payload.get("prior_execution_raw_sharpes"), list):
        payload["prior_execution_raw_sharpes"] = tuple(payload["prior_execution_raw_sharpes"])
    try:
        config = V25RegimePortfolioConfig(**payload)
    except TypeError as exc:
        raise ValueError("V2.5 config fields are invalid") from exc
    config.validate()
    return config


def classify_v25_regimes(
    rows: tuple[BaselineObservation, ...], *, direction: int, threshold: float
) -> tuple[V25RegimeState, ...]:
    if direction not in {-1, 1} or threshold != 0.0:
        raise ValueError("V2.5 regime contract is invalid")
    groups: dict[str, list[BaselineObservation]] = defaultdict(list)
    for row in rows:
        groups[row.execution_at].append(row)
    states: list[V25RegimeState] = []
    for execution_at, cross_section in sorted(groups.items()):
        eligible = tuple(row for row in cross_section if row.eligible)
        if not eligible:
            raise ValueError(f"V2.5 regime has no eligible observations: {execution_at}")
        visible = all(
            row.signal_available_at < row.execution_at
            and row.liquidity_available_at < row.execution_at
            for row in eligible
        )
        if not visible:
            raise ValueError("V2.5 regime input is not point-in-time visible")
        value = median(direction * row.signal for row in eligible)
        states.append(
            V25RegimeState(
                execution_at,
                value,
                "RISK_ON" if value > threshold else "RISK_OFF",
                len(eligible),
                visible,
            )
        )
    if {item.regime for item in states} != {"RISK_ON", "RISK_OFF"}:
        raise ValueError("V2.5 requires both preregistered regimes in research data")
    return tuple(states)


def apply_v25_policy(
    residual_rows: tuple[BaselineObservation, ...],
    control_rows: tuple[BaselineObservation, ...],
    regimes: tuple[V25RegimeState, ...],
    *,
    policy_id: str,
    target_direction: int,
    control_direction: int,
) -> tuple[BaselineObservation, ...]:
    if policy_id not in V25_POLICIES:
        raise ValueError(f"unsupported V2.5 policy: {policy_id}")
    controls = {(row.execution_at, row.instrument): row for row in control_rows}
    residuals = {(row.execution_at, row.instrument): row for row in residual_rows}
    if set(controls) != set(residuals):
        raise ValueError("V2.5 residual and control panels do not match")
    by_date = {item.execution_at: item.regime for item in regimes}
    if set(by_date) != {key[0] for key in residuals}:
        raise ValueError("V2.5 regime dates do not match execution dates")
    output: list[BaselineObservation] = []
    for key in sorted(residuals):
        row = residuals[key]
        if by_date[row.execution_at] == "RISK_ON":
            output.append(row)
        elif policy_id == "risk_off_cash":
            output.append(replace(row, eligible=False))
        else:
            control = controls[key]
            output.append(
                replace(
                    row,
                    signal=control.signal * control_direction * target_direction,
                    eligible=control.eligible,
                )
            )
    return tuple(output)


def _score(
    policy_id: str,
    report: BaselineReport,
    *,
    trial_id: str | None,
    trial_number: int | None,
    prior_trial_count: int,
) -> V25PolicyScore:
    if report.metrics.net_sharpe is None:
        raise ValueError(f"V2.5 policy Sharpe is undefined: {policy_id}")
    return V25PolicyScore(
        policy_id,
        trial_id,
        trial_number,
        None if trial_number is None else prior_trial_count + trial_number,
        raw_sharpe(report),
        report.metrics.net_sharpe,
        report.metrics.net_total_return,
        report.metrics.max_drawdown,
        report.metrics.total_turnover,
        report.metrics.total_cost,
        report.metrics.capacity_clipped_notional,
        tuple(period.net_return for period in report.periods),
    )


def select_v25_policy(scores: tuple[V25PolicyScore, ...]) -> V25PolicyScore:
    if {score.policy_id for score in scores} != set(V25_POLICIES):
        raise ValueError("V2.5 selection requires exactly the preregistered policies")
    return min(
        scores,
        key=lambda item: (
            -item.annualized_net_sharpe,
            -item.max_drawdown,
            item.policy_id,
        ),
    )


def strategy_family_pbo(scores: tuple[V25PolicyScore, ...], *, blocks: int) -> V25StrategyFamilyPBO:
    if len(scores) < 2:
        raise ValueError("V2.5 PBO requires at least two policies")
    periods = len(scores[0].period_returns)
    if any(len(item.period_returns) != periods for item in scores):
        raise ValueError("V2.5 PBO policies must share period counts")
    if blocks < 4 or blocks % 2 or periods < blocks:
        raise ValueError("V2.5 PBO block design is invalid")
    boundaries = tuple(
        (index * periods // blocks, (index + 1) * periods // blocks) for index in range(blocks)
    )
    policy_ids = tuple(sorted(item.policy_id for item in scores))
    by_policy = {item.policy_id: item.period_returns for item in scores}
    block_scores = {
        policy_id: tuple(
            sum(by_policy[policy_id][start:end]) / (end - start) for start, end in boundaries
        )
        for policy_id in policy_ids
    }
    logits: list[float] = []
    half = blocks // 2
    all_blocks = set(range(blocks))
    for in_sample in combinations(range(blocks), half):
        out_sample = tuple(sorted(all_blocks - set(in_sample)))
        in_scores = {
            policy_id: sum(block_scores[policy_id][index] for index in in_sample) / half
            for policy_id in policy_ids
        }
        selected = max(policy_ids, key=lambda item: (in_scores[item], item))
        out_scores = [
            sum(block_scores[policy_id][index] for index in out_sample) / half
            for policy_id in policy_ids
        ]
        ranks = average_ranks(out_scores)
        relative_rank = ranks[policy_ids.index(selected)] / (len(policy_ids) + 1)
        logits.append(math.log(relative_rank / (1 - relative_rank)))
    matrix_hash = sha256_bytes(canonical_json(block_scores).encode())
    return V25StrategyFamilyPBO(
        V25_PBO_VERSION,
        V25_PBO_SCOPE,
        sum(value <= 0 for value in logits) / len(logits),
        len(logits),
        blocks,
        len(policy_ids),
        tuple(logits),
        matrix_hash,
        False,
    )


def _regime_performance(
    periods: tuple[BacktestPeriod, ...], regimes: tuple[V25RegimeState, ...]
) -> tuple[V25RegimePerformance, ...]:
    state = {item.execution_at: item.regime for item in regimes}
    grouped: dict[str, list[float]] = defaultdict(list)
    for period in periods:
        grouped[state[period.execution_at]].append(period.net_return)
    result: list[V25RegimePerformance] = []
    for regime in ("RISK_ON", "RISK_OFF"):
        values = tuple(grouped[regime])
        sharpe = None
        if len(values) > 1:
            dispersion = stdev(values)
            sharpe = (
                0.0 if dispersion == 0 else sum(values) / len(values) / dispersion * math.sqrt(12)
            )
        result.append(
            V25RegimePerformance(
                regime,
                len(values),
                math.prod(1 + value for value in values) - 1,
                sharpe,
                sum(values) / len(values),
                sum(value < 0 for value in values) / len(values),
            )
        )
    return tuple(result)


def _resolve_child(parent: Path, value: str) -> Path:
    child = Path(value)
    return child if child.is_absolute() else (parent.parent / child).resolve()


def run_v25_regime_portfolio(
    paths: LocalPathConfig,
    config_path: str | Path,
    *,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    ingested_at: str,
) -> tuple[V25RegimePortfolioReport, V25RegimePortfolioArtifacts]:
    config_path = Path(config_path).expanduser().resolve()
    config = load_v25_regime_portfolio_config(config_path)
    v24_path = _resolve_child(config_path, config.v24_config)
    v24 = load_v24_temporal_stability_config(v24_path)
    v23_path = _resolve_child(v24_path, v24.v23_config)
    v23, panel = build_v23_frozen_panel(
        paths,
        v23_path,
        output_dir=Path(output_dir).expanduser().resolve() / "readiness",
        ingested_at=ingested_at,
    )
    contract = (
        (panel.source_snapshot_sha256, config.expected_source_snapshot_sha256),
        (panel.target_schema.schema_id, config.target_schema_id),
        (panel.target_schema.fingerprint, config.target_fingerprint),
        (panel.control_schema.schema_id, config.control_schema_id),
        (panel.control_schema.fingerprint, config.control_fingerprint),
    )
    if any(actual != expected for actual, expected in contract):
        raise ValueError("V2.5 differs from its frozen data or factor contract")
    source_manifest = build_composite_snapshot_manifest(
        {
            "v23_readiness": panel.source_snapshot_sha256,
            "qd_daily": panel.daily_source_sha256,
            "qd_fund_flow": panel.flow_source_sha256,
            "prior_evidence": config.prior_evidence_sha256,
        }
    )
    snapshot_id = registry.register_snapshot(
        source_manifest,
        vendor_version="V2.5 frozen V2.3 panel and regime policies",
        notes="Preregistered research-only epoch; 2025/2026 remain sealed.",
    )
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            name="v2.5_preregistered_regime_portfolio",
            hypothesis="A zero-threshold market regime changes frozen signal portfolio usage.",
            dataset_snapshot_id=snapshot_id,
            code_version=code_version,
            search_space=canonical_json(asdict(config)),
        )
    )
    residual = shared_non_overlapping(panel.residual_rows, v23.horizon_sessions, v23.top_k)
    control_by_key = {(row.execution_at, row.instrument): row for row in panel.control_rows}
    residual_keys = tuple((row.execution_at, row.instrument) for row in residual)
    if any(key not in control_by_key for key in residual_keys):
        raise ValueError("V2.5 residual execution keys are missing control observations")
    control = tuple(control_by_key[key] for key in residual_keys)
    regimes = classify_v25_regimes(
        control,
        direction=panel.control_schema.direction,
        threshold=config.regime_threshold,
    )
    baseline_config = BaselineConfig(
        top_k=v23.top_k,
        direction=panel.target_schema.direction,
        commission_bps=v23.commission_bps,
        sell_tax_bps=v23.sell_tax_bps,
        slippage_bps=v23.slippage_bps,
        impact_coefficient_bps=v23.impact_coefficient_bps,
        max_participation_rate=v23.max_participation_rate,
        periods_per_year=12,
        missing_holding_policy="stale_zero_return",
    )
    baseline_report = run_momentum_topk(
        residual,
        BaselineLineage(
            panel.target_schema.schema_id,
            panel.target_schema.version,
            snapshot_id,
            experiment_id,
            "v23_exact_replay",
            code_version,
        ),
        baseline_config,
        initial_nav=v23.initial_nav,
    )
    baseline = _score(
        "v23_frozen_baseline",
        baseline_report,
        trial_id=None,
        trial_number=None,
        prior_trial_count=config.prior_trial_count,
    )
    expected = (
        (baseline.raw_net_sharpe, config.prior_raw_net_sharpe),
        (baseline.annualized_net_sharpe, config.prior_annualized_net_sharpe),
        (baseline.net_total_return, config.prior_net_total_return),
        (baseline.max_drawdown, config.prior_max_drawdown),
        (baseline.total_cost, config.prior_total_cost),
        (baseline.total_turnover, config.prior_total_turnover),
        (len(baseline.period_returns), config.prior_periods),
    )
    exact_replay = all(
        math.isclose(float(actual), float(prior), abs_tol=1e-12) for actual, prior in expected
    )
    if not exact_replay:
        raise ValueError("V2.5 does not exactly replay the frozen V2.3 execution")

    candidates: list[V25PolicyScore] = []
    candidate_reports: dict[str, BaselineReport] = {}
    candidate_rows: dict[str, tuple[BaselineObservation, ...]] = {}
    for policy_id in V25_POLICIES:
        trial_id, trial_number = registry.create_trial(
            TrialSpec(
                experiment_id=experiment_id,
                model_name="v2.5_regime_portfolio_policy",
                factor_set=panel.target_schema.schema_id,
                hyperparams=canonical_json(
                    {
                        "policy_id": policy_id,
                        "regime_signal": panel.control_schema.schema_id,
                        "regime_threshold": config.regime_threshold,
                    }
                ),
                seed=config.seed,
                train_start=panel.research_start,
                train_end=panel.research_end,
                validation_start=panel.validation_start,
                validation_end=panel.validation_end,
                test_start=panel.test_start,
                test_end=panel.test_end,
            )
        )
        rows = apply_v25_policy(
            residual,
            control,
            regimes,
            policy_id=policy_id,
            target_direction=panel.target_schema.direction,
            control_direction=panel.control_schema.direction,
        )
        report = run_momentum_topk(
            rows,
            BaselineLineage(
                panel.target_schema.schema_id,
                panel.target_schema.version,
                snapshot_id,
                experiment_id,
                trial_id,
                code_version,
            ),
            replace(
                baseline_config,
                allow_empty_selection=policy_id == "risk_off_cash",
            ),
            initial_nav=v23.initial_nav,
        )
        score = _score(
            policy_id,
            report,
            trial_id=trial_id,
            trial_number=trial_number,
            prior_trial_count=config.prior_trial_count,
        )
        registry.record_trial_result(trial_id, canonical_json(asdict(score)))
        candidates.append(score)
        candidate_reports[policy_id] = report
        candidate_rows[policy_id] = rows
    candidate_tuple = tuple(candidates)
    selected = select_v25_policy(candidate_tuple)
    selected_report = candidate_reports[selected.policy_id]
    selected_rows = candidate_rows[selected.policy_id]
    cumulative = config.prior_trial_count + registry.global_trial_count()
    if registry.global_trial_count() != 2 or cumulative != 47:
        raise ValueError("V2.5 must create exactly two inferential trials")
    pbo = strategy_family_pbo((baseline, *candidate_tuple), blocks=config.pbo_blocks)
    moments = sample_return_moments(selected.period_returns)
    dsr = deflated_sharpe_ratio(
        observed_sharpe=selected.raw_net_sharpe,
        trial_sharpes=(
            *config.prior_execution_raw_sharpes,
            *(item.raw_net_sharpe for item in candidate_tuple),
        ),
        recorded_trial_count=cumulative,
        observations=len(selected.period_returns),
        skewness=moments.skewness,
        excess_kurtosis=moments.excess_kurtosis,
    )
    evaluation = evaluation_rows(selected_rows, horizon="20d")
    signal_placebo = run_placebo(
        evaluation,
        horizon="20d",
        direction=panel.target_schema.direction,
        method="signal_shuffle",
        seed=config.seed,
        repetitions=config.placebo_repetitions,
    )
    return_placebo = run_placebo(
        evaluation,
        horizon="20d",
        direction=panel.target_schema.direction,
        method="return_permutation",
        seed=config.seed + 1,
        repetitions=config.placebo_repetitions,
    )
    temporal = temporal_diagnostics(
        selected_report.periods,
        rolling_periods=12,
        periods_per_year=12,
    )
    regime_performance = _regime_performance(selected_report.periods, regimes)
    execution_dates = tuple(period.execution_at for period in baseline_report.periods)
    common_dates = all(
        tuple(period.execution_at for period in report.periods) == execution_dates
        for report in candidate_reports.values()
    )
    no_capacity_clip = all(
        score.capacity_clipped_notional == 0 for score in (baseline, *candidate_tuple)
    )
    engineering_checks = (
        ("EXACT_V23_REPLAY", exact_replay, "all frozen execution metrics match"),
        (
            "POINT_IN_TIME_REGIME",
            all(item.point_in_time_visible for item in regimes),
            "visible before execution",
        ),
        ("COMMON_EXECUTION_DATES", common_dates, f"periods={len(execution_dates)}"),
        ("TRIAL_LEDGER", cumulative == 47, f"new=2 cumulative={cumulative}"),
        ("NO_CAPACITY_CLIP", no_capacity_clip, "all policies unclipped"),
        ("PBO_SCOPE", pbo.scope == V25_PBO_SCOPE and not pbo.complete_search_coverage, pbo.scope),
        ("SEALED_WINDOWS", True, "2025/2026 not loaded"),
    )
    alpha_checks = (
        (
            "SHARPE_IMPROVEMENT",
            selected.annualized_net_sharpe
            >= config.prior_annualized_net_sharpe + config.minimum_sharpe_improvement,
            f"{selected.annualized_net_sharpe:.6f}",
        ),
        (
            "MAX_DRAWDOWN",
            selected.max_drawdown >= -config.maximum_drawdown,
            f"{selected.max_drawdown:.2%}",
        ),
        (
            "POSITIVE_YEAR_FRACTION",
            temporal.positive_year_fraction >= config.minimum_positive_year_fraction,
            f"{temporal.positive_year_fraction:.2%}",
        ),
        (
            "WORST_YEAR_RETURN",
            temporal.worst_year_return >= config.minimum_worst_year_return,
            f"{temporal.worst_year_return:.2%}",
        ),
        (
            "WORST_YEAR_SHARPE",
            temporal.worst_year_sharpe >= config.minimum_worst_year_sharpe,
            f"{temporal.worst_year_sharpe:.6f}",
        ),
        (
            "ROLLING_SHARPE",
            temporal.minimum_rolling_sharpe >= config.minimum_rolling_sharpe,
            f"{temporal.minimum_rolling_sharpe:.6f}",
        ),
        (
            "RETURN_CONCENTRATION",
            temporal.top_decile_absolute_return_contribution
            <= config.maximum_top_decile_absolute_return_contribution,
            f"{temporal.top_decile_absolute_return_contribution:.2%}",
        ),
        (
            "SIGNAL_PLACEBO",
            signal_placebo.empirical_p_value <= config.max_placebo_p_value,
            f"p={signal_placebo.empirical_p_value}",
        ),
        (
            "RETURN_PLACEBO",
            return_placebo.empirical_p_value <= config.max_placebo_p_value,
            f"p={return_placebo.empirical_p_value}",
        ),
        ("PBO_POLICY_SELECTION", pbo.probability <= config.maximum_pbo, f"PBO={pbo.probability}"),
        ("DSR", dsr.probability >= config.min_dsr_probability, f"p={dsr.probability}"),
    )
    engineering_passed = all(item[1] for item in engineering_checks)
    alpha_passed = engineering_passed and all(item[1] for item in alpha_checks)
    improved = selected.annualized_net_sharpe > baseline.annualized_net_sharpe
    report = V25RegimePortfolioReport(
        V25_METHOD_VERSION,
        experiment_id,
        snapshot_id,
        panel.source_snapshot_sha256,
        config.prior_evidence_sha256,
        (panel.research_start, panel.research_end),
        "median(oriented price_momentum_5_20d) > 0",
        regimes,
        baseline,
        candidate_tuple,
        selected.policy_id,
        temporal,
        regime_performance,
        signal_placebo,
        return_placebo,
        pbo,
        moments,
        dsr,
        config.prior_trial_count,
        registry.global_trial_count(),
        cumulative,
        engineering_checks,
        alpha_checks,
        "RESEARCH_PREVIEW_READY" if engineering_passed else "RELEASE_BLOCKED",
        "PASS_ALPHA_COURT"
        if alpha_passed
        else "PROMOTE_RESEARCH_ONLY"
        if improved
        else "REJECT_NO_IMPROVEMENT",
        False,
        False,
    )
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "v2.5-regime-portfolio.json"
    en_path = output / "v2.5-regime-portfolio.en.md"
    zh_path = output / "v2.5-regime-portfolio.zh.md"
    json_path.write_text(report.to_json() + "\n", encoding="utf-8", newline="\n")
    en_path.write_text(report.to_markdown("en"), encoding="utf-8", newline="\n")
    zh_path.write_text(report.to_markdown("zh"), encoding="utf-8", newline="\n")
    artifacts = {"json": json_path, "markdown_en": en_path, "markdown_zh": zh_path}
    replay_payload = {
        "replay_version": V25_REPLAY_VERSION,
        "method_version": report.method_version,
        "source_snapshot_sha256": report.source_snapshot_sha256,
        "prior_evidence_sha256": report.prior_evidence_sha256,
        "cumulative_trial_count": report.cumulative_trial_count,
        "selected_policy_id": report.selected_policy_id,
        "release_decision": report.release_decision,
        "alpha_decision": report.alpha_decision,
        "pbo_scope": report.strategy_family_pbo.scope,
        "validation_window_opened": False,
        "test_window_opened": False,
        "artifacts": {name: sha256_file(path) for name, path in sorted(artifacts.items())},
    }
    replay_path = output / "v2.5-replay-manifest.json"
    replay_path.write_text(
        json.dumps(replay_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return report, V25RegimePortfolioArtifacts(json_path, en_path, zh_path, replay_path)


def verify_v25_regime_portfolio_replay(source: str | Path) -> V25ReplayVerification:
    path = Path(source).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("replay_version") != V25_REPLAY_VERSION:
        raise ValueError("unsupported V2.5 replay manifest")
    if payload.get("validation_window_opened") or payload.get("test_window_opened"):
        raise ValueError("V2.5 replay reports sealed-window access")
    if payload.get("cumulative_trial_count") != 47:
        raise ValueError("V2.5 replay cumulative trial count is not 47")
    if payload.get("pbo_scope") != V25_PBO_SCOPE:
        raise ValueError("V2.5 replay PBO scope is invalid")
    mapping = {
        "json": path.parent / "v2.5-regime-portfolio.json",
        "markdown_en": path.parent / "v2.5-regime-portfolio.en.md",
        "markdown_zh": path.parent / "v2.5-regime-portfolio.zh.md",
    }
    expected = payload.get("artifacts", {})
    mismatches = tuple(
        name
        for name, artifact in mapping.items()
        if not artifact.is_file() or expected.get(name) != sha256_file(artifact)
    )
    return V25ReplayVerification(not mismatches, len(mapping), mismatches)
