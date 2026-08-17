from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from stephen_quant.baseline import (
    BaselineConfig,
    BaselineLineage,
    BaselineObservation,
    BaselineReport,
    run_momentum_topk,
)
from stephen_quant.discovery import v21_mechanism_generation_plan
from stephen_quant.discovery.attribution import _residuals
from stephen_quant.evaluation import EvaluationError, pearson_correlation
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
    QdAlternativeConfig,
    build_multisource_factor_observations,
    build_qmt_factor_observations,
    load_qd_alternative_directory,
    load_qd_daily_directory,
    read_dynamic_memberships,
)
from stephen_quant.v2.real_qd import (
    load_v21_real_research_config,
    resolve_discovery_config,
    run_v21_readiness,
)

from .v22_portfolio_breadth import (
    _canonical,
    _evaluation_rows,
    _execution_memberships,
    _raw_sharpe,
    _sha_file,
    _shared_non_overlapping,
)

V23_CONFIG_VERSION = "2.3.0"
V23_METHOD_VERSION = "v2.3-same-day-style-residualization-1.0.0"
V23_REPLAY_VERSION = "v2.3-style-residualization-replay-1.0.0"


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class V23StyleResidualizationConfig:
    v21_config: str
    expected_source_snapshot_sha256: str
    target_schema_id: str
    target_fingerprint: str
    control_schema_id: str
    control_fingerprint: str
    prior_trial_count: int
    prior_execution_raw_sharpes: tuple[float, ...]
    prior_annualized_net_sharpe: float
    prior_net_total_return: float
    prior_max_drawdown: float
    prior_pbo: float
    prior_signal_placebo_p_value: float
    prior_return_placebo_p_value: float
    prior_dsr_probability: float
    prior_decision: str
    prior_evidence_sha256: str
    top_k: int
    horizon_sessions: int
    initial_nav: float
    commission_bps: float
    sell_tax_bps: float
    slippage_bps: float
    impact_coefficient_bps: float
    max_participation_rate: float
    placebo_repetitions: int
    max_placebo_p_value: float
    min_dsr_probability: float
    maximum_pbo: float
    minimum_sharpe_improvement: float
    maximum_drawdown: float
    maximum_mean_abs_control_correlation: float
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
            "prior_annualized_net_sharpe": self.prior_annualized_net_sharpe,
            "prior_net_total_return": self.prior_net_total_return,
            "prior_max_drawdown": self.prior_max_drawdown,
            "prior_pbo": self.prior_pbo,
            "prior_signal_placebo_p_value": self.prior_signal_placebo_p_value,
            "prior_return_placebo_p_value": self.prior_return_placebo_p_value,
            "prior_dsr_probability": self.prior_dsr_probability,
            "prior_decision": self.prior_decision,
        }

    @property
    def calculated_evidence_sha256(self) -> str:
        return _sha_bytes(_canonical(self.evidence_payload()).encode())

    def validate(self) -> None:
        if self.prior_trial_count != 42 or len(self.prior_execution_raw_sharpes) != 8:
            raise ValueError("V2.3 must carry forward the complete V2.2 evidence")
        if self.prior_evidence_sha256 != self.calculated_evidence_sha256:
            raise ValueError("V2.3 prior evidence hash does not match its frozen payload")
        if self.prior_decision != "REJECT_NO_IMPROVEMENT":
            raise ValueError("V2.3 must inherit the rejected V2.2 decision")
        if self.top_k != 5 or self.horizon_sessions != 20 or self.initial_nav != 3_000_000.0:
            raise ValueError("V2.3 Top-K, horizon, and NAV are frozen")
        hashes = (
            self.expected_source_snapshot_sha256,
            self.target_fingerprint,
            self.control_fingerprint,
        )
        if any(
            len(value) != 64 or any(c not in "0123456789abcdef" for c in value)
            for value in hashes
        ):
            raise ValueError("V2.3 hashes must be lowercase SHA-256 values")
        if self.placebo_repetitions < 1 or self.maximum_drawdown <= 0:
            raise ValueError("V2.3 falsification settings are invalid")
        if not 0 < self.min_dsr_probability < 1 or not 0 < self.max_placebo_p_value < 1:
            raise ValueError("V2.3 probability thresholds are invalid")
        if not 0 <= self.maximum_pbo < 1 or not 0 < self.max_participation_rate <= 1:
            raise ValueError("V2.3 PBO or capacity threshold is invalid")
        if not 0 <= self.maximum_mean_abs_control_correlation <= 1:
            raise ValueError("V2.3 control-correlation threshold is invalid")
        numeric = (
            self.prior_annualized_net_sharpe,
            self.prior_net_total_return,
            self.prior_max_drawdown,
            self.prior_dsr_probability,
            *self.prior_execution_raw_sharpes,
            self.commission_bps,
            self.sell_tax_bps,
            self.slippage_bps,
            self.impact_coefficient_bps,
            self.minimum_sharpe_improvement,
        )
        if any(not math.isfinite(value) for value in numeric):
            raise ValueError("V2.3 numeric settings must be finite")


