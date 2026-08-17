from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from itertools import pairwise
from pathlib import Path
from statistics import median

from stephen_quant.baseline import (
    BaselineConfig,
    BaselineLineage,
    BaselineObservation,
    run_momentum_topk,
)
from stephen_quant.evaluation import ols_residuals, spearman_correlation
from stephen_quant.falsification import deflated_sharpe_ratio, run_placebo
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest
from stephen_quant.path_config import LocalPathConfig
from stephen_quant.qmt import load_qd_daily_directory

from .research_epoch import (
    evaluation_rows,
    raw_sharpe,
    sample_return_moments,
    shared_non_overlapping,
)
from .v23_style_residualization import build_v23_frozen_panel
from .v27_risk_controls import (
    NormalizedRiskExposure,
    PriceRiskConfig,
    PriceRiskObservation,
    build_causal_price_exposures,
    fit_fold_local_risk_state,
    transform_heldout_risk_exposures,
    transform_training_risk_exposures,
)

PIT_LITE_CONFIG_VERSION = "2.9.0"
PIT_LITE_METHOD_VERSION = "pit-lite-walk-forward-statistical-risk-1.0.0"
PIT_LITE_REPLAY_VERSION = "pit-lite-walk-forward-statistical-risk-replay-1.0.0"
VARIANTS = ("RAW", "PRICE_STYLE", "PCA_NEUTRAL", "STATISTICAL_CLUSTER_NEUTRAL")


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class PitLiteConfig:
    config_version: str
    issue_number: int
    v23_config: str
    industry_audit_result_sha256: str
    industry_classification: str
    prior_inferential_trials: int
    candidate_id: str
    candidate_fingerprint: str
    research_start: str
    research_end: str
    train_end_2023: str
    train_end_2024: str
    evaluation_years: tuple[int, ...]
    horizon_sessions: int
    clusters: int
    kmeans_iterations: int
    pca_iterations: int
    minimum_cluster_members: int
    seed: int
    top_k: int
    missing_holding_policy: str
    initial_nav_cny: float
    capacity_nav_cny: float
    commission_bps: float
    sell_tax_bps: float
    slippage_bps: float
    impact_coefficient_bps: float
    max_participation_rate: float
    placebo_repetitions: int
    max_placebo_p_value: float
    minimum_dsr_probability: float
    maximum_drawdown: float
    minimum_annualized_sharpe: float
    inherited_pbo: float
    risk: PriceRiskConfig

    def validate(self) -> None:
        if self.config_version != PIT_LITE_CONFIG_VERSION or self.issue_number != 98:
            raise ValueError("PIT-Lite config must bind Issue #98")
        if self.industry_classification != "B_CURRENT_LABEL_BACKFILL":
            raise ValueError("real PIT-Lite run requires the audited B industry classification")
        hashes = (self.industry_audit_result_sha256, self.candidate_fingerprint)
        if any(len(item) != 64 or any(char not in "0123456789abcdef" for char in item) for item in hashes):
            raise ValueError("PIT-Lite evidence hashes must be lowercase SHA-256")
        if self.prior_inferential_trials != 51 or self.evaluation_years != (2023, 2024):
            raise ValueError("PIT-Lite trial lineage or walk-forward years changed")
        if self.candidate_id != "flow_confirmation_20_20d" or self.horizon_sessions != 20:
            raise ValueError("PIT-Lite candidate formula/horizon changed")
        if self.research_start != "2022-01-04" or self.research_end != "2024-12-31":
            raise ValueError("PIT-Lite may use only the frozen 2022-2024 research window")
        if self.train_end_2023 != "2022-12-31" or self.train_end_2024 != "2023-12-31":
            raise ValueError("PIT-Lite walk-forward training cutoffs changed")
        if self.clusters < 2 or min(self.kmeans_iterations, self.pca_iterations) < 1:
            raise ValueError("PIT-Lite statistical risk settings are invalid")
        if (
            self.minimum_cluster_members < 2
            or self.top_k != 5
            or self.missing_holding_policy != "stale_zero_return"
        ):
            raise ValueError("PIT-Lite portfolio/cluster settings changed")
        if self.initial_nav_cny != 3_000_000 or self.capacity_nav_cny != 20_000_000:
            raise ValueError("PIT-Lite capital levels must remain CNY 3m and CNY 20m")
        if self.placebo_repetitions < 1 or not 0 < self.max_placebo_p_value < 1:
            raise ValueError("PIT-Lite placebo contract is invalid")
        if not 0 < self.minimum_dsr_probability < 1 or not 0 < self.maximum_drawdown < 1:
            raise ValueError("PIT-Lite statistical thresholds are invalid")
        self.risk.validate()

    @property
    def sha256(self) -> str:
        self.validate()
        return _sha(asdict(self))


