from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import stdev

from stephen_quant.baseline import (
    BaselineConfig,
    BaselineLineage,
    BaselineObservation,
    BaselineReport,
    run_momentum_topk,
)
from stephen_quant.discovery import v21_mechanism_generation_plan
from stephen_quant.evaluation import EvaluationObservation
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

V22_CONFIG_VERSION = "2.2.0"
V22_METHOD_VERSION = "v2.2-frozen-signal-portfolio-breadth-1.0.0"
V22_REPLAY_VERSION = "v2.2-portfolio-breadth-replay-1.0.0"


def _canonical(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class V22PortfolioBreadthConfig:
    v21_config: str
    expected_source_snapshot_sha256: str
    prior_research_semantic_sha256: str
    target_schema_id: str
    target_fingerprint: str
    prior_trial_count: int
    prior_execution_raw_sharpes: tuple[float, ...]
    prior_annualized_net_sharpe: float
    prior_net_total_return: float
    prior_max_drawdown: float
    prior_pbo: float
    prior_signal_placebo_p_value: float
    prior_return_placebo_p_value: float
    prior_evidence_sha256: str
    top_ks: tuple[int, ...]
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
    seed: int

    def evidence_payload(self) -> dict[str, object]:
        return {
            "expected_source_snapshot_sha256": self.expected_source_snapshot_sha256,
            "prior_research_semantic_sha256": self.prior_research_semantic_sha256,
            "target_schema_id": self.target_schema_id,
            "target_fingerprint": self.target_fingerprint,
            "prior_trial_count": self.prior_trial_count,
            "prior_execution_raw_sharpes": self.prior_execution_raw_sharpes,
            "prior_annualized_net_sharpe": self.prior_annualized_net_sharpe,
            "prior_net_total_return": self.prior_net_total_return,
            "prior_max_drawdown": self.prior_max_drawdown,
            "prior_pbo": self.prior_pbo,
            "prior_signal_placebo_p_value": self.prior_signal_placebo_p_value,
            "prior_return_placebo_p_value": self.prior_return_placebo_p_value,
        }

    @property
    def calculated_evidence_sha256(self) -> str:
        return _sha_bytes(_canonical(self.evidence_payload()).encode())

    def validate(self) -> None:
        if self.top_ks != (5, 10, 15, 20):
            raise ValueError("V2.2 top_ks must remain the frozen 5/10/15/20 grid")
        if self.prior_trial_count != 37 or len(self.prior_execution_raw_sharpes) != 4:
            raise ValueError("V2.2 must carry forward the complete V2.1 evidence")
        if self.prior_evidence_sha256 != self.calculated_evidence_sha256:
            raise ValueError("V2.2 prior evidence hash does not match its frozen payload")
        if self.horizon_sessions != 20 or self.initial_nav != 3_000_000.0:
            raise ValueError("V2.2 horizon and NAV are frozen")
        hashes = (self.expected_source_snapshot_sha256, self.prior_research_semantic_sha256, self.target_fingerprint)
        if any(len(value) != 64 or any(c not in "0123456789abcdef" for c in value) for value in hashes):
            raise ValueError("V2.2 hashes must be lowercase SHA-256 values")
        if self.placebo_repetitions < 1 or self.maximum_drawdown <= 0:
            raise ValueError("V2.2 falsification settings are invalid")
        if not 0 < self.min_dsr_probability < 1 or not 0 < self.max_placebo_p_value < 1:
            raise ValueError("V2.2 probability thresholds are invalid")
        if not 0 <= self.maximum_pbo < 1 or not 0 < self.max_participation_rate <= 1:
            raise ValueError("V2.2 PBO or capacity threshold is invalid")
        numeric = (
            self.prior_annualized_net_sharpe,
            self.prior_net_total_return,
            self.prior_max_drawdown,
            *self.prior_execution_raw_sharpes,
            self.commission_bps,
            self.sell_tax_bps,
            self.slippage_bps,
            self.impact_coefficient_bps,
            self.minimum_sharpe_improvement,
        )
        if any(not math.isfinite(value) for value in numeric):
            raise ValueError("V2.2 numeric settings must be finite")


@dataclass(frozen=True)
class V22BreadthScore:
    top_k: int
    trial_id: str
    local_trial_number: int
    cumulative_trial_number: int
    periods: int
    raw_net_sharpe: float
    annualized_net_sharpe: float | None
    net_total_return: float
    max_drawdown: float
    total_turnover: float
    total_cost: float
    capacity_clipped_notional: float


@dataclass(frozen=True)
class V22NegativeControl:
    top_k: int
    trial_id: str
    local_trial_number: int
    cumulative_trial_number: int
    annualized_net_sharpe: float | None
    net_total_return: float
    passed: bool


@dataclass(frozen=True)
class V22PortfolioBreadthReport:
    method_version: str
    experiment_id: str
    snapshot_id: str
    source_snapshot_sha256: str
    prior_evidence_sha256: str
    target_schema_id: str
    target_fingerprint: str
    research_window: tuple[str, str]
    scores: tuple[V22BreadthScore, ...]
    selected_top_k: int
    negative_control: V22NegativeControl
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
            raise ValueError("V2.2 report language must be en or zh")
        zh = language == "zh"
        selected = next(item for item in self.scores if item.top_k == self.selected_top_k)
        lines = [
            "# V2.2 组合宽度研究结果" if zh else "# V2.2 Portfolio Breadth Research Result",
            "",
            f"- {'结论' if zh else 'Decision'}: **{self.decision}**",
            f"- {'固定因子' if zh else 'Frozen factor'}: `{self.target_schema_id}`",
            f"- {'选择宽度' if zh else 'Selected breadth'}: Top-{self.selected_top_k}",
            f"- {'累计试验' if zh else 'Cumulative trials'}: {self.cumulative_trial_count}",
            f"- DSR: {self.deflated_sharpe.probability:.4%}",
            f"- {'选择后净收益' if zh else 'Selected net return'}: {selected.net_total_return:.2%}",
            f"- {'选择后年化净 Sharpe' if zh else 'Selected annualized net Sharpe'}: {selected.annualized_net_sharpe if selected.annualized_net_sharpe is not None else 'N/A'}",
            f"- {'选择后最大回撤' if zh else 'Selected max drawdown'}: {selected.max_drawdown:.2%}",
            "",
            "| Top-K | Net return | Net Sharpe | Max drawdown | Turnover | Cost | Capacity clipped |",
            "|---:|---:|---:|---:|---:|---:|---:|",
        ]
        lines.extend(
            f"| {item.top_k} | {item.net_total_return:.2%} | "
            f"{'N/A' if item.annualized_net_sharpe is None else f'{item.annualized_net_sharpe:.4f}'} | "
            f"{item.max_drawdown:.2%} | {item.total_turnover:.4f} | {item.total_cost:,.2f} | {item.capacity_clipped_notional:,.2f} |"
            for item in self.scores
        )
        lines.extend(["", "## 门禁" if zh else "## Gates", ""])
        lines.extend(
            f"- {'通过' if passed and zh else 'PASS' if passed else '失败' if zh else 'FAIL'} `{name}`: {detail}"
            for name, passed, detail in self.checks
        )
        lines.extend([
            "",
            "> 仅使用已消耗的 2022–2024 研究数据；2025/2026 未打开。" if zh else "> Uses consumed 2022–2024 research data only; 2025/2026 remained sealed.",
            "",
        ])
        return "\n".join(lines)


@dataclass(frozen=True)
class V22PortfolioBreadthArtifacts:
    json_path: Path
    markdown_en_path: Path
    markdown_zh_path: Path
    replay_manifest_path: Path


@dataclass(frozen=True)
class V22ReplayVerification:
    passed: bool
    checked_artifacts: int
    mismatches: tuple[str, ...]


def select_v22_breadth(scores: tuple[V22BreadthScore, ...]) -> V22BreadthScore:
    if tuple(sorted(item.top_k for item in scores)) != (5, 10, 15, 20):
        raise ValueError("V2.2 selection requires exactly one frozen breadth score")
    return max(scores, key=lambda item: (item.raw_net_sharpe, -item.top_k))


def cumulative_v22_trial_count(
    config: V22PortfolioBreadthConfig, new_trial_count: int
) -> int:
    if new_trial_count != len(config.top_ks) + 1:
        raise ValueError("V2.2 requires four breadth trials and one negative control")
    return config.prior_trial_count + new_trial_count


def load_v22_portfolio_breadth_config(source: str | Path) -> V22PortfolioBreadthConfig:
    path = Path(source).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.pop("config_version", None) != V22_CONFIG_VERSION:
        raise ValueError(f"V2.2 config_version must be {V22_CONFIG_VERSION}")
    for key in ("prior_execution_raw_sharpes", "top_ks"):
        if isinstance(payload.get(key), list):
            payload[key] = tuple(payload[key])
    try:
        config = V22PortfolioBreadthConfig(**payload)
    except TypeError as exc:
        raise ValueError("V2.2 config fields are invalid") from exc
    config.validate()
    return config


def _execution_memberships(
    memberships: dict[str, tuple[str, ...]], execution_dates: list[str]
) -> dict[str, tuple[str, ...]]:
    ordered = sorted(memberships)
    result: dict[str, tuple[str, ...]] = {}
    offset = 0
    latest: tuple[str, ...] = ()
    for execution_day in sorted(execution_dates):
        while offset < len(ordered) and ordered[offset] < execution_day:
            latest = memberships[ordered[offset]]
            offset += 1
        result[execution_day] = latest
    return result


def _shared_non_overlapping(
    rows: tuple[BaselineObservation, ...], horizon: int, minimum_eligible: int
) -> tuple[BaselineObservation, ...]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        if row.eligible:
            counts[row.execution_at] += 1
    dates = sorted(day for day, count in counts.items() if count >= minimum_eligible)
    selected = set(dates[::horizon])
    if len(selected) < 2:
        raise ValueError("V2.2 has insufficient shared non-overlapping periods")
    return tuple(row for row in rows if row.execution_at in selected)


def _raw_sharpe(report: BaselineReport) -> float:
    values = [item.net_return for item in report.periods]
    dispersion = stdev(values)
    return 0.0 if dispersion == 0 else (sum(values) / len(values)) / dispersion


def _evaluation_rows(rows: tuple[BaselineObservation, ...]) -> tuple[EvaluationObservation, ...]:
    return tuple(
        EvaluationObservation(
            instrument=row.instrument,
            timestamp=row.execution_at,
            factor_value=row.signal,
            forward_return=row.forward_return,
            factor_available_at=row.signal_available_at,
            label_start_at=row.execution_at,
            label_end_at=row.return_end_at,
            horizon="20d",
            subperiod="research",
            regime="unspecified",
        )
        for row in rows
        if row.eligible
    )


def _score(
    report: BaselineReport,
    *,
    top_k: int,
    trial_id: str,
    local_trial_number: int,
    prior_trial_count: int,
) -> V22BreadthScore:
    return V22BreadthScore(
        top_k,
        trial_id,
        local_trial_number,
        prior_trial_count + local_trial_number,
        report.metrics.periods,
        _raw_sharpe(report),
        report.metrics.net_sharpe,
        report.metrics.net_total_return,
        report.metrics.max_drawdown,
        report.metrics.total_turnover,
        report.metrics.total_cost,
        report.metrics.capacity_clipped_notional,
    )


def run_v22_portfolio_breadth(
    paths: LocalPathConfig,
    config_path: str | Path,
    *,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    ingested_at: str,
) -> tuple[V22PortfolioBreadthReport, V22PortfolioBreadthArtifacts]:
    config_path = Path(config_path).expanduser().resolve()
    config = load_v22_portfolio_breadth_config(config_path)
    v21_path = Path(config.v21_config)
    v21_path = v21_path if v21_path.is_absolute() else (config_path.parent / v21_path).resolve()
    v21 = load_v21_real_research_config(v21_path)
    discovery = resolve_discovery_config(v21, v21_path)
    output = Path(output_dir).expanduser().resolve()
    readiness, readiness_artifacts = run_v21_readiness(
        paths, v21, output / "readiness", ingested_at=ingested_at
    )
    if readiness.decision != "READY":
        raise ValueError("V2.2 is blocked by V2.1 readiness")
    if readiness.source_snapshot_sha256 != config.expected_source_snapshot_sha256:
        raise ValueError("V2.2 source snapshot differs from frozen V2.1 evidence")

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
        vendor_version="V2.2 frozen V2.1 signal inputs",
        notes="Research-only 2022-2024; 2025/2026 remain sealed.",
    )
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            name="v2.2_frozen_signal_portfolio_breadth",
            hypothesis="Increasing breadth improves the V2.1 flow-confirmation portfolio.",
            dataset_snapshot_id=snapshot_id,
            code_version=code_version,
            search_space=_canonical(asdict(config)),
        )
    )

    templates = {item.template_id: item for item in v21_mechanism_generation_plan().templates}
    target = templates["flow_confirmation"].render(window=20, horizon="20d")
    anchor_schema = templates["price_momentum"].render(window=5, horizon="20d")
    if target.schema_id != config.target_schema_id or target.fingerprint != config.target_fingerprint:
        raise ValueError("V2.2 target factor no longer matches frozen V2.1 contract")
    execution_dates = sorted(
        {bar.trade_date for bar in daily.bars if discovery.research_start <= bar.trade_date <= discovery.research_end}
    )
    eligibility = _execution_memberships(memberships, execution_dates)
    anchors = build_qmt_factor_observations(
        daily.bars,
        anchor_schema.compile(),
        test_start=discovery.research_start,
        test_end=discovery.research_end,
        horizon_sessions=config.horizon_sessions,
        eligible_by_execution_date=eligibility,
    )
    target_rows = build_multisource_factor_observations(
        daily.bars,
        {"qd_fund_flow": flow.observations},
        target.compile(),
        anchors,
    )
    execution_rows = _shared_non_overlapping(
        target_rows, config.horizon_sessions, max(config.top_ks)
    )
    baseline_config = {
        "direction": target.direction,
        "commission_bps": config.commission_bps,
        "sell_tax_bps": config.sell_tax_bps,
        "slippage_bps": config.slippage_bps,
        "impact_coefficient_bps": config.impact_coefficient_bps,
        "max_participation_rate": config.max_participation_rate,
        "periods_per_year": max(1, 252 // config.horizon_sessions),
        "missing_holding_policy": "stale_zero_return",
    }
    scores: list[V22BreadthScore] = []
    for top_k in config.top_ks:
        trial_id, trial_number = registry.create_trial(
            TrialSpec(
                experiment_id=experiment_id,
                model_name="v2.2_frozen_signal_portfolio_breadth",
                factor_set=target.schema_id,
                hyperparams=_canonical({"top_k": top_k, "frozen_config": asdict(config)}),
                seed=config.seed,
                train_start=discovery.research_start,
                train_end=discovery.research_end,
                validation_start=discovery.validation_start,
                validation_end=discovery.validation_end,
                test_start=discovery.test_start,
                test_end=discovery.test_end,
            )
        )
        report = run_momentum_topk(
            execution_rows,
            BaselineLineage(
                target.schema_id, target.version, snapshot_id, experiment_id, trial_id, code_version
            ),
            BaselineConfig(top_k=top_k, **baseline_config),
            initial_nav=config.initial_nav,
        )
        item = _score(
            report,
            top_k=top_k,
            trial_id=trial_id,
            local_trial_number=trial_number,
            prior_trial_count=config.prior_trial_count,
        )
        registry.record_trial_result(trial_id, _canonical(asdict(item)))
        scores.append(item)

    selected = select_v22_breadth(tuple(scores))
    control = next(item for item in scores if item.top_k == 5)
    control_values = (
        (control.annualized_net_sharpe, config.prior_annualized_net_sharpe),
        (control.net_total_return, config.prior_net_total_return),
        (control.max_drawdown, config.prior_max_drawdown),
    )
    if any(actual is None or not math.isclose(actual, expected, abs_tol=1e-12) for actual, expected in control_values):
        raise ValueError("V2.2 Top-5 control does not exactly replay frozen V2.1 execution")
    negative_trial_id, negative_trial_number = registry.create_trial(
        TrialSpec(
            experiment_id=experiment_id,
            model_name="v2.2_reversed_ranking_negative_control",
            factor_set=target.schema_id,
            hyperparams=_canonical({"top_k": selected.top_k, "direction": -target.direction}),
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
        execution_rows,
        BaselineLineage(
            target.schema_id,
            target.version,
            snapshot_id,
            experiment_id,
            negative_trial_id,
            code_version,
        ),
        BaselineConfig(top_k=selected.top_k, **{**baseline_config, "direction": -target.direction}),
        initial_nav=config.initial_nav,
    )
    negative = V22NegativeControl(
        selected.top_k,
        negative_trial_id,
        negative_trial_number,
        config.prior_trial_count + negative_trial_number,
        negative_report.metrics.net_sharpe,
        negative_report.metrics.net_total_return,
        negative_report.metrics.net_sharpe is not None and negative_report.metrics.net_sharpe <= 0,
    )
    registry.record_trial_result(negative_trial_id, _canonical(asdict(negative)))
    cumulative = cumulative_v22_trial_count(config, registry.global_trial_count())
    dsr = deflated_sharpe_ratio(
        observed_sharpe=selected.raw_net_sharpe,
        trial_sharpes=(*config.prior_execution_raw_sharpes, *(item.raw_net_sharpe for item in scores)),
        recorded_trial_count=cumulative,
        observations=selected.periods,
    )
    evaluation = _evaluation_rows(target_rows)
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
    selected_sharpe = selected.annualized_net_sharpe or float("-inf")
    checks = (
        ("CONTROL_REPLAY", True, "Top-5 exactly reproduces V2.1"),
        ("BREADTH_CHANGED", selected.top_k != 5, f"selected Top-{selected.top_k}"),
        (
            "SHARPE_IMPROVEMENT",
            selected_sharpe >= config.prior_annualized_net_sharpe + config.minimum_sharpe_improvement,
            f"{selected_sharpe:.6f} vs required {config.prior_annualized_net_sharpe + config.minimum_sharpe_improvement:.6f}",
        ),
        ("MAX_DRAWDOWN", selected.max_drawdown >= -config.maximum_drawdown, f"{selected.max_drawdown:.2%}"),
        ("POSITIVE_NET_RETURN", selected.net_total_return > 0, f"{selected.net_total_return:.2%}"),
        ("NO_CAPACITY_CLIP", selected.capacity_clipped_notional == 0, f"{selected.capacity_clipped_notional:.2f}"),
        ("NEGATIVE_CONTROL", negative.passed, f"Sharpe={negative.annualized_net_sharpe}"),
        ("SIGNAL_PLACEBO", signal_placebo.empirical_p_value <= config.max_placebo_p_value, f"p={signal_placebo.empirical_p_value}"),
        ("RETURN_PLACEBO", return_placebo.empirical_p_value <= config.max_placebo_p_value, f"p={return_placebo.empirical_p_value}"),
        ("PBO", config.prior_pbo <= config.maximum_pbo, f"PBO={config.prior_pbo}"),
        ("DSR", dsr.probability >= config.min_dsr_probability, f"p={dsr.probability}"),
        ("SEALED_WINDOWS", True, "2025/2026 not loaded"),
    )
    improvement_passed = all(item[1] for item in checks[:7])
    alpha_passed = improvement_passed and all(item[1] for item in checks[7:])
    decision = (
        "PASS_ALPHA_COURT"
        if alpha_passed
        else "PROMOTE_RESEARCH_ONLY"
        if improvement_passed
        else "REJECT_NO_IMPROVEMENT"
    )
    report = V22PortfolioBreadthReport(
        V22_METHOD_VERSION,
        experiment_id,
        snapshot_id,
        readiness.source_snapshot_sha256,
        config.prior_evidence_sha256,
        target.schema_id,
        target.fingerprint,
        (discovery.research_start, discovery.research_end),
        tuple(scores),
        selected.top_k,
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
    json_path = output / "v2.2-portfolio-breadth.json"
    en_path = output / "v2.2-portfolio-breadth.en.md"
    zh_path = output / "v2.2-portfolio-breadth.zh.md"
    json_path.write_text(report.to_json() + "\n", encoding="utf-8", newline="\n")
    en_path.write_text(report.to_markdown("en"), encoding="utf-8", newline="\n")
    zh_path.write_text(report.to_markdown("zh"), encoding="utf-8", newline="\n")
    artifacts = {"json": json_path, "markdown_en": en_path, "markdown_zh": zh_path}
    replay_payload = {
        "replay_version": V22_REPLAY_VERSION,
        "method_version": report.method_version,
        "source_snapshot_sha256": report.source_snapshot_sha256,
        "prior_evidence_sha256": report.prior_evidence_sha256,
        "cumulative_trial_count": report.cumulative_trial_count,
        "validation_window_opened": False,
        "test_window_opened": False,
        "artifacts": {name: _sha_file(path) for name, path in sorted(artifacts.items())},
    }
    replay_path = output / "v2.2-replay-manifest.json"
    replay_path.write_text(
        json.dumps(replay_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return report, V22PortfolioBreadthArtifacts(json_path, en_path, zh_path, replay_path)


def verify_v22_portfolio_breadth_replay(source: str | Path) -> V22ReplayVerification:
    path = Path(source).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("replay_version") != V22_REPLAY_VERSION:
        raise ValueError("unsupported V2.2 replay manifest")
    if payload.get("validation_window_opened") or payload.get("test_window_opened"):
        raise ValueError("V2.2 replay reports sealed-window access")
    if payload.get("cumulative_trial_count") != 42:
        raise ValueError("V2.2 replay cumulative trial count is not 42")
    mapping = {
        "json": path.parent / "v2.2-portfolio-breadth.json",
        "markdown_en": path.parent / "v2.2-portfolio-breadth.en.md",
        "markdown_zh": path.parent / "v2.2-portfolio-breadth.zh.md",
    }
    expected = payload.get("artifacts", {})
    mismatches = tuple(
        name
        for name, artifact in mapping.items()
        if not artifact.is_file() or expected.get(name) != _sha_file(artifact)
    )
    return V22ReplayVerification(not mismatches, len(mapping), mismatches)