@dataclass(frozen=True)
class V23ExecutionScore:
    name: str
    trial_id: str | None
    local_trial_number: int | None
    cumulative_trial_number: int | None
    periods: int
    raw_net_sharpe: float
    annualized_net_sharpe: float | None
    net_total_return: float
    max_drawdown: float
    total_turnover: float
    total_cost: float
    capacity_clipped_notional: float


@dataclass(frozen=True)
class V23ResidualizationAudit:
    dates: int
    observations: int
    signal_changed: bool
    mean_abs_price_control_correlation: float
    mean_abs_log_adv_correlation: float
    maximum_abs_price_control_correlation: float
    maximum_abs_log_adv_correlation: float
    forward_returns_used_in_fit: bool
    point_in_time_visible: bool


@dataclass(frozen=True)
class V23NegativeControl:
    trial_id: str
    local_trial_number: int
    cumulative_trial_number: int
    annualized_net_sharpe: float | None
    net_total_return: float
    passed: bool


@dataclass(frozen=True)
class V23StyleResidualizationReport:
    method_version: str
    experiment_id: str
    snapshot_id: str
    source_snapshot_sha256: str
    prior_evidence_sha256: str
    target_schema_id: str
    target_fingerprint: str
    control_schema_id: str
    control_fingerprint: str
    research_window: tuple[str, str]
    raw_control: V23ExecutionScore
    residualized_candidate: V23ExecutionScore
    residualization_audit: V23ResidualizationAudit
    negative_control: V23NegativeControl
    placebo_signal: PlaceboResult
    placebo_return: PlaceboResult
    deflated_sharpe: DeflatedSharpeResult
    inherited_pbo: float
    prior_trial_count: int
    new_trial_count: int
    cumulative_trial_count: int
    checks: tuple[tuple[str, bool, str], ...]
    decision: str
    validation_window_opened: bool
    test_window_opened: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"en", "zh"}:
            raise ValueError("V2.3 report language must be en or zh")
        zh = language == "zh"
        raw, candidate = self.raw_control, self.residualized_candidate
        lines = [
            "# V2.3 风格残差化研究结果" if zh else "# V2.3 Style Residualization Result",
            "",
            f"- {'结论' if zh else 'Decision'}: **{self.decision}**",
            f"- {'固定因子' if zh else 'Frozen factor'}: `{self.target_schema_id}`",
            f"- {'控制变量' if zh else 'Controls'}: `{self.control_schema_id}` + `log(ADV20)`",
            f"- {'累计试验' if zh else 'Cumulative trials'}: {self.cumulative_trial_count}",
            f"- DSR: {self.deflated_sharpe.probability:.4%}",
            "",
            "| Variant | Net return | Net Sharpe | Max drawdown | Turnover | Cost |",
            "|---|---:|---:|---:|---:|---:|",
            (
                f"| Raw Top-5 | {raw.net_total_return:.2%} | {raw.annualized_net_sharpe:.4f} | "
                f"{raw.max_drawdown:.2%} | {raw.total_turnover:.4f} | {raw.total_cost:,.2f} |"
            ),
            (
                f"| Residualized Top-5 | {candidate.net_total_return:.2%} | "
                f"{candidate.annualized_net_sharpe:.4f} | {candidate.max_drawdown:.2%} | "
                f"{candidate.total_turnover:.4f} | {candidate.total_cost:,.2f} |"
            ),
            "",
            "## 门禁" if zh else "## Gates",
            "",
        ]
        lines.extend(
            f"- {'通过' if passed and zh else 'PASS' if passed else '失败' if zh else 'FAIL'} "
            f"`{name}`: {detail}"
            for name, passed, detail in self.checks
        )
        lines.extend(
            [
                "",
                "> 仅使用已消耗的 2022–2024 研究数据；2025/2026 未打开。"
                if zh
                else "> Uses consumed 2022–2024 research data only; 2025/2026 remained sealed.",
                "",
            ]
        )
        return "\n".join(lines)


