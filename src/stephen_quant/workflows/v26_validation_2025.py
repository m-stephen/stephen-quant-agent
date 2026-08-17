from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from stephen_quant.baseline import (
    BaselineConfig,
    BaselineLineage,
    BaselineObservation,
    BaselineReport,
    run_momentum_topk,
)
from stephen_quant.discovery import v21_mechanism_generation_plan
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
from stephen_quant.qmt import (
    DynamicUniverseConfig,
    QdAlternativeConfig,
    build_dynamic_universe,
    build_multisource_factor_observations,
    build_qmt_factor_observations,
    load_qd_alternative_directory,
    load_qd_daily_directory,
    write_dynamic_universe,
)
from stephen_quant.v2.real_qd import load_v21_real_research_config

from .research_epoch import (
    ReturnMoments,
    canonical_json,
    evaluation_rows,
    execution_memberships,
    raw_sharpe,
    sample_return_moments,
    sha256_bytes,
    sha256_file,
    shared_non_overlapping,
)
from .v23_style_residualization import residualize_v23_style
from .v24_temporal_stability import V24TemporalDiagnostics, temporal_diagnostics
from .v25_regime_portfolio import (
    V25RegimeState,
    apply_v25_policy,
    classify_v25_regimes,
    load_v25_regime_portfolio_config,
)

V26_CONFIG_VERSION = "2.6.0"
V26_METHOD_VERSION = "v2.6-one-shot-2025-validation-1.0.0"
V26_REPLAY_VERSION = "v2.6-validation-replay-1.0.0"
V26_PBO_STATUS = "NOT_APPLICABLE_FROZEN_SINGLE_POLICY"


@dataclass(frozen=True)
class V26ValidationConfig:
    v25_config: str
    v21_config: str
    validation_data_start: str
    validation_start: str
    validation_end: str
    sealed_test_start: str
    sealed_test_end: str
    target_schema_id: str
    target_fingerprint: str
    control_schema_id: str
    control_fingerprint: str
    frozen_policy_id: str
    regime_threshold: float
    top_k: int
    horizon_sessions: int
    initial_nav: float
    commission_bps: float
    sell_tax_bps: float
    slippage_bps: float
    impact_coefficient_bps: float
    max_participation_rate: float
    prior_trial_count: int
    prior_execution_raw_sharpes: tuple[float, ...]
    prior_research_period_returns: tuple[float, ...]
    prior_research_raw_sharpe: float
    prior_research_annualized_sharpe: float
    prior_research_net_return: float
    prior_research_max_drawdown: float
    prior_policy_selection_pbo: float
    prior_evidence_sha256: str
    minimum_daily_sessions: int
    minimum_validation_periods: int
    rolling_periods: int
    minimum_regime_periods: int
    minimum_net_return: float
    minimum_annualized_sharpe: float
    maximum_drawdown: float
    minimum_rolling_sharpe: float
    maximum_top_decile_absolute_return_contribution: float
    placebo_repetitions: int
    max_placebo_p_value: float
    min_combined_dsr_probability: float
    seed: int

    def evidence_payload(self) -> dict[str, object]:
        return {
            "target_schema_id": self.target_schema_id,
            "target_fingerprint": self.target_fingerprint,
            "control_schema_id": self.control_schema_id,
            "control_fingerprint": self.control_fingerprint,
            "frozen_policy_id": self.frozen_policy_id,
            "regime_threshold": self.regime_threshold,
            "top_k": self.top_k,
            "horizon_sessions": self.horizon_sessions,
            "initial_nav": self.initial_nav,
            "commission_bps": self.commission_bps,
            "sell_tax_bps": self.sell_tax_bps,
            "slippage_bps": self.slippage_bps,
            "impact_coefficient_bps": self.impact_coefficient_bps,
            "max_participation_rate": self.max_participation_rate,
            "prior_trial_count": self.prior_trial_count,
            "prior_execution_raw_sharpes": self.prior_execution_raw_sharpes,
            "prior_research_period_returns": self.prior_research_period_returns,
            "prior_research_raw_sharpe": self.prior_research_raw_sharpe,
            "prior_research_annualized_sharpe": self.prior_research_annualized_sharpe,
            "prior_research_net_return": self.prior_research_net_return,
            "prior_research_max_drawdown": self.prior_research_max_drawdown,
            "prior_policy_selection_pbo": self.prior_policy_selection_pbo,
        }

    @property
    def calculated_evidence_sha256(self) -> str:
        return sha256_bytes(canonical_json(self.evidence_payload()).encode())

    def validate(self) -> None:
        if self.prior_trial_count != 47 or len(self.prior_execution_raw_sharpes) != 11:
            raise ValueError("V2.6 must inherit all V2.5 inferential evidence")
        if len(self.prior_research_period_returns) != 35:
            raise ValueError("V2.6 must inherit the 35-period frozen research path")
        if self.prior_evidence_sha256 != self.calculated_evidence_sha256:
            raise ValueError("V2.6 prior evidence hash does not match its frozen payload")
        if self.frozen_policy_id != "risk_off_cash" or self.regime_threshold != 0.0:
            raise ValueError("V2.6 policy and zero regime threshold are frozen")
        if self.top_k != 5 or self.horizon_sessions != 20 or self.initial_nav != 3_000_000:
            raise ValueError("V2.6 portfolio contract differs from V2.5")
        if (self.validation_start, self.validation_end) != (
            "2025-01-03",
            "2025-12-31",
        ):
            raise ValueError("V2.6 validation window is frozen to 2025")
        if not self.validation_data_start < self.validation_start:
            raise ValueError("V2.6 validation history must precede validation")
        if not self.validation_end < self.sealed_test_start <= self.sealed_test_end:
            raise ValueError("V2.6 final-test window must remain after validation")
        if self.minimum_daily_sessions < 230 or self.minimum_validation_periods < 10:
            raise ValueError("V2.6 readiness minimums cannot be weakened")
        if self.rolling_periods < 2 or self.minimum_regime_periods < 1:
            raise ValueError("V2.6 rolling or regime counts are invalid")
        probabilities = (
            self.maximum_top_decile_absolute_return_contribution,
            self.max_placebo_p_value,
            self.min_combined_dsr_probability,
            self.prior_policy_selection_pbo,
        )
        if any(not 0 <= value <= 1 for value in probabilities):
            raise ValueError("V2.6 probability thresholds must be in [0, 1]")
        if self.maximum_drawdown <= 0 or self.placebo_repetitions < 1:
            raise ValueError("V2.6 risk or placebo settings are invalid")


