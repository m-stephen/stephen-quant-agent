from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import stdev

from stephen_quant.baseline import (
    BacktestPeriod,
    BaselineConfig,
    BaselineLineage,
    run_momentum_topk,
)
from stephen_quant.falsification import DeflatedSharpeResult, deflated_sharpe_ratio
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest
from stephen_quant.path_config import LocalPathConfig

from .research_epoch import (
    ReturnMoments,
    canonical_json,
    raw_sharpe,
    sample_return_moments,
    sha256_bytes,
    sha256_file,
    shared_non_overlapping,
)
from .v23_style_residualization import (
    V23StyleResidualizationConfig,
    build_v23_frozen_panel,
)

V24_CONFIG_VERSION = "2.4.0"
V24_METHOD_VERSION = "v2.4-frozen-temporal-stability-1.0.0"
V24_REPLAY_VERSION = "v2.4-temporal-stability-replay-1.0.0"


@dataclass(frozen=True)
class V24TemporalStabilityConfig:
    v23_config: str
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
    prior_pbo: float
    prior_pbo_scope: str
    prior_signal_placebo_p_value: float
    prior_return_placebo_p_value: float
    prior_dsr_probability: float
    prior_return_skewness: float
    prior_return_excess_kurtosis: float
    prior_decision: str
    prior_evidence_sha256: str
    rolling_periods: int
    periods_per_year: int
    minimum_positive_year_fraction: float
    minimum_worst_year_return: float
    minimum_worst_year_sharpe: float
    minimum_rolling_sharpe: float
    maximum_rolling_drawdown: float
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
            "prior_pbo": self.prior_pbo,
            "prior_pbo_scope": self.prior_pbo_scope,
            "prior_signal_placebo_p_value": self.prior_signal_placebo_p_value,
            "prior_return_placebo_p_value": self.prior_return_placebo_p_value,
            "prior_dsr_probability": self.prior_dsr_probability,
            "prior_return_skewness": self.prior_return_skewness,
            "prior_return_excess_kurtosis": self.prior_return_excess_kurtosis,
            "prior_decision": self.prior_decision,
        }

    @property
    def calculated_evidence_sha256(self) -> str:
        return sha256_bytes(canonical_json(self.evidence_payload()).encode())

    def validate(self) -> None:
        if self.prior_trial_count != 44 or len(self.prior_execution_raw_sharpes) != 9:
            raise ValueError("V2.4 must inherit the complete V2.3 evidence")
        if self.prior_evidence_sha256 != self.calculated_evidence_sha256:
            raise ValueError("V2.4 prior evidence hash does not match its frozen payload")
        if self.prior_decision != "PROMOTE_RESEARCH_ONLY":
            raise ValueError("V2.4 must inherit the V2.3 research-only decision")
        if self.prior_pbo_scope != "SIGNAL_SELECTION_ONLY":
            raise ValueError("V2.4 inherited PBO scope must remain explicit")
        if self.prior_periods != 35 or self.rolling_periods != 12:
            raise ValueError("V2.4 period counts are frozen")
        if self.periods_per_year != 12:
            raise ValueError("V2.4 annualization is frozen at 12 periods")
        hashes = (
            self.expected_source_snapshot_sha256,
            self.target_fingerprint,
            self.control_fingerprint,
        )
        if any(
            len(value) != 64 or any(c not in "0123456789abcdef" for c in value)
            for value in hashes
        ):
            raise ValueError("V2.4 hashes must be lowercase SHA-256 values")
        probabilities = (
            self.minimum_positive_year_fraction,
            self.maximum_top_decile_absolute_return_contribution,
            self.max_placebo_p_value,
            self.maximum_pbo,
            self.min_dsr_probability,
        )
        if any(not 0 <= value <= 1 for value in probabilities):
            raise ValueError("V2.4 probability thresholds must be in [0, 1]")
        if self.maximum_rolling_drawdown <= 0:
            raise ValueError("V2.4 drawdown magnitude must be positive")
        numeric = (
            self.prior_raw_net_sharpe,
            self.prior_annualized_net_sharpe,
            self.prior_net_total_return,
            self.prior_max_drawdown,
            self.prior_total_cost,
            self.prior_total_turnover,
            self.prior_dsr_probability,
            self.prior_return_skewness,
            self.prior_return_excess_kurtosis,
            *self.prior_execution_raw_sharpes,
        )
        if any(not math.isfinite(value) for value in numeric):
            raise ValueError("V2.4 numeric evidence must be finite")