@dataclass(frozen=True)
class V23StyleResidualizationArtifacts:
    json_path: Path
    markdown_en_path: Path
    markdown_zh_path: Path
    replay_manifest_path: Path


@dataclass(frozen=True)
class V23ReplayVerification:
    passed: bool
    checked_artifacts: int
    mismatches: tuple[str, ...]


def load_v23_style_residualization_config(
    source: str | Path,
) -> V23StyleResidualizationConfig:
    path = Path(source).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.pop("config_version", None) != V23_CONFIG_VERSION:
        raise ValueError(f"V2.3 config_version must be {V23_CONFIG_VERSION}")
    if isinstance(payload.get("prior_execution_raw_sharpes"), list):
        payload["prior_execution_raw_sharpes"] = tuple(payload["prior_execution_raw_sharpes"])
    try:
        config = V23StyleResidualizationConfig(**payload)
    except TypeError as exc:
        raise ValueError("V2.3 config fields are invalid") from exc
    config.validate()
    return config


def _visible(row: BaselineObservation) -> bool:
    return (
        row.signal_available_at < row.execution_at
        and row.liquidity_available_at < row.execution_at
    )


def residualize_v23_style(
    target_rows: tuple[BaselineObservation, ...],
    control_rows: tuple[BaselineObservation, ...],
    *,
    target_direction: int,
    control_direction: int,
) -> tuple[tuple[BaselineObservation, ...], V23ResidualizationAudit]:
    if target_direction not in {-1, 1} or control_direction not in {-1, 1}:
        raise ValueError("V2.3 factor directions must be -1 or 1")
    target = {(row.execution_at, row.instrument): row for row in target_rows}
    control = {(row.execution_at, row.instrument): row for row in control_rows}
    if len(target) != len(target_rows) or len(control) != len(control_rows):
        raise ValueError("V2.3 residualization panel contains duplicate keys")
    if set(target) != set(control):
        raise ValueError("V2.3 target and control panels must match exactly")
    by_date: dict[str, list[tuple[str, BaselineObservation]]] = defaultdict(list)
    for (execution_at, instrument), row in target.items():
        by_date[execution_at].append((instrument, row))

    replacements: dict[tuple[str, str], float] = {}
    price_correlations: list[float] = []
    adv_correlations: list[float] = []
    changed = False
    visible = True
    observation_count = 0
    used_dates = 0
    for execution_at, cross_section in sorted(by_date.items()):
        ordered = sorted(
            ((instrument, row) for instrument, row in cross_section if row.eligible),
            key=lambda item: item[0],
        )
        if len(ordered) < 5:
            continue
        oriented_target: list[float] = []
        design: list[list[float]] = []
        for instrument, row in ordered:
            peer = control[(execution_at, instrument)]
            if peer.eligible != row.eligible or peer.forward_return != row.forward_return:
                raise ValueError("V2.3 target and control timing/labels are inconsistent")
            visible = visible and _visible(row) and _visible(peer)
            oriented_target.append(target_direction * row.signal)
            design.append(
                [control_direction * peer.signal, math.log(row.average_daily_value)]
            )
        residuals = _residuals(oriented_target, design)
        price = [row[0] for row in design]
        adv = [row[1] for row in design]
        try:
            price_correlations.append(abs(pearson_correlation(residuals, price)))
            adv_correlations.append(abs(pearson_correlation(residuals, adv)))
        except EvaluationError as exc:
            raise ValueError("V2.3 control correlation is undefined") from exc
        for (instrument, _), raw, residual in zip(
            ordered, oriented_target, residuals, strict=True
        ):
            replacements[(execution_at, instrument)] = residual * target_direction
            changed = changed or not math.isclose(raw, residual, abs_tol=1e-12)
        observation_count += len(ordered)
        used_dates += 1
    if not replacements or not price_correlations or not adv_correlations:
        raise ValueError("V2.3 residualization produced no valid cross-sections")
    if not visible:
        raise ValueError("V2.3 residualization controls are not point-in-time visible")
    output = tuple(
        replace(row, signal=replacements[(row.execution_at, row.instrument)])
        if (row.execution_at, row.instrument) in replacements
        else row
        for row in target_rows
    )
    audit = V23ResidualizationAudit(
        used_dates,
        observation_count,
        changed,
        sum(price_correlations) / len(price_correlations),
        sum(adv_correlations) / len(adv_correlations),
        max(price_correlations),
        max(adv_correlations),
        False,
        True,
    )
    return output, audit