@dataclass(frozen=True)
class V26ReadinessReport:
    decision: str
    validation_window: tuple[str, str]
    final_test_window: tuple[str, str]
    source_snapshot_sha256: str
    daily_source_sha256: str
    flow_source_sha256: str
    universe_source_sha256: str
    daily_sessions: int
    universe_sessions: int
    mean_selected: float
    validation_periods: int
    minimum_cross_section: int
    maximum_loaded_date: str
    checks: tuple[tuple[str, bool, str], ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class V26ValidationPanel:
    readiness: V26ReadinessReport
    target_rows: tuple[BaselineObservation, ...]
    control_rows: tuple[BaselineObservation, ...]
    policy_rows: tuple[BaselineObservation, ...]
    regimes: tuple[V25RegimeState, ...]
    target_version: str
    target_direction: int


@dataclass(frozen=True)
class V26ValidationScore:
    trial_id: str
    local_trial_number: int
    cumulative_trial_number: int
    periods: int
    raw_net_sharpe: float
    annualized_net_sharpe: float
    net_total_return: float
    max_drawdown: float
    total_turnover: float
    total_cost: float
    capacity_clipped_notional: float
    period_returns: tuple[float, ...]


@dataclass(frozen=True)
class V26ValidationReport:
    method_version: str
    experiment_id: str
    trial_id: str
    snapshot_id: str
    readiness: V26ReadinessReport
    prior_evidence_sha256: str
    frozen_policy_id: str
    score: V26ValidationScore
    temporal: V24TemporalDiagnostics
    risk_on_periods: int
    risk_off_periods: int
    signal_placebo: PlaceboResult
    return_placebo: PlaceboResult
    combined_return_moments: ReturnMoments
    combined_deflated_sharpe: DeflatedSharpeResult
    historical_policy_selection_pbo: float
    pbo_status: str
    prior_trial_count: int
    new_trial_count: int
    cumulative_trial_count: int
    engineering_checks: tuple[tuple[str, bool, str], ...]
    validation_checks: tuple[tuple[str, bool, str], ...]
    decision: str
    live_trading_authorized: bool
    final_test_window_opened: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"en", "zh"}:
            raise ValueError("V2.6 report language must be en or zh")
        zh = language == "zh"
        lines = [
            "# V2.6 2025 独立验证结果" if zh else "# V2.6 2025 Independent Validation Result",
            "",
            f"- {'结论' if zh else 'Decision'}: **{self.decision}**",
            f"- {'冻结策略' if zh else 'Frozen policy'}: `{self.frozen_policy_id}`",
            f"- {'验证周期' if zh else 'Validation periods'}: {self.score.periods}",
            f"- {'净收益' if zh else 'Net return'}: {self.score.net_total_return:.2%}",
            f"- {'年化净 Sharpe' if zh else 'Annualized net Sharpe'}: {self.score.annualized_net_sharpe:.4f}",
            f"- {'最大回撤' if zh else 'Maximum drawdown'}: {self.score.max_drawdown:.2%}",
            f"- {'合并 DSR' if zh else 'Combined DSR'}: {self.combined_deflated_sharpe.probability:.4%}",
            f"- PBO: `{self.pbo_status}`; {'历史警告' if zh else 'historical warning'}={self.historical_policy_selection_pbo:.2%}",
            "",
            "## 工程门禁" if zh else "## Engineering gates",
            "",
        ]
        lines.extend(
            f"- {'通过' if passed and zh else 'PASS' if passed else '失败' if zh else 'FAIL'} "
            f"`{name}`: {detail}"
            for name, passed, detail in self.engineering_checks
        )
        lines.extend(["", "## 验证门禁" if zh else "## Validation gates", ""])
        lines.extend(
            f"- {'通过' if passed and zh else 'PASS' if passed else '失败' if zh else 'FAIL'} "
            f"`{name}`: {detail}"
            for name, passed, detail in self.validation_checks
        )
        lines.extend(
            [
                "",
                "> 本次结果不授权实盘或打开 2026 最终测试。"
                if zh
                else "> This result does not authorize live trading or opening the 2026 final test.",
                "",
            ]
        )
        return "\n".join(lines)