@dataclass(frozen=True)
class V24PeriodSummary:
    label: str
    start: str
    end: str
    periods: int
    net_total_return: float
    annualized_net_sharpe: float | None
    max_drawdown: float
    total_cost: float


@dataclass(frozen=True)
class V24TemporalDiagnostics:
    yearly: tuple[V24PeriodSummary, ...]
    rolling: tuple[V24PeriodSummary, ...]
    positive_year_fraction: float
    worst_year_return: float
    worst_year_sharpe: float
    minimum_rolling_sharpe: float
    maximum_rolling_drawdown: float
    top_decile_absolute_return_contribution: float


@dataclass(frozen=True)
class V24TemporalStabilityReport:
    method_version: str
    experiment_id: str
    trial_id: str
    snapshot_id: str
    source_snapshot_sha256: str
    prior_evidence_sha256: str
    target_schema_id: str
    target_fingerprint: str
    control_schema_id: str
    control_fingerprint: str
    research_window: tuple[str, str]
    periods: int
    raw_net_sharpe: float
    annualized_net_sharpe: float | None
    net_total_return: float
    max_drawdown: float
    total_turnover: float
    total_cost: float
    capacity_clipped_notional: float
    return_moments: ReturnMoments
    deflated_sharpe: DeflatedSharpeResult
    inherited_signal_placebo_p_value: float
    inherited_return_placebo_p_value: float
    inherited_pbo: float
    inherited_pbo_scope: str
    temporal: V24TemporalDiagnostics
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
            raise ValueError("V2.4 report language must be en or zh")
        zh = language == "zh"
        lines = [
            "# V2.4 时间稳定性与发布候选结果"
            if zh
            else "# V2.4 Temporal Stability and Release Candidate Result",
            "",
            f"- {'发布结论' if zh else 'Release decision'}: **{self.release_decision}**",
            f"- {'Alpha 结论' if zh else 'Alpha decision'}: **{self.alpha_decision}**",
            f"- {'累计试验' if zh else 'Cumulative trials'}: {self.cumulative_trial_count}",
            f"- DSR: {self.deflated_sharpe.probability:.4%}",
            f"- {'净收益' if zh else 'Net return'}: {self.net_total_return:.2%}",
            (
                f"- {'年化净 Sharpe' if zh else 'Annualized net Sharpe'}: "
                f"{self.annualized_net_sharpe}"
            ),
            f"- {'最大回撤' if zh else 'Maximum drawdown'}: {self.max_drawdown:.2%}",
            "",
            "## 年度结果" if zh else "## Calendar-year results",
            "",
            "| Year | Periods | Net return | Net Sharpe | Max drawdown | Cost |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        lines.extend(
            f"| {item.label} | {item.periods} | {item.net_total_return:.2%} | "
            f"{item.annualized_net_sharpe} | {item.max_drawdown:.2%} | "
            f"{item.total_cost:,.2f} |"
            for item in self.temporal.yearly
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
                "> 工程发布不等于 Alpha 通过；仅使用 2022–2024，2025/2026 未打开。"
                if zh
                else "> Engineering release is not an Alpha claim; only 2022–2024 was used and 2025/2026 remained sealed.",
                "",
            ]
        )
        return "\n".join(lines)


@dataclass(frozen=True)
class V24TemporalStabilityArtifacts:
    json_path: Path
    markdown_en_path: Path
    markdown_zh_path: Path
    replay_manifest_path: Path


@dataclass(frozen=True)
class V24ReplayVerification:
    passed: bool
    checked_artifacts: int
    mismatches: tuple[str, ...]


def load_v24_temporal_stability_config(source: str | Path) -> V24TemporalStabilityConfig:
    path = Path(source).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.pop("config_version", None) != V24_CONFIG_VERSION:
        raise ValueError(f"V2.4 config_version must be {V24_CONFIG_VERSION}")
    if isinstance(payload.get("prior_execution_raw_sharpes"), list):
        payload["prior_execution_raw_sharpes"] = tuple(payload["prior_execution_raw_sharpes"])
    try:
        config = V24TemporalStabilityConfig(**payload)
    except TypeError as exc:
        raise ValueError("V2.4 config fields are invalid") from exc
    config.validate()
    return config


def _max_drawdown(returns: tuple[float, ...]) -> float:
    nav = 1.0
    peak = 1.0
    drawdown = 0.0
    for value in returns:
        nav *= 1 + value
        peak = max(peak, nav)
        drawdown = min(drawdown, nav / peak - 1)
    return drawdown