@dataclass(frozen=True)
class PcState:
    means: tuple[float, ...]
    loading: tuple[float, ...]
    fit_rows: int
    state_sha256: str


@dataclass(frozen=True)
class ClusterState:
    centroids: tuple[tuple[float, ...], ...]
    fit_rows: int
    iterations: int
    state_sha256: str


@dataclass(frozen=True)
class VariantResult:
    name: str
    observations: int
    periods: int
    mean_rank_ic: float
    yearly_rank_ic: dict[str, float]
    net_total_return_3m: float
    annualized_net_sharpe_3m: float | None
    max_drawdown_3m: float
    total_cost_3m: float
    net_total_return_20m: float
    annualized_net_sharpe_20m: float | None
    max_drawdown_20m: float
    capacity_clipped_notional_20m: float
    signal_placebo_p_value: float
    return_placebo_p_value: float
    dsr_probability: float


@dataclass(frozen=True)
class PitLiteReport:
    method_version: str
    decision: str
    candidate_status: str
    experiment_id: str
    trial_id: str
    local_trial_number: int
    cumulative_inferential_trials: int
    config_sha256: str
    source_snapshot_sha256: str
    industry_audit_result_sha256: str
    industry_classification: str
    industry_proxy_used_for_signal: bool
    evaluation_years: tuple[int, ...]
    walk_forward_states: dict[str, dict[str, str]]
    variants: tuple[VariantResult, ...]
    inherited_pbo: float
    inherited_pbo_scope: str
    inferential_trial_delta: int
    validation_2025_accesses: int
    final_2026_accesses: int
    checks: tuple[tuple[str, bool, str], ...]
    result_sha256: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    def to_markdown(self, *, language: str) -> str:
        zh = language == "zh"
        title = "PIT-Lite 因子研究结果" if zh else "PIT-Lite Factor Research Result"
        lines = [
            f"# {title}",
            "",
            f"- {'结论' if zh else 'Decision'}: **{self.decision}**",
            f"- {'候选状态' if zh else 'Candidate status'}: `{self.candidate_status}`",
            f"- {'冻结候选' if zh else 'Frozen candidate'}: `flow_confirmation_20_20d`",
            f"- {'累计推断性试验' if zh else 'Cumulative inferential trials'}: {self.cumulative_inferential_trials}",
            f"- {'行业字段' if zh else 'Industry field'}: `{self.industry_classification}` / diagnostics only",
            "",
            "| Variant | RankIC | 3m return | 3m Sharpe | 3m drawdown | 20m return | DSR |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for item in self.variants:
            sharpe = "N/A" if item.annualized_net_sharpe_3m is None else f"{item.annualized_net_sharpe_3m:.4f}"
            lines.append(
                f"| {item.name} | {item.mean_rank_ic:.4f} | {item.net_total_return_3m:.2%} | "
                f"{sharpe} | {item.max_drawdown_3m:.2%} | {item.net_total_return_20m:.2%} | "
                f"{item.dsr_probability:.2%} |"
            )
        lines.extend(["", "## " + ("门禁" if zh else "Gates"), ""])
        for name, passed, detail in self.checks:
            marker = "通过" if passed and zh else "失败" if zh else "PASS" if passed else "FAIL"
            lines.append(f"- {marker} `{name}`: {detail}")
        lines.extend(
            [
                "",
                (
                    "> 本轮只使用 2022–2024；2025/2026 未被该研究 operation 读取。"
                    if zh
                    else "> This research operation used 2022–2024 only; it did not read 2025/2026."
                ),
                "",
            ]
        )
        return "\n".join(lines)


@dataclass(frozen=True)
class PitLiteArtifacts:
    json_path: Path
    markdown_zh_path: Path
    markdown_en_path: Path
    replay_path: Path


def load_pit_lite_config(source: str | Path) -> PitLiteConfig:
    path = Path(source).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("PIT-Lite config must be a JSON object")
    payload["evaluation_years"] = tuple(payload["evaluation_years"])
    payload["risk"] = PriceRiskConfig(**payload["risk"])
    config = PitLiteConfig(**payload)
    config.validate()
    return config


def _market_proxy(bars: tuple[object, ...]) -> dict[str, float]:
    by_instrument: dict[str, list[object]] = defaultdict(list)
    for bar in bars:
        by_instrument[bar.instrument].append(bar)
    returns: dict[str, list[float]] = defaultdict(list)
    for rows in by_instrument.values():
        ordered = sorted(rows, key=lambda item: item.trade_date)
        for left, right in pairwise(ordered):
            if left.close > 0 and right.close > 0:
                returns[right.trade_date].append(right.close / left.close - 1)
    level = 100.0
    result: dict[str, float] = {}
    for day in sorted(returns):
        values = returns[day]
        if len(values) < 10:
            continue
        level *= 1 + median(values)
        if level <= 0 or not math.isfinite(level):
            raise ValueError("causal cross-sectional market proxy became invalid")
        result[day] = level
    return result


def _risk_exposures(bars: tuple[object, ...], config: PriceRiskConfig) -> tuple[object, ...]:
    market = _market_proxy(bars)
    observations = tuple(
        PriceRiskObservation(
            instrument=bar.instrument,
            decision_at=f"{bar.trade_date}T15:01:00+08:00",
            close=bar.close,
            amount=bar.amount,
            market_close=market[bar.trade_date],
        )
        for bar in bars
        if bar.trade_date in market and bar.close > 0 and bar.amount > 0
    )
    return build_causal_price_exposures(observations, config)


def _fit_pc(rows: tuple[NormalizedRiskExposure, ...], iterations: int) -> PcState:
    width = len(rows[0].values)
    means = tuple(sum(row.values[index] for row in rows) / len(rows) for index in range(width))
    covariance = [[0.0 for _ in range(width)] for _ in range(width)]
    for row in rows:
        centered = [row.values[index] - means[index] for index in range(width)]
        for left in range(width):
            for right in range(width):
                covariance[left][right] += centered[left] * centered[right]
    scale = max(len(rows) - 1, 1)
    covariance = [[value / scale for value in row] for row in covariance]
    vector = [float(index + 1) for index in range(width)]
    norm = math.sqrt(sum(value * value for value in vector))
    vector = [value / norm for value in vector]
    for _ in range(iterations):
        updated = [sum(covariance[i][j] * vector[j] for j in range(width)) for i in range(width)]
        norm = math.sqrt(sum(value * value for value in updated))
        if norm <= 1e-15:
            raise ValueError("PCA covariance has no non-zero first component")
        vector = [value / norm for value in updated]
    if next(value for value in vector if abs(value) > 1e-12) < 0:
        vector = [-value for value in vector]
    core = {"means": means, "loading": tuple(vector), "fit_rows": len(rows)}
    return PcState(**core, state_sha256=_sha(core))


def _fit_clusters(
    rows: tuple[NormalizedRiskExposure, ...], clusters: int, iterations: int
) -> ClusterState:
    unique = sorted({tuple(row.values) for row in rows})
    if len(unique) < clusters:
        raise ValueError("not enough distinct risk vectors for statistical clusters")
    centroids = [unique[round(index * (len(unique) - 1) / (clusters - 1))] for index in range(clusters)]
    for _ in range(iterations):
        assigned: list[list[tuple[float, ...]]] = [[] for _ in centroids]
        for row in rows:
            group = min(
                range(len(centroids)),
                key=lambda index: (sum((a - b) ** 2 for a, b in zip(row.values, centroids[index], strict=True)), index),
            )
            assigned[group].append(tuple(row.values))
        next_centroids = []
        for index, members in enumerate(assigned):
            if not members:
                next_centroids.append(centroids[index])
                continue
            next_centroids.append(
                tuple(sum(item[column] for item in members) / len(members) for column in range(len(members[0])))
            )
        centroids = next_centroids
    core = {"centroids": tuple(centroids), "fit_rows": len(rows), "iterations": iterations}
    return ClusterState(**core, state_sha256=_sha(core))


def _pc_score(state: PcState, row: NormalizedRiskExposure) -> float:
    return sum((value - state.means[index]) * state.loading[index] for index, value in enumerate(row.values))


def _cluster(state: ClusterState, row: NormalizedRiskExposure) -> int:
    return min(
        range(len(state.centroids)),
        key=lambda index: (sum((a - b) ** 2 for a, b in zip(row.values, state.centroids[index], strict=True)), index),
    )


def _walk_forward_variants(
    target: tuple[BaselineObservation, ...],
    price: tuple[BaselineObservation, ...],
    exposures: tuple[object, ...],
    config: PitLiteConfig,
    source_snapshot_sha256: str,
) -> tuple[dict[str, tuple[BaselineObservation, ...]], dict[str, dict[str, str]]]:
    target_map = {(row.execution_at, row.instrument): row for row in target}
    price_map = {(row.execution_at, row.instrument): row for row in price}
    if set(target_map) != set(price_map):
        raise ValueError("raw and price-style panels differ")
    variants: dict[str, list[BaselineObservation]] = {name: [] for name in VARIANTS}
    states: dict[str, dict[str, str]] = {}
    for year in config.evaluation_years:
        training_end = config.train_end_2023 if year == 2023 else config.train_end_2024
        state = fit_fold_local_risk_state(
            exposures,
            training_start=config.research_start + "T00:00:00+08:00",
            training_end=training_end + "T23:59:59+08:00",
            source_snapshot_sha256=source_snapshot_sha256,
            config=config.risk,
        )
        training_raw = tuple(
            row
            for row in exposures
            if state.training_start <= row.decision_at <= state.training_end
        )
        heldout_raw = tuple(row for row in exposures if row.decision_at[:4] == str(year))
        training = transform_training_risk_exposures(state, training_raw)
        heldout = transform_heldout_risk_exposures(state, heldout_raw)
        pc = _fit_pc(training, config.pca_iterations)
        clusters = _fit_clusters(training, config.clusters, config.kmeans_iterations)
        states[str(year)] = {
            "risk_state_sha256": state.state_sha256,
            "pca_state_sha256": pc.state_sha256,
            "cluster_state_sha256": clusters.state_sha256,
        }
        heldout_map = {(row.decision_at[:10], row.instrument): row for row in heldout}
        by_date: dict[str, list[tuple[BaselineObservation, BaselineObservation, NormalizedRiskExposure]]] = defaultdict(list)
        for key, row in target_map.items():
            if row.execution_at[:4] != str(year) or not row.eligible:
                continue
            exposure = heldout_map.get((row.signal_at[:10], row.instrument))
            if exposure is not None:
                by_date[row.execution_at].append((row, price_map[key], exposure))
        for day, cross_section in sorted(by_date.items()):
            ordered = sorted(cross_section, key=lambda item: item[0].instrument)
            if len(ordered) < 10:
                continue
            raw_values = [item[0].signal for item in ordered]
            pca_values = ols_residuals(raw_values, [[_pc_score(pc, item[2])] for item in ordered])
            memberships = [_cluster(clusters, item[2]) for item in ordered]
            groups: dict[int, list[float]] = defaultdict(list)
            for membership, value in zip(memberships, raw_values, strict=True):
                groups[membership].append(value)
            overall = sum(raw_values) / len(raw_values)
            group_means = {
                group: sum(values) / len(values) if len(values) >= config.minimum_cluster_members else overall
                for group, values in groups.items()
            }
            for index, (raw, styled, _) in enumerate(ordered):
                variants["RAW"].append(raw)
                variants["PRICE_STYLE"].append(styled)
                variants["PCA_NEUTRAL"].append(replace(raw, signal=pca_values[index]))
                variants["STATISTICAL_CLUSTER_NEUTRAL"].append(
                    replace(raw, signal=raw.signal - group_means[memberships[index]])
                )
    common = set.intersection(
        *({(row.execution_at, row.instrument) for row in rows} for rows in variants.values())
    )
    return (
        {
            name: tuple(row for row in rows if (row.execution_at, row.instrument) in common)
            for name, rows in variants.items()
        },
        states,
    )


def _mean_rank_ic(rows: tuple[BaselineObservation, ...]) -> tuple[float, dict[str, float]]:
    by_date: dict[str, list[BaselineObservation]] = defaultdict(list)
    for row in rows:
        if row.eligible:
            by_date[row.execution_at].append(row)
    daily: dict[str, float] = {}
    for day, items in by_date.items():
        if len(items) >= 3:
            daily[day] = spearman_correlation(
                [item.signal for item in items], [item.forward_return for item in items]
            )
    yearly = {
        str(year): sum(value for day, value in daily.items() if day[:4] == str(year))
        / sum(day[:4] == str(year) for day in daily)
        for year in (2023, 2024)
    }
    return sum(daily.values()) / len(daily), yearly


def _execute(
    rows: tuple[BaselineObservation, ...], lineage: BaselineLineage, config: PitLiteConfig, nav: float
):
    return run_momentum_topk(
        shared_non_overlapping(rows, config.horizon_sessions, config.top_k),
        lineage,
        BaselineConfig(
            top_k=config.top_k,
            commission_bps=config.commission_bps,
            sell_tax_bps=config.sell_tax_bps,
            slippage_bps=config.slippage_bps,
            impact_coefficient_bps=config.impact_coefficient_bps,
            max_participation_rate=config.max_participation_rate,
            missing_holding_policy=config.missing_holding_policy,
        ),
        initial_nav=nav,
    )


def run_pit_lite_research(
    paths: LocalPathConfig,
    config_source: str | Path,
    *,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    ingested_at: str,
) -> tuple[PitLiteReport, PitLiteArtifacts]:
    config_path = Path(config_source).expanduser().resolve()
    config = load_pit_lite_config(config_path)
    config_sha = config.sha256
    v23_path = Path(config.v23_config)
    v23_path = v23_path if v23_path.is_absolute() else (config_path.parent / v23_path).resolve()
    source_manifest = build_composite_snapshot_manifest(
        {
            "frozen_v23_config": _file_sha(v23_path),
            "industry_proxy_audit": config.industry_audit_result_sha256,
            "pit_lite_contract": config_sha,
        }
    )
    snapshot_id = registry.register_snapshot(
        source_manifest,
        vendor_version="QD 2022-2024 PIT-Lite / no mixed-year benchmark",
        notes="Issue #98; 2025/2026 excluded; industry field diagnostics only.",
    )
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            name="issue_98_pit_lite_statistical_risk",
            hypothesis=(
                "The frozen flow-confirmation candidate remains directionally stable across raw, "
                "price-style, PCA and statistical-cluster risk specifications."
            ),
            dataset_snapshot_id=snapshot_id,
            code_version=code_version,
            search_space=config_path.read_text(encoding="utf-8"),
        )
    )
    trial_id, trial_number = registry.create_trial(
        TrialSpec(
            experiment_id=experiment_id,
            model_name="pit_lite_walk_forward_statistical_risk",
            factor_set=config.candidate_id,
            hyperparams=_canonical(asdict(config)),
            seed=config.seed,
            train_start=config.research_start,
            train_end=config.train_end_2024,
            validation_start="2023-01-01",
            validation_end=config.research_end,
            test_start="2026-01-01",
            test_end="2026-12-31",
        )
    )
    try:
        _, panel = build_v23_frozen_panel(
            paths, v23_path, output_dir=Path(output_dir) / "readiness", ingested_at=ingested_at
        )
        if panel.target_schema.schema_id != config.candidate_id or panel.target_schema.fingerprint != config.candidate_fingerprint:
            raise ValueError("loaded candidate differs from the frozen PIT-Lite contract")
        instruments = tuple(sorted({row.instrument for row in panel.target_rows}))
        daily = load_qd_daily_directory(
            paths.choose("qd_daily_dir", None, "qd_daily_dir"),
            start_date="2021-07-01",
            end_date=config.research_end,
            instruments=instruments,
            adjustment="back_ratio",
        )
        exposures = _risk_exposures(daily.bars, config.risk)
        panels, states = _walk_forward_variants(
            panel.target_rows,
            panel.residual_rows,
            exposures,
            config,
            source_manifest.snapshot_sha256,
        )
        reports_3m = {}
        reports_20m = {}
        for name in VARIANTS:
            lineage = BaselineLineage(
                factor_id=f"{config.candidate_id}:{name.lower()}",
                factor_version=PIT_LITE_METHOD_VERSION,
                snapshot_id=snapshot_id,
                experiment_id=experiment_id,
                trial_id=trial_id,
                code_version=code_version,
            )
            reports_3m[name] = _execute(panels[name], lineage, config, config.initial_nav_cny)
            reports_20m[name] = _execute(panels[name], lineage, config, config.capacity_nav_cny)
        # Carry the eight frozen V2.2 execution estimates plus all preregistered risk specifications.
        v23_payload = json.loads(v23_path.read_text(encoding="utf-8"))
        trial_sharpes = [*v23_payload["prior_execution_raw_sharpes"], *(raw_sharpe(reports_3m[name]) for name in VARIANTS)]
        results: list[VariantResult] = []
        for name in VARIANTS:
            rows = panels[name]
            evaluation = evaluation_rows(rows, horizon="20d")
            mean_ic, yearly = _mean_rank_ic(rows)
            signal_placebo = run_placebo(
                evaluation, horizon="20d", direction=1, method="signal_shuffle",
                seed=config.seed, repetitions=config.placebo_repetitions,
            )
            return_placebo = run_placebo(
                evaluation, horizon="20d", direction=1, method="return_permutation",
                seed=config.seed, repetitions=config.placebo_repetitions,
            )
            report_3m = reports_3m[name]
            report_20m = reports_20m[name]
            moments = sample_return_moments([period.net_return for period in report_3m.periods])
            dsr = deflated_sharpe_ratio(
                observed_sharpe=raw_sharpe(report_3m),
                trial_sharpes=trial_sharpes,
                recorded_trial_count=config.prior_inferential_trials + 1,
                observations=len(report_3m.periods),
                skewness=moments.skewness,
                excess_kurtosis=moments.excess_kurtosis,
            )
            results.append(
                VariantResult(
                    name=name,
                    observations=len(rows),
                    periods=len(report_3m.periods),
                    mean_rank_ic=mean_ic,
                    yearly_rank_ic=yearly,
                    net_total_return_3m=report_3m.metrics.net_total_return,
                    annualized_net_sharpe_3m=report_3m.metrics.net_sharpe,
                    max_drawdown_3m=report_3m.metrics.max_drawdown,
                    total_cost_3m=report_3m.metrics.total_cost,
                    net_total_return_20m=report_20m.metrics.net_total_return,
                    annualized_net_sharpe_20m=report_20m.metrics.net_sharpe,
                    max_drawdown_20m=report_20m.metrics.max_drawdown,
                    capacity_clipped_notional_20m=report_20m.metrics.capacity_clipped_notional,
                    signal_placebo_p_value=signal_placebo.empirical_p_value,
                    return_placebo_p_value=return_placebo.empirical_p_value,
                    dsr_probability=dsr.probability,
                )
            )
        checks = (
            ("ALL_VARIANTS_POSITIVE_RANK_IC", all(item.mean_rank_ic > 0 and all(value > 0 for value in item.yearly_rank_ic.values()) for item in results), "raw/price/PCA/cluster must be positive in both walk-forward years"),
            ("ALL_VARIANTS_EXECUTION_SHARPE", all(item.annualized_net_sharpe_3m is not None and item.annualized_net_sharpe_3m >= config.minimum_annualized_sharpe for item in results), f"minimum annualized net Sharpe={config.minimum_annualized_sharpe}"),
            ("ALL_VARIANTS_DRAWDOWN", all(item.max_drawdown_3m >= -config.maximum_drawdown for item in results), f"maximum drawdown={config.maximum_drawdown:.0%}"),
            ("ALL_VARIANTS_PLACEBO", all(item.signal_placebo_p_value <= config.max_placebo_p_value and item.return_placebo_p_value <= config.max_placebo_p_value for item in results), f"maximum p={config.max_placebo_p_value}"),
            ("ALL_VARIANTS_DSR", all(item.dsr_probability >= config.minimum_dsr_probability for item in results), f"minimum DSR={config.minimum_dsr_probability}"),
            ("CAPACITY_20M", all(item.capacity_clipped_notional_20m == 0 for item in results), "no capacity clipping at CNY 20m"),
            ("INDUSTRY_PROXY_NOT_USED", True, "B-grade current-label backfill is diagnostics only"),
            ("SEALED_WINDOWS", True, "workflow selects daily files only through 2024-12-31"),
        )
        passed = all(item[1] for item in checks)
        decision = "PROVISIONAL_INDUSTRY_UNCONTROLLED" if passed else "NO_ROBUST_ALPHA_POPULATION"
        core = {
            "method_version": PIT_LITE_METHOD_VERSION,
            "decision": decision,
            "candidate_status": decision,
            "experiment_id": experiment_id,
            "trial_id": trial_id,
            "local_trial_number": trial_number,
            "cumulative_inferential_trials": config.prior_inferential_trials + 1,
            "config_sha256": config_sha,
            "source_snapshot_sha256": source_manifest.snapshot_sha256,
            "industry_audit_result_sha256": config.industry_audit_result_sha256,
            "industry_classification": config.industry_classification,
            "industry_proxy_used_for_signal": False,
            "evaluation_years": config.evaluation_years,
            "walk_forward_states": states,
            "variants": tuple(results),
            "inherited_pbo": config.inherited_pbo,
            "inherited_pbo_scope": "frozen V2.1 candidate-selection layer only; non-rescuing",
            "inferential_trial_delta": 1,
            "validation_2025_accesses": 0,
            "final_2026_accesses": 0,
            "checks": checks,
        }
        hash_payload = {**core, "variants": [asdict(item) for item in results]}
        report = PitLiteReport(**core, result_sha256=_sha(hash_payload))
        registry.record_trial_result(trial_id, report.to_json())
        output = Path(output_dir).expanduser().resolve()
        output.mkdir(parents=True, exist_ok=True)
        json_path = output / "pit-lite-research.json"
        zh_path = output / "pit-lite-research.zh.md"
        en_path = output / "pit-lite-research.en.md"
        replay_path = output / "pit-lite-replay.json"
        json_path.write_text(report.to_json() + "\n", encoding="utf-8")
        zh_path.write_text(report.to_markdown(language="zh"), encoding="utf-8")
        en_path.write_text(report.to_markdown(language="en"), encoding="utf-8")
        replay = {
            "replay_version": PIT_LITE_REPLAY_VERSION,
            "config_sha256": config_sha,
            "source_snapshot_sha256": source_manifest.snapshot_sha256,
            "result_sha256": report.result_sha256,
            "artifacts": {
                path.name: _file_sha(path) for path in (json_path, zh_path, en_path)
            },
        }
        replay_path.write_text(json.dumps(replay, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        for kind, path in (("pit_lite_json", json_path), ("pit_lite_zh", zh_path), ("pit_lite_en", en_path), ("pit_lite_replay", replay_path)):
            registry.register_artifact(trial_id=trial_id, kind=kind, path=str(path), sha256=_file_sha(path))
        return report, PitLiteArtifacts(json_path, zh_path, en_path, replay_path)
    except Exception as exc:
        registry.record_trial_result(trial_id, json.dumps({"status": "failed_engineering", "error": str(exc)}, ensure_ascii=False, sort_keys=True))
        raise