@dataclass(frozen=True)
class V26ValidationArtifacts:
    readiness_json_path: Path
    json_path: Path
    markdown_en_path: Path
    markdown_zh_path: Path
    replay_manifest_path: Path


@dataclass(frozen=True)
class V26ReplayVerification:
    passed: bool
    checked_artifacts: int
    mismatches: tuple[str, ...]


def load_v26_validation_config(source: str | Path) -> V26ValidationConfig:
    path = Path(source).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.pop("config_version", None) != V26_CONFIG_VERSION:
        raise ValueError(f"V2.6 config_version must be {V26_CONFIG_VERSION}")
    for key in ("prior_execution_raw_sharpes", "prior_research_period_returns"):
        if isinstance(payload.get(key), list):
            payload[key] = tuple(payload[key])
    try:
        config = V26ValidationConfig(**payload)
    except TypeError as exc:
        raise ValueError("V2.6 config fields are invalid") from exc
    config.validate()
    return config


def _resolve_child(parent: Path, value: str) -> Path:
    child = Path(value)
    return child if child.is_absolute() else (parent.parent / child).resolve()


def build_v26_validation_panel(
    paths: LocalPathConfig,
    config_path: str | Path,
    *,
    output_dir: str | Path,
    ingested_at: str,
) -> V26ValidationPanel:
    config_path = Path(config_path).expanduser().resolve()
    config = load_v26_validation_config(config_path)
    v25 = load_v25_regime_portfolio_config(_resolve_child(config_path, config.v25_config))
    v21 = load_v21_real_research_config(_resolve_child(config_path, config.v21_config))
    if (
        v25.target_schema_id != config.target_schema_id
        or v25.target_fingerprint != config.target_fingerprint
        or v25.control_schema_id != config.control_schema_id
        or v25.control_fingerprint != config.control_fingerprint
        or v25.regime_threshold != config.regime_threshold
    ):
        raise ValueError("V2.6 differs from the frozen V2.5 policy inputs")
    if (
        v21.sealed_validation_start != config.validation_start
        or v21.sealed_validation_end != config.validation_end
        or v21.sealed_test_start != config.sealed_test_start
        or v21.sealed_test_end != config.sealed_test_end
    ):
        raise ValueError("V2.6 windows differ from the original sealed contract")
    daily_dir = paths.choose("qd_daily_dir", None, "qd_daily_dir")
    fundamental_dir = paths.choose("qd_fundamental_dir", None, "qd_fundamental_dir")
    flow_dir = paths.choose("qd_fund_flow_dir", None, "qd_fund_flow_dir")
    output = Path(output_dir).expanduser().resolve()
    universe = build_dynamic_universe(
        daily_dir,
        fundamental_dir,
        DynamicUniverseConfig(
            research_start="2025-01-02",
            research_end=config.validation_end,
            top_n=v21.universe_top_n,
            minimum_history_sessions=v21.minimum_history_sessions,
            liquidity_lookback=v21.liquidity_lookback,
            minimum_mean_amount_cny=v21.minimum_mean_amount_cny,
        ),
    )
    write_dynamic_universe(universe, output / "dynamic-universe")
    memberships = {item.decision_date: item.members for item in universe.memberships}
    instruments = tuple(sorted({item for members in memberships.values() for item in members}))
    daily = load_qd_daily_directory(
        daily_dir,
        start_date=config.validation_data_start,
        end_date=config.validation_end,
        instruments=instruments,
        adjustment="back_ratio",
    )
    flow = load_qd_alternative_directory(
        flow_dir,
        QdAlternativeConfig(
            source_kind="fund_flow",
            start_date=config.validation_data_start,
            end_date=config.validation_end,
            ingested_at=ingested_at,
            instruments=instruments,
        ),
    )
    templates = {item.template_id: item for item in v21_mechanism_generation_plan().templates}
    target = templates["flow_confirmation"].render(window=20, horizon="20d")
    control_schema = templates["price_momentum"].render(window=5, horizon="20d")
    if (
        target.schema_id != config.target_schema_id
        or target.fingerprint != config.target_fingerprint
        or control_schema.schema_id != config.control_schema_id
        or control_schema.fingerprint != config.control_fingerprint
    ):
        raise ValueError("V2.6 factor contract differs from V2.5")
    execution_dates = sorted(
        {
            bar.trade_date
            for bar in daily.bars
            if config.validation_start <= bar.trade_date <= config.validation_end
        }
    )
    eligibility = execution_memberships(memberships, execution_dates)
    controls = build_qmt_factor_observations(
        daily.bars,
        control_schema.compile(),
        test_start=config.validation_start,
        test_end=config.validation_end,
        horizon_sessions=config.horizon_sessions,
        eligible_by_execution_date=eligibility,
    )
    target_rows = build_multisource_factor_observations(
        daily.bars,
        {"qd_fund_flow": flow.observations},
        target.compile(),
        controls,
    )
    residual_rows, residual_audit = residualize_v23_style(
        target_rows,
        controls,
        target_direction=target.direction,
        control_direction=control_schema.direction,
    )
    residual = shared_non_overlapping(
        residual_rows,
        config.horizon_sessions,
        config.top_k,
    )
    control_by_key = {(row.execution_at, row.instrument): row for row in controls}
    residual_keys = tuple((row.execution_at, row.instrument) for row in residual)
    if any(key not in control_by_key for key in residual_keys):
        raise ValueError("V2.6 residual execution keys lack control observations")
    control = tuple(control_by_key[key] for key in residual_keys)
    regimes = classify_v25_regimes(
        control,
        direction=control_schema.direction,
        threshold=config.regime_threshold,
    )
    policy_rows = apply_v25_policy(
        residual,
        control,
        regimes,
        policy_id=config.frozen_policy_id,
        target_direction=target.direction,
        control_direction=control_schema.direction,
    )
    counts: dict[str, int] = defaultdict(int)
    for row in residual:
        if row.eligible:
            counts[row.execution_at] += 1
    minimum_cross_section = min(counts.values()) if counts else 0
    maximum_loaded_date = max(
        daily.audit.end_date,
        flow.audit.end_date,
        universe.research_end,
    )
    source = build_composite_snapshot_manifest(
        {
            "dynamic_universe": universe.source_snapshot_sha256,
            "qd_daily": daily.audit.source_sha256,
            "qd_fund_flow": flow.audit.source_sha256,
            "prior_evidence": config.prior_evidence_sha256,
        }
    )
    validation_sessions = len(execution_dates)
    checks = (
        (
            "DAILY_SESSIONS",
            validation_sessions >= config.minimum_daily_sessions,
            str(validation_sessions),
        ),
        (
            "PIT_MEMBERSHIP",
            universe.exact_fundamental_matches == universe.sessions,
            f"{universe.exact_fundamental_matches}/{universe.sessions}",
        ),
        (
            "UNIVERSE_SIZE",
            universe.mean_selected >= v21.minimum_mean_selected,
            f"{universe.mean_selected:.2f}",
        ),
        (
            "VALIDATION_PERIODS",
            len(regimes) >= config.minimum_validation_periods,
            str(len(regimes)),
        ),
        (
            "MINIMUM_CROSS_SECTION",
            minimum_cross_section >= config.top_k,
            str(minimum_cross_section),
        ),
        (
            "POINT_IN_TIME",
            residual_audit.point_in_time_visible and not residual_audit.forward_returns_used_in_fit,
            "visible; labels excluded",
        ),
        ("NO_2026_LOAD", maximum_loaded_date <= config.validation_end, maximum_loaded_date),
    )
    readiness = V26ReadinessReport(
        "READY" if all(item[1] for item in checks) else "DATA_BLOCKED",
        (config.validation_start, config.validation_end),
        (config.sealed_test_start, config.sealed_test_end),
        source.snapshot_sha256,
        daily.audit.source_sha256,
        flow.audit.source_sha256,
        universe.source_snapshot_sha256,
        validation_sessions,
        universe.sessions,
        universe.mean_selected,
        len(regimes),
        minimum_cross_section,
        maximum_loaded_date,
        checks,
    )
    output.mkdir(parents=True, exist_ok=True)
    (output / "v2.6-readiness.json").write_text(
        json.dumps(readiness.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return V26ValidationPanel(
        readiness,
        residual,
        control,
        policy_rows,
        regimes,
        target.version,
        target.direction,
    )


def _score(
    trial_id: str,
    trial_number: int,
    config: V26ValidationConfig,
    report: BaselineReport,
) -> V26ValidationScore:
    if report.metrics.net_sharpe is None:
        raise ValueError("V2.6 validation Sharpe is undefined")
    return V26ValidationScore(
        trial_id,
        trial_number,
        config.prior_trial_count + trial_number,
        report.metrics.periods,
        raw_sharpe(report),
        report.metrics.net_sharpe,
        report.metrics.net_total_return,
        report.metrics.max_drawdown,
        report.metrics.total_turnover,
        report.metrics.total_cost,
        report.metrics.capacity_clipped_notional,
        tuple(period.net_return for period in report.periods),
    )


def run_v26_validation(
    paths: LocalPathConfig,
    config_path: str | Path,
    *,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    ingested_at: str,
) -> tuple[V26ValidationReport, V26ValidationArtifacts]:
    if registry.global_trial_count() != 0:
        raise ValueError("V2.6 one-shot registry already contains an inferential trial")
    config_path = Path(config_path).expanduser().resolve()
    config = load_v26_validation_config(config_path)
    output = Path(output_dir).expanduser().resolve()
    panel = build_v26_validation_panel(
        paths,
        config_path,
        output_dir=output / "readiness",
        ingested_at=ingested_at,
    )
    if panel.readiness.decision != "READY":
        raise ValueError("V2.6 validation is DATA_BLOCKED before trial creation")
    snapshot = build_composite_snapshot_manifest(
        {
            "validation_source": panel.readiness.source_snapshot_sha256,
            "prior_evidence": config.prior_evidence_sha256,
        }
    )
    snapshot_id = registry.register_snapshot(
        snapshot,
        vendor_version="V2.6 one-shot 2025 validation",
        notes="2025 validation opened by explicit approval; 2026 remains sealed.",
    )
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            name="v2.6_one_shot_2025_validation",
            hypothesis="The frozen V2.5 risk-off cash policy generalizes to 2025.",
            dataset_snapshot_id=snapshot_id,
            code_version=code_version,
            search_space=canonical_json(asdict(config)),
        )
    )
    trial_id, trial_number = registry.create_trial(
        TrialSpec(
            experiment_id=experiment_id,
            model_name="v2.6_frozen_risk_off_cash_validation",
            factor_set=config.target_schema_id,
            hyperparams=canonical_json(
                {
                    "policy_id": config.frozen_policy_id,
                    "regime_threshold": config.regime_threshold,
                    "parameters_changed": False,
                }
            ),
            seed=config.seed,
            train_start="2022-01-04",
            train_end="2024-12-31",
            validation_start=config.validation_start,
            validation_end=config.validation_end,
            test_start=config.sealed_test_start,
            test_end=config.sealed_test_end,
        )
    )
    baseline_config = BaselineConfig(
        top_k=config.top_k,
        direction=panel.target_direction,
        commission_bps=config.commission_bps,
        sell_tax_bps=config.sell_tax_bps,
        slippage_bps=config.slippage_bps,
        impact_coefficient_bps=config.impact_coefficient_bps,
        max_participation_rate=config.max_participation_rate,
        periods_per_year=max(1, 252 // config.horizon_sessions),
        missing_holding_policy="stale_zero_return",
        allow_empty_selection=True,
    )
    baseline = run_momentum_topk(
        panel.policy_rows,
        BaselineLineage(
            config.target_schema_id,
            panel.target_version,
            snapshot_id,
            experiment_id,
            trial_id,
            code_version,
        ),
        baseline_config,
        initial_nav=config.initial_nav,
    )
    score = _score(trial_id, trial_number, config, baseline)
    temporal = temporal_diagnostics(
        baseline.periods,
        rolling_periods=config.rolling_periods,
        periods_per_year=baseline_config.periods_per_year,
    )
    regime_by_date = {item.execution_at: item.regime for item in panel.regimes}
    risk_on = sum(regime_by_date[item.execution_at] == "RISK_ON" for item in baseline.periods)
    risk_off = sum(regime_by_date[item.execution_at] == "RISK_OFF" for item in baseline.periods)
    evaluation = evaluation_rows(panel.policy_rows, horizon="20d")
    signal_placebo = run_placebo(
        evaluation,
        horizon="20d",
        direction=panel.target_direction,
        method="signal_shuffle",
        seed=config.seed,
        repetitions=config.placebo_repetitions,
    )
    return_placebo = run_placebo(
        evaluation,
        horizon="20d",
        direction=panel.target_direction,
        method="return_permutation",
        seed=config.seed + 1,
        repetitions=config.placebo_repetitions,
    )
    combined_returns = (*config.prior_research_period_returns, *score.period_returns)
    moments = sample_return_moments(combined_returns)
    combined_raw = sum(combined_returns) / len(combined_returns)
    dispersion = math.sqrt(
        sum((value - combined_raw) ** 2 for value in combined_returns) / (len(combined_returns) - 1)
    )
    combined_raw = 0.0 if dispersion == 0 else combined_raw / dispersion
    dsr = deflated_sharpe_ratio(
        observed_sharpe=combined_raw,
        trial_sharpes=(*config.prior_execution_raw_sharpes, combined_raw),
        recorded_trial_count=config.prior_trial_count + 1,
        observations=len(combined_returns),
        skewness=moments.skewness,
        excess_kurtosis=moments.excess_kurtosis,
    )
    engineering_checks = (
        ("READINESS", panel.readiness.decision == "READY", panel.readiness.decision),
        (
            "FROZEN_POLICY",
            config.frozen_policy_id == "risk_off_cash" and config.regime_threshold == 0,
            "unchanged",
        ),
        (
            "ONE_SHOT_TRIAL",
            registry.global_trial_count() == 1 and trial_number == 1,
            "new=1 cumulative=48",
        ),
        (
            "NO_CAPACITY_CLIP",
            score.capacity_clipped_notional == 0,
            f"{score.capacity_clipped_notional:.2f}",
        ),
        (
            "PBO_NOT_RESET",
            config.prior_policy_selection_pbo > 0 and V26_PBO_STATUS.startswith("NOT_APPLICABLE"),
            f"historical={config.prior_policy_selection_pbo:.2%}",
        ),
        (
            "FINAL_TEST_SEALED",
            panel.readiness.maximum_loaded_date <= config.validation_end,
            panel.readiness.maximum_loaded_date,
        ),
    )
    validation_checks = (
        (
            "POSITIVE_NET_RETURN",
            score.net_total_return > config.minimum_net_return,
            f"{score.net_total_return:.2%}",
        ),
        (
            "ANNUALIZED_SHARPE",
            score.annualized_net_sharpe >= config.minimum_annualized_sharpe,
            f"{score.annualized_net_sharpe:.6f}",
        ),
        (
            "MAX_DRAWDOWN",
            score.max_drawdown >= -config.maximum_drawdown,
            f"{score.max_drawdown:.2%}",
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
            "REGIME_COVERAGE",
            risk_on >= config.minimum_regime_periods and risk_off >= config.minimum_regime_periods,
            f"on={risk_on} off={risk_off}",
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
        (
            "COMBINED_DSR",
            dsr.probability >= config.min_combined_dsr_probability,
            f"p={dsr.probability}",
        ),
    )
    engineering_passed = all(item[1] for item in engineering_checks)
    validation_passed = engineering_passed and all(item[1] for item in validation_checks)
    decision = (
        "VALIDATION_PASS_FINAL_TEST_CANDIDATE" if validation_passed else "VALIDATION_FAIL_STOP"
    )
    report = V26ValidationReport(
        V26_METHOD_VERSION,
        experiment_id,
        trial_id,
        snapshot_id,
        panel.readiness,
        config.prior_evidence_sha256,
        config.frozen_policy_id,
        score,
        temporal,
        risk_on,
        risk_off,
        signal_placebo,
        return_placebo,
        moments,
        dsr,
        config.prior_policy_selection_pbo,
        V26_PBO_STATUS,
        config.prior_trial_count,
        registry.global_trial_count(),
        config.prior_trial_count + registry.global_trial_count(),
        engineering_checks,
        validation_checks,
        decision,
        False,
        False,
    )
    registry.record_trial_result(trial_id, canonical_json(report.to_dict()))
    output.mkdir(parents=True, exist_ok=True)
    readiness_path = output / "readiness" / "v2.6-readiness.json"
    json_path = output / "v2.6-validation.json"
    en_path = output / "v2.6-validation.en.md"
    zh_path = output / "v2.6-validation.zh.md"
    json_path.write_text(report.to_json() + "\n", encoding="utf-8", newline="\n")
    en_path.write_text(report.to_markdown("en"), encoding="utf-8", newline="\n")
    zh_path.write_text(report.to_markdown("zh"), encoding="utf-8", newline="\n")
    artifacts = {
        "readiness": readiness_path,
        "json": json_path,
        "markdown_en": en_path,
        "markdown_zh": zh_path,
    }
    replay_payload = {
        "replay_version": V26_REPLAY_VERSION,
        "method_version": report.method_version,
        "source_snapshot_sha256": report.readiness.source_snapshot_sha256,
        "prior_evidence_sha256": report.prior_evidence_sha256,
        "cumulative_trial_count": report.cumulative_trial_count,
        "decision": report.decision,
        "pbo_status": report.pbo_status,
        "live_trading_authorized": False,
        "final_test_window_opened": False,
        "artifacts": {name: sha256_file(path) for name, path in sorted(artifacts.items())},
    }
    replay_path = output / "v2.6-replay-manifest.json"
    replay_path.write_text(
        json.dumps(replay_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return report, V26ValidationArtifacts(
        readiness_path,
        json_path,
        en_path,
        zh_path,
        replay_path,
    )


def verify_v26_validation_replay(source: str | Path) -> V26ReplayVerification:
    path = Path(source).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("replay_version") != V26_REPLAY_VERSION:
        raise ValueError("unsupported V2.6 replay manifest")
    if payload.get("final_test_window_opened") or payload.get("live_trading_authorized"):
        raise ValueError("V2.6 replay violates release boundaries")
    if payload.get("cumulative_trial_count") != 48:
        raise ValueError("V2.6 replay cumulative trial count is not 48")
    if payload.get("pbo_status") != V26_PBO_STATUS:
        raise ValueError("V2.6 replay PBO status is invalid")
    mapping = {
        "readiness": path.parent / "readiness" / "v2.6-readiness.json",
        "json": path.parent / "v2.6-validation.json",
        "markdown_en": path.parent / "v2.6-validation.en.md",
        "markdown_zh": path.parent / "v2.6-validation.zh.md",
    }
    expected = payload.get("artifacts", {})
    mismatches = tuple(
        name
        for name, artifact in mapping.items()
        if not artifact.is_file() or expected.get(name) != sha256_file(artifact)
    )
    return V26ReplayVerification(not mismatches, len(mapping), mismatches)