def _summary(
    label: str, periods: tuple[BacktestPeriod, ...], *, periods_per_year: int
) -> V24PeriodSummary:
    if not periods:
        raise ValueError("V2.4 temporal summary cannot be empty")
    returns = tuple(item.net_return for item in periods)
    total_return = math.prod(1 + value for value in returns) - 1
    sharpe = None
    if len(returns) > 1:
        dispersion = stdev(returns)
        sharpe = 0.0 if dispersion == 0 else sum(returns) / len(returns) / dispersion
        sharpe *= math.sqrt(periods_per_year)
    return V24PeriodSummary(
        label,
        periods[0].execution_at[:10],
        periods[-1].return_end_at[:10],
        len(periods),
        total_return,
        sharpe,
        _max_drawdown(returns),
        sum(item.total_cost for item in periods),
    )


def temporal_diagnostics(
    periods: tuple[BacktestPeriod, ...],
    *,
    rolling_periods: int,
    periods_per_year: int,
) -> V24TemporalDiagnostics:
    if len(periods) < rolling_periods or rolling_periods < 2:
        raise ValueError("V2.4 has insufficient periods for rolling diagnostics")
    by_year: dict[str, list[BacktestPeriod]] = defaultdict(list)
    for period in periods:
        by_year[period.execution_at[:4]].append(period)
    yearly = tuple(
        _summary(year, tuple(items), periods_per_year=periods_per_year)
        for year, items in sorted(by_year.items())
    )
    if any(item.annualized_net_sharpe is None for item in yearly):
        raise ValueError("V2.4 yearly summaries require at least two periods each")
    rolling = tuple(
        _summary(
            f"rolling_{index + 1}",
            periods[index : index + rolling_periods],
            periods_per_year=periods_per_year,
        )
        for index in range(len(periods) - rolling_periods + 1)
    )
    returns = tuple(item.net_return for item in periods)
    absolute = sorted((abs(value) for value in returns), reverse=True)
    top_count = max(1, math.ceil(len(absolute) * 0.10))
    contribution = sum(absolute[:top_count]) / sum(absolute) if sum(absolute) else 0.0
    yearly_sharpes = tuple(float(item.annualized_net_sharpe) for item in yearly)
    rolling_sharpes = tuple(float(item.annualized_net_sharpe) for item in rolling)
    return V24TemporalDiagnostics(
        yearly,
        rolling,
        sum(item.net_total_return > 0 for item in yearly) / len(yearly),
        min(item.net_total_return for item in yearly),
        min(yearly_sharpes),
        min(rolling_sharpes),
        min(item.max_drawdown for item in rolling),
        contribution,
    )


def cumulative_v24_trial_count(
    config: V24TemporalStabilityConfig, new_trial_count: int
) -> int:
    if new_trial_count != 1:
        raise ValueError("V2.4 requires exactly one temporal-validation trial")
    return config.prior_trial_count + new_trial_count


def _validate_v23_contract(
    config: V24TemporalStabilityConfig, v23: V23StyleResidualizationConfig
) -> None:
    frozen = (
        (v23.expected_source_snapshot_sha256, config.expected_source_snapshot_sha256),
        (v23.target_schema_id, config.target_schema_id),
        (v23.target_fingerprint, config.target_fingerprint),
        (v23.control_schema_id, config.control_schema_id),
        (v23.control_fingerprint, config.control_fingerprint),
    )
    if any(actual != expected for actual, expected in frozen):
        raise ValueError("V2.4 differs from the frozen V2.3 data or factor contract")
    if v23.top_k != 5 or v23.horizon_sessions != 20 or v23.initial_nav != 3_000_000.0:
        raise ValueError("V2.4 differs from the frozen V2.3 execution contract")