def cumulative_v23_trial_count(
    config: V23StyleResidualizationConfig, new_trial_count: int
) -> int:
    if new_trial_count != 2:
        raise ValueError("V2.3 requires one candidate and one negative-control trial")
    return config.prior_trial_count + new_trial_count


def _score(
    name: str,
    report: BaselineReport,
    *,
    trial_id: str | None,
    local_trial_number: int | None,
    prior_trial_count: int,
) -> V23ExecutionScore:
    return V23ExecutionScore(
        name,
        trial_id,
        local_trial_number,
        None if local_trial_number is None else prior_trial_count + local_trial_number,
        report.metrics.periods,
        _raw_sharpe(report),
        report.metrics.net_sharpe,
        report.metrics.net_total_return,
        report.metrics.max_drawdown,
        report.metrics.total_turnover,
        report.metrics.total_cost,
        report.metrics.capacity_clipped_notional,
    )


def run_v23_style_residualization(
    paths: LocalPathConfig,
    config_path: str | Path,
    *,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    ingested_at: str,
) -> tuple[V23StyleResidualizationReport, V23StyleResidualizationArtifacts]:
    config_path = Path(config_path).expanduser().resolve()
    config = load_v23_style_residualization_config(config_path)
    v21_path = Path(config.v21_config)
    v21_path = v21_path if v21_path.is_absolute() else (config_path.parent / v21_path).resolve()
    v21 = load_v21_real_research_config(v21_path)
    discovery = resolve_discovery_config(v21, v21_path)
    output = Path(output_dir).expanduser().resolve()
    readiness, readiness_artifacts = run_v21_readiness(
        paths, v21, output / "readiness", ingested_at=ingested_at
    )
    if readiness.decision != "READY":
        raise ValueError("V2.3 is blocked by V2.1 readiness")
    if readiness.source_snapshot_sha256 != config.expected_source_snapshot_sha256:
        raise ValueError("V2.3 source snapshot differs from frozen evidence")

    memberships = read_dynamic_memberships(readiness_artifacts.membership_jsonl_path)
    instruments = tuple(sorted({item for members in memberships.values() for item in members}))
    daily = load_qd_daily_directory(
        paths.choose("qd_daily_dir", None, "qd_daily_dir"),
        start_date=discovery.data_start,
        end_date=discovery.research_end,
        instruments=instruments,
        adjustment="back_ratio",
    )
    flow = load_qd_alternative_directory(
        paths.choose("qd_fund_flow_dir", None, "qd_fund_flow_dir"),
        QdAlternativeConfig(
            source_kind="fund_flow",
            start_date=discovery.research_start,
            end_date=discovery.research_end,
            ingested_at=ingested_at,
            instruments=instruments,
        ),
    )
    source_manifest = build_composite_snapshot_manifest(
        {
            "v21_readiness": readiness.source_snapshot_sha256,
            "qd_daily": daily.audit.source_sha256,
            "qd_fund_flow": flow.audit.source_sha256,
            "prior_evidence": config.prior_evidence_sha256,
        }
    )
    snapshot_id = registry.register_snapshot(
        source_manifest,
        vendor_version="V2.3 frozen V2.1 signal and decision-time controls",
        notes="Research-only 2022-2024; 2025/2026 remain sealed.",
    )
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            name="v2.3_same_day_style_residualization",
            hypothesis="Same-day style residualization improves frozen Top-5 execution.",
            dataset_snapshot_id=snapshot_id,
            code_version=code_version,
            search_space=_canonical(asdict(config)),
        )
    )

    templates = {item.template_id: item for item in v21_mechanism_generation_plan().templates}
    target = templates["flow_confirmation"].render(window=20, horizon="20d")
    control_schema = templates["price_momentum"].render(window=5, horizon="20d")
    if target.schema_id != config.target_schema_id or target.fingerprint != config.target_fingerprint:
        raise ValueError("V2.3 target factor differs from the frozen contract")
    if (
        control_schema.schema_id != config.control_schema_id
        or control_schema.fingerprint != config.control_fingerprint
    ):
        raise ValueError("V2.3 style control differs from the frozen contract")
    execution_dates = sorted(
        {
            bar.trade_date
            for bar in daily.bars
            if discovery.research_start <= bar.trade_date <= discovery.research_end
        }
    )
    eligibility = _execution_memberships(memberships, execution_dates)
    controls = build_qmt_factor_observations(
        daily.bars,
        control_schema.compile(),
        test_start=discovery.research_start,
        test_end=discovery.research_end,
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
    raw_execution = _shared_non_overlapping(
        target_rows, config.horizon_sessions, config.top_k
    )
    residual_execution = _shared_non_overlapping(
        residual_rows, config.horizon_sessions, config.top_k
    )
    if tuple((row.execution_at, row.instrument) for row in raw_execution) != tuple(
        (row.execution_at, row.instrument) for row in residual_execution
    ):
        raise ValueError("V2.3 raw and residual execution panels differ")
    baseline_config = BaselineConfig(
        top_k=config.top_k,
        direction=target.direction,
        commission_bps=config.commission_bps,
        sell_tax_bps=config.sell_tax_bps,
        slippage_bps=config.slippage_bps,
        impact_coefficient_bps=config.impact_coefficient_bps,
        max_participation_rate=config.max_participation_rate,
        periods_per_year=max(1, 252 // config.horizon_sessions),
        missing_holding_policy="stale_zero_return",
    )
    raw_report = run_momentum_topk(
        raw_execution,
        BaselineLineage(
            target.schema_id, target.version, snapshot_id, experiment_id, "control_replay", code_version
        ),
        baseline_config,
        initial_nav=config.initial_nav,
    )
    raw_score = _score(
        "raw_control",
        raw_report,
        trial_id=None,
        local_trial_number=None,
        prior_trial_count=config.prior_trial_count,
    )
    control_values = (
        (raw_score.annualized_net_sharpe, config.prior_annualized_net_sharpe),
        (raw_score.net_total_return, config.prior_net_total_return),
        (raw_score.max_drawdown, config.prior_max_drawdown),
    )
    if any(
        actual is None or not math.isclose(actual, expected, abs_tol=1e-12)
        for actual, expected in control_values
    ):
        raise ValueError("V2.3 raw Top-5 control does not exactly replay frozen V2.1 execution")

    candidate_trial_id, candidate_trial_number = registry.create_trial(
        TrialSpec(
            experiment_id=experiment_id,
            model_name="v2.3_same_day_style_residualization",
            factor_set=target.schema_id,
            hyperparams=_canonical(
                {
                    "top_k": config.top_k,
                    "controls": [control_schema.schema_id, "log_adv20"],
                    "fit_scope": "same_decision_date_cross_section",
                }
            ),
            seed=config.seed,
            train_start=discovery.research_start,
            train_end=discovery.research_end,
            validation_start=discovery.validation_start,
            validation_end=discovery.validation_end,
            test_start=discovery.test_start,
            test_end=discovery.test_end,
        )
    )
    candidate_report = run_momentum_topk(
        residual_execution,
        BaselineLineage(
            target.schema_id,
            target.version,
            snapshot_id,
            experiment_id,
            candidate_trial_id,
            code_version,
        ),
        baseline_config,
        initial_nav=config.initial_nav,
    )
    candidate = _score(
        "style_residualized",
        candidate_report,
        trial_id=candidate_trial_id,
        local_trial_number=candidate_trial_number,
        prior_trial_count=config.prior_trial_count,
    )
    registry.record_trial_result(candidate_trial_id, _canonical(asdict(candidate)))

    negative_trial_id, negative_trial_number = registry.create_trial(
        TrialSpec(
            experiment_id=experiment_id,
            model_name="v2.3_reversed_residualized_ranking_negative_control",
            factor_set=target.schema_id,
            hyperparams=_canonical(
                {"top_k": config.top_k, "direction": -target.direction}
            ),
            seed=config.seed,
            train_start=discovery.research_start,
            train_end=discovery.research_end,
            validation_start=discovery.validation_start,
            validation_end=discovery.validation_end,
            test_start=discovery.test_start,
            test_end=discovery.test_end,
        )
    )
    negative_report = run_momentum_topk(
        residual_execution,
        BaselineLineage(
            target.schema_id,
            target.version,
            snapshot_id,
            experiment_id,
            negative_trial_id,
            code_version,
        ),
        replace(baseline_config, direction=-target.direction),
        initial_nav=config.initial_nav,
    )
    negative = V23NegativeControl(
        negative_trial_id,
        negative_trial_number,
        config.prior_trial_count + negative_trial_number,
        negative_report.metrics.net_sharpe,
        negative_report.metrics.net_total_return,
        negative_report.metrics.net_sharpe is not None
        and negative_report.metrics.net_sharpe <= 0,
    )
    registry.record_trial_result(negative_trial_id, _canonical(asdict(negative)))
    cumulative = cumulative_v23_trial_count(config, registry.global_trial_count())
    dsr = deflated_sharpe_ratio(
        observed_sharpe=candidate.raw_net_sharpe,
        trial_sharpes=(*config.prior_execution_raw_sharpes, candidate.raw_net_sharpe),
        recorded_trial_count=cumulative,
        observations=candidate.periods,
    )
    evaluation = _evaluation_rows(residual_rows)
    signal_placebo = run_placebo(
        evaluation,
        horizon="20d",
        direction=target.direction,
        method="signal_shuffle",
        seed=config.seed,
        repetitions=config.placebo_repetitions,
    )
    return_placebo = run_placebo(
        evaluation,
        horizon="20d",
        direction=target.direction,
        method="return_permutation",
        seed=config.seed + 1,
        repetitions=config.placebo_repetitions,
    )
    candidate_sharpe = candidate.annualized_net_sharpe or float("-inf")
    correlations_pass = (
        residual_audit.mean_abs_price_control_correlation
        <= config.maximum_mean_abs_control_correlation
        and residual_audit.mean_abs_log_adv_correlation
        <= config.maximum_mean_abs_control_correlation
    )
    checks = (
        ("CONTROL_REPLAY", True, "raw Top-5 exactly reproduces V2.1"),
        ("SIGNAL_CHANGED", residual_audit.signal_changed, "residual signal differs from raw"),
        (
            "CONTROL_EXPOSURE",
            correlations_pass,
            (
                "mean |corr| price="
                f"{residual_audit.mean_abs_price_control_correlation:.6g}, "
                f"logADV={residual_audit.mean_abs_log_adv_correlation:.6g}"
            ),
        ),
        (
            "SHARPE_IMPROVEMENT",
            candidate_sharpe
            >= config.prior_annualized_net_sharpe + config.minimum_sharpe_improvement,
            (
                f"{candidate_sharpe:.6f} vs required "
                f"{config.prior_annualized_net_sharpe + config.minimum_sharpe_improvement:.6f}"
            ),
        ),
        (
            "MAX_DRAWDOWN",
            candidate.max_drawdown >= -config.maximum_drawdown,
            f"{candidate.max_drawdown:.2%}",
        ),
        ("POSITIVE_NET_RETURN", candidate.net_total_return > 0, f"{candidate.net_total_return:.2%}"),
        (
            "NO_CAPACITY_CLIP",
            candidate.capacity_clipped_notional == 0,
            f"{candidate.capacity_clipped_notional:.2f}",
        ),
        ("NEGATIVE_CONTROL", negative.passed, f"Sharpe={negative.annualized_net_sharpe}"),
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
        ("PBO", config.prior_pbo <= config.maximum_pbo, f"PBO={config.prior_pbo}"),
        ("DSR", dsr.probability >= config.min_dsr_probability, f"p={dsr.probability}"),
        ("SEALED_WINDOWS", True, "2025/2026 not loaded"),
    )
    improvement_passed = all(item[1] for item in checks[:8])
    alpha_passed = improvement_passed and all(item[1] for item in checks[8:])
    decision = (
        "PASS_ALPHA_COURT"
        if alpha_passed
        else "PROMOTE_RESEARCH_ONLY"
        if improvement_passed
        else "REJECT_NO_IMPROVEMENT"
    )
    report = V23StyleResidualizationReport(
        V23_METHOD_VERSION,
        experiment_id,
        snapshot_id,
        readiness.source_snapshot_sha256,
        config.prior_evidence_sha256,
        target.schema_id,
        target.fingerprint,
        control_schema.schema_id,
        control_schema.fingerprint,
        (discovery.research_start, discovery.research_end),
        raw_score,
        candidate,
        residual_audit,
        negative,
        signal_placebo,
        return_placebo,
        dsr,
        config.prior_pbo,
        config.prior_trial_count,
        registry.global_trial_count(),
        cumulative,
        checks,
        decision,
        False,
        False,
    )
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "v2.3-style-residualization.json"
    en_path = output / "v2.3-style-residualization.en.md"
    zh_path = output / "v2.3-style-residualization.zh.md"
    json_path.write_text(report.to_json() + "\n", encoding="utf-8", newline="\n")
    en_path.write_text(report.to_markdown("en"), encoding="utf-8", newline="\n")
    zh_path.write_text(report.to_markdown("zh"), encoding="utf-8", newline="\n")
    artifacts = {"json": json_path, "markdown_en": en_path, "markdown_zh": zh_path}
    replay_payload = {
        "replay_version": V23_REPLAY_VERSION,
        "method_version": report.method_version,
        "source_snapshot_sha256": report.source_snapshot_sha256,
        "prior_evidence_sha256": report.prior_evidence_sha256,
        "cumulative_trial_count": report.cumulative_trial_count,
        "validation_window_opened": False,
        "test_window_opened": False,
        "artifacts": {name: _sha_file(path) for name, path in sorted(artifacts.items())},
    }
    replay_path = output / "v2.3-replay-manifest.json"
    replay_path.write_text(
        json.dumps(replay_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return report, V23StyleResidualizationArtifacts(
        json_path, en_path, zh_path, replay_path
    )


def verify_v23_style_residualization_replay(source: str | Path) -> V23ReplayVerification:
    path = Path(source).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("replay_version") != V23_REPLAY_VERSION:
        raise ValueError("unsupported V2.3 replay manifest")
    if payload.get("validation_window_opened") or payload.get("test_window_opened"):
        raise ValueError("V2.3 replay reports sealed-window access")
    if payload.get("cumulative_trial_count") != 44:
        raise ValueError("V2.3 replay cumulative trial count is not 44")
    mapping = {
        "json": path.parent / "v2.3-style-residualization.json",
        "markdown_en": path.parent / "v2.3-style-residualization.en.md",
        "markdown_zh": path.parent / "v2.3-style-residualization.zh.md",
    }
    expected = payload.get("artifacts", {})
    mismatches = tuple(
        name
        for name, artifact in mapping.items()
        if not artifact.is_file() or expected.get(name) != _sha_file(artifact)
    )
    return V23ReplayVerification(not mismatches, len(mapping), mismatches)