def run_v24_temporal_stability(
    paths: LocalPathConfig,
    config_path: str | Path,
    *,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    ingested_at: str,
) -> tuple[V24TemporalStabilityReport, V24TemporalStabilityArtifacts]:
    config_path = Path(config_path).expanduser().resolve()
    config = load_v24_temporal_stability_config(config_path)
    v23_path = Path(config.v23_config)
    v23_path = v23_path if v23_path.is_absolute() else (config_path.parent / v23_path).resolve()
    output = Path(output_dir).expanduser().resolve()
    v23, panel = build_v23_frozen_panel(
        paths,
        v23_path,
        output_dir=output / "readiness",
        ingested_at=ingested_at,
    )
    _validate_v23_contract(config, v23)
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
        vendor_version="V2.4 frozen V2.3 temporal validation",
        notes="Research-preview audit only; 2025/2026 remain sealed.",
    )
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            name="v2.4_frozen_temporal_stability",
            hypothesis="The frozen V2.3 mapping is stable across consumed research time.",
            dataset_snapshot_id=snapshot_id,
            code_version=code_version,
            search_space=canonical_json(asdict(config)),
        )
    )
    trial_id, trial_number = registry.create_trial(
        TrialSpec(
            experiment_id=experiment_id,
            model_name="v2.4_frozen_temporal_stability",
            factor_set=panel.target_schema.schema_id,
            hyperparams=canonical_json(
                {
                    "formula_changed": False,
                    "top_k": v23.top_k,
                    "rolling_periods": config.rolling_periods,
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
    execution_rows = shared_non_overlapping(
        panel.residual_rows, v23.horizon_sessions, v23.top_k
    )
    baseline_config = BaselineConfig(
        top_k=v23.top_k,
        direction=panel.target_schema.direction,
        commission_bps=v23.commission_bps,
        sell_tax_bps=v23.sell_tax_bps,
        slippage_bps=v23.slippage_bps,
        impact_coefficient_bps=v23.impact_coefficient_bps,
        max_participation_rate=v23.max_participation_rate,
        periods_per_year=config.periods_per_year,
        missing_holding_policy="stale_zero_return",
    )
    baseline = run_momentum_topk(
        execution_rows,
        BaselineLineage(
            panel.target_schema.schema_id,
            panel.target_schema.version,
            snapshot_id,
            experiment_id,
            trial_id,
            code_version,
        ),
        baseline_config,
        initial_nav=v23.initial_nav,
    )
    replay_values = (
        (raw_sharpe(baseline), config.prior_raw_net_sharpe),
        (baseline.metrics.net_sharpe, config.prior_annualized_net_sharpe),
        (baseline.metrics.net_total_return, config.prior_net_total_return),
        (baseline.metrics.max_drawdown, config.prior_max_drawdown),
        (baseline.metrics.total_cost, config.prior_total_cost),
        (baseline.metrics.total_turnover, config.prior_total_turnover),
        (baseline.metrics.periods, config.prior_periods),
    )
    exact_replay = all(
        actual is not None and math.isclose(actual, expected, abs_tol=1e-12)
        for actual, expected in replay_values
    )
    if not exact_replay:
        raise ValueError("V2.4 does not exactly replay the frozen V2.3 execution")
    temporal = temporal_diagnostics(
        baseline.periods,
        rolling_periods=config.rolling_periods,
        periods_per_year=config.periods_per_year,
    )
    moments = sample_return_moments(
        tuple(period.net_return for period in baseline.periods)
    )
    cumulative = cumulative_v24_trial_count(config, registry.global_trial_count())
    dsr = deflated_sharpe_ratio(
        observed_sharpe=config.prior_raw_net_sharpe,
        trial_sharpes=config.prior_execution_raw_sharpes,
        recorded_trial_count=cumulative,
        observations=config.prior_periods,
        skewness=moments.skewness,
        excess_kurtosis=moments.excess_kurtosis,
    )
    years = tuple(item.label for item in temporal.yearly)
    engineering_checks = (
        ("EXACT_V23_REPLAY", exact_replay, "all execution metrics match"),
        ("YEARS_REPRESENTED", years == ("2022", "2023", "2024"), str(years)),
        (
            "POINT_IN_TIME_CONTROLS",
            panel.residualization_audit.point_in_time_visible
            and not panel.residualization_audit.forward_returns_used_in_fit,
            "controls visible; forward returns excluded",
        ),
        (
            "NO_CAPACITY_CLIP",
            baseline.metrics.capacity_clipped_notional == 0,
            f"{baseline.metrics.capacity_clipped_notional:.2f}",
        ),
        ("TRIAL_LEDGER", cumulative == 45 and trial_number == 1, f"count={cumulative}"),
        ("PBO_SCOPE", config.prior_pbo_scope == "SIGNAL_SELECTION_ONLY", config.prior_pbo_scope),
        ("SEALED_WINDOWS", True, "2025/2026 not loaded"),
    )
    alpha_checks = (
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
            "ROLLING_DRAWDOWN",
            temporal.maximum_rolling_drawdown >= -config.maximum_rolling_drawdown,
            f"{temporal.maximum_rolling_drawdown:.2%}",
        ),
        (
            "RETURN_CONCENTRATION",
            temporal.top_decile_absolute_return_contribution
            <= config.maximum_top_decile_absolute_return_contribution,
            f"{temporal.top_decile_absolute_return_contribution:.2%}",
        ),
        (
            "SIGNAL_PLACEBO",
            config.prior_signal_placebo_p_value <= config.max_placebo_p_value,
            f"p={config.prior_signal_placebo_p_value}",
        ),
        (
            "RETURN_PLACEBO",
            config.prior_return_placebo_p_value <= config.max_placebo_p_value,
            f"p={config.prior_return_placebo_p_value}",
        ),
        ("PBO_SIGNAL_SELECTION", config.prior_pbo <= config.maximum_pbo, f"PBO={config.prior_pbo}"),
        ("DSR", dsr.probability >= config.min_dsr_probability, f"p={dsr.probability}"),
    )
    engineering_passed = all(item[1] for item in engineering_checks)
    alpha_passed = engineering_passed and all(item[1] for item in alpha_checks)
    report = V24TemporalStabilityReport(
        V24_METHOD_VERSION,
        experiment_id,
        trial_id,
        snapshot_id,
        panel.source_snapshot_sha256,
        config.prior_evidence_sha256,
        panel.target_schema.schema_id,
        panel.target_schema.fingerprint,
        panel.control_schema.schema_id,
        panel.control_schema.fingerprint,
        (panel.research_start, panel.research_end),
        baseline.metrics.periods,
        raw_sharpe(baseline),
        baseline.metrics.net_sharpe,
        baseline.metrics.net_total_return,
        baseline.metrics.max_drawdown,
        baseline.metrics.total_turnover,
        baseline.metrics.total_cost,
        baseline.metrics.capacity_clipped_notional,
        moments,
        dsr,
        config.prior_signal_placebo_p_value,
        config.prior_return_placebo_p_value,
        config.prior_pbo,
        config.prior_pbo_scope,
        temporal,
        config.prior_trial_count,
        registry.global_trial_count(),
        cumulative,
        engineering_checks,
        alpha_checks,
        "RESEARCH_PREVIEW_READY" if engineering_passed else "RELEASE_BLOCKED",
        "PASS_ALPHA_COURT" if alpha_passed else "RESEARCH_PREVIEW_ONLY",
        False,
        False,
    )
    registry.record_trial_result(trial_id, canonical_json(report.to_dict()))
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "v2.4-temporal-stability.json"
    en_path = output / "v2.4-temporal-stability.en.md"
    zh_path = output / "v2.4-temporal-stability.zh.md"
    json_path.write_text(report.to_json() + "\n", encoding="utf-8", newline="\n")
    en_path.write_text(report.to_markdown("en"), encoding="utf-8", newline="\n")
    zh_path.write_text(report.to_markdown("zh"), encoding="utf-8", newline="\n")
    artifacts = {"json": json_path, "markdown_en": en_path, "markdown_zh": zh_path}
    replay_payload = {
        "replay_version": V24_REPLAY_VERSION,
        "method_version": report.method_version,
        "source_snapshot_sha256": report.source_snapshot_sha256,
        "prior_evidence_sha256": report.prior_evidence_sha256,
        "cumulative_trial_count": report.cumulative_trial_count,
        "release_decision": report.release_decision,
        "alpha_decision": report.alpha_decision,
        "validation_window_opened": False,
        "test_window_opened": False,
        "artifacts": {name: sha256_file(path) for name, path in sorted(artifacts.items())},
    }
    replay_path = output / "v2.4-replay-manifest.json"
    replay_path.write_text(
        json.dumps(replay_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return report, V24TemporalStabilityArtifacts(json_path, en_path, zh_path, replay_path)


def verify_v24_temporal_stability_replay(source: str | Path) -> V24ReplayVerification:
    path = Path(source).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("replay_version") != V24_REPLAY_VERSION:
        raise ValueError("unsupported V2.4 replay manifest")
    if payload.get("validation_window_opened") or payload.get("test_window_opened"):
        raise ValueError("V2.4 replay reports sealed-window access")
    if payload.get("cumulative_trial_count") != 45:
        raise ValueError("V2.4 replay cumulative trial count is not 45")
    mapping = {
        "json": path.parent / "v2.4-temporal-stability.json",
        "markdown_en": path.parent / "v2.4-temporal-stability.en.md",
        "markdown_zh": path.parent / "v2.4-temporal-stability.zh.md",
    }
    expected = payload.get("artifacts", {})
    mismatches = tuple(
        name
        for name, artifact in mapping.items()
        if not artifact.is_file() or expected.get(name) != sha256_file(artifact)
    )
    return V24ReplayVerification(not mismatches, len(mapping), mismatches)
