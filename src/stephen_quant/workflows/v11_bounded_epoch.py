from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path
from statistics import mean

from stephen_quant.cross_validation import (
    SampleInterval,
    SplitLineage,
    audit_manifest,
    generate_cpcv_manifest,
)
from stephen_quant.discovery.portfolio_native import (
    PortfolioNativeReport,
    PortfolioPolicy,
    evaluate_portfolio_native,
)
from stephen_quant.discovery.v10_generator import FIELDS, V10Candidate, V10Field
from stephen_quant.falsification import (
    deflated_sharpe_ratio,
    probability_of_fold_selection_overfitting,
)
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest

from .v10_empirical import _cross_source_panel, _observations, _regime_attribution
from .v11_research_reset import (
    RAW_GLOBAL_TRIALS_AT_FREEZE,
    NullPlacebo,
    PboIdentifiability,
    UniverseRobustness,
    _sha,
    assess_pbo_identifiability,
    null_placebo,
    universe_robustness,
)

V11_EPOCH_VERSION = "v11.0-one-shot-mechanism-horizon-1.0.0"


@dataclass(frozen=True)
class V11EpochCandidate:
    candidate_id: str
    mechanism: str
    primary_horizon: int
    expression: str
    operator: str
    fields: tuple[V10Field, ...]
    direction: int
    negative_control: bool

    def as_v10_candidate(self) -> V10Candidate:
        return V10Candidate(
            self.candidate_id,
            self.operator,
            self.fields,
            self.direction,
            self.mechanism,
            self.expression,
            "T+1_OPEN",
        )


@dataclass(frozen=True)
class SignalPortfolioBridge:
    periods: int
    non_overlapping_effective_samples: int
    average_top_k_breadth: float
    frictionless_excess_return: float
    standard_cost_excess_return: float
    double_cost_excess_return: float
    total_turnover: float
    capacity_cny: float
    year_returns: tuple[tuple[str, float], ...]
    regime_returns: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class V11EpochEvidence:
    candidate: V11EpochCandidate
    trial_id: str
    trial_number: int
    portfolio: PortfolioNativeReport
    bridge: SignalPortfolioBridge
    universe_robustness: UniverseRobustness
    signal_null: NullPlacebo
    return_null: NullPlacebo
    universe_construction_null: NullPlacebo
    dsr_probability: float
    pbo_probability: float | None
    pbo_identifiability: PboIdentifiability
    failed_gates: tuple[str, ...]


@dataclass(frozen=True)
class V11EpochReport:
    method_version: str
    experiment_id: str
    decision: str
    frozen_budget: int
    inferential_trials_added: int
    raw_global_trials_after: int
    selected_candidate_ids: tuple[str, ...]
    candidates: tuple[V11EpochEvidence, ...]
    unauthorized_sealed_label_reads: int
    forced_stop: bool
    report_sha256: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True)

    def to_markdown(self, language: str) -> str:
        zh = language == "zh"
        title = "# V11.0 一次性机制—期限研究" if zh else "# V11.0 One-shot Mechanism-Horizon Epoch"
        lines = [
            title,
            "",
            f"**{'结论' if zh else 'Decision'}: `{self.decision}`**",
            "",
            f"- {'真实候选 Trial' if zh else 'Inferential candidate trials'}: {self.inferential_trials_added}",
            f"- {'累计原始 Trial' if zh else 'Raw global trials'}: {self.raw_global_trials_after}",
            f"- {'晋级候选' if zh else 'Eligible candidates'}: {len(self.selected_candidate_ids)}",
            f"- {'强制停止' if zh else 'Forced stop'}: {str(self.forced_stop).lower()}",
            "",
            "| Candidate | Horizon | Return | Sharpe | Double cost | DSR | PBO | Result |",
            "|---|---:|---:|---:|---:|---:|---:|---|",
        ]
        for item in self.candidates:
            pbo = "N/I" if item.pbo_probability is None else f"{item.pbo_probability:.3f}"
            lines.append(
                f"| `{item.candidate.expression}` | {item.candidate.primary_horizon} | "
                f"{item.portfolio.net_excess_total_return:.2%} | "
                f"{item.portfolio.annualized_net_excess_sharpe:.3f} | "
                f"{item.portfolio.double_cost_total_return:.2%} | "
                f"{item.dsr_probability:.3f} | {pbo} | "
                f"{', '.join(item.failed_gates) or 'PASS'} |"
            )
        lines.extend(
            [
                "",
                "> 2022–2024 are development-only; 2025–2026 labels were not read."
                if not zh
                else "> 2022–2024 仅为开发数据；未读取 2025–2026 收益标签。",
                "",
            ]
        )
        return "\n".join(lines)


def _identity(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _field(name: str) -> V10Field:
    return next(item for item in FIELDS if item.name == name)


def _expression(operator: str, fields: tuple[V10Field, ...], direction: int) -> str:
    names = [item.name for item in fields]
    base = (
        f"rank({names[0]})"
        if operator == "rank"
        else f"rank({names[0]})-rank({names[1]})"
        if operator == "divergence"
        else "*".join(f"(2*rank({name})-1)" for name in names)
        if operator == "centered_interaction"
        else "*".join(f"rank({name})" for name in names)
    )
    return base if direction > 0 else f"-({base})"


def _candidate(
    mechanism: str,
    horizon: int,
    operator: str,
    names: tuple[str, ...],
    direction: int,
    *,
    negative_control: bool = False,
) -> V11EpochCandidate:
    fields = tuple(_field(name) for name in names)
    payload = {
        "version": V11_EPOCH_VERSION,
        "mechanism": mechanism,
        "horizon": horizon,
        "operator": operator,
        "fields": names,
        "direction": direction,
        "negative_control": negative_control,
    }
    return V11EpochCandidate(
        _identity(payload),
        mechanism,
        horizon,
        _expression(operator, fields, direction),
        operator,
        fields,
        direction,
        negative_control,
    )


def frozen_epoch_candidates() -> tuple[V11EpochCandidate, ...]:
    result = (
        _candidate("auction_open_absorption", 3, "rank", ("auction_return",), -1),
        _candidate("auction_open_absorption", 3, "rank", ("auction_amount_ratio",), 1),
        _candidate(
            "auction_open_absorption",
            3,
            "divergence",
            ("auction_return", "intraday_return"),
            -1,
            negative_control=True,
        ),
        _candidate("intraday_closing_structure", 5, "rank", ("closing_volume_share",), 1),
        _candidate("intraday_closing_structure", 5, "rank", ("vwap_deviation",), -1),
        _candidate(
            "intraday_closing_structure",
            5,
            "divergence",
            ("late_30_return", "intraday_return"),
            -1,
            negative_control=True,
        ),
        _candidate(
            "fund_flow_price_mismatch",
            10,
            "divergence",
            ("net_inflow_ratio", "ret_20"),
            1,
        ),
        _candidate(
            "fund_flow_price_mismatch",
            10,
            "divergence",
            ("main_inflow_ratio", "ret_20"),
            1,
        ),
        _candidate(
            "fund_flow_price_mismatch",
            10,
            "rank",
            ("net_inflow_ratio",),
            1,
            negative_control=True,
        ),
        _candidate(
            "chip_dynamic_crowding",
            20,
            "divergence",
            ("profit_ratio", "concentration"),
            -1,
        ),
        _candidate(
            "chip_dynamic_crowding",
            20,
            "centered_interaction",
            ("concentration", "volatility_20"),
            -1,
        ),
        _candidate(
            "chip_dynamic_crowding",
            20,
            "rank",
            ("profit_ratio",),
            1,
            negative_control=True,
        ),
    )
    if len(result) != 12 or len({item.candidate_id for item in result}) != 12:
        raise RuntimeError("V11 epoch must contain exactly 12 unique frozen candidates")
    return result


def signal_portfolio_bridge(report: PortfolioNativeReport) -> SignalPortfolioBridge:
    return SignalPortfolioBridge(
        len(report.periods),
        len(report.periods),
        mean(len(item.holdings) for item in report.periods),
        math.prod(1.0 + item.gross_excess_return for item in report.periods) - 1.0,
        report.net_excess_total_return,
        report.double_cost_total_return,
        report.total_turnover,
        report.capacity_cny,
        tuple((item.year, item.net_excess_return) for item in report.year_attribution),
        tuple(
            (item.regime, item.net_excess_total_return)
            for item in _regime_attribution(report)
        ),
    )


def _family_pbo(
    mechanism: str,
    items: tuple[V11EpochCandidate, ...],
    portfolios: dict[str, PortfolioNativeReport],
    rows: tuple[dict[str, object], ...],
    feature_snapshot_id: str,
    experiment_id: str,
    code_version: str,
    holding_sessions: int,
) -> tuple[PboIdentifiability, float | None]:
    dates = sorted({period.date for item in items for period in portfolios[item.candidate_id].periods})
    timing = {
        str(row["execution_date"]): (str(row["signal_date"]), str(row["exit_date"]))
        for row in rows
        if str(row["execution_date"]) in set(dates)
    }
    shared = tuple(day for day in dates if day in timing)
    samples = tuple(
        SampleInterval(
            day,
            "CROSS_SECTION",
            f"{timing[day][0]}T18:00:00+08:00",
            f"{day}T09:30:00+08:00",
            f"{timing[day][1]}T09:30:00+08:00",
        )
        for day in shared
    )
    manifest = generate_cpcv_manifest(
        samples,
        SplitLineage(feature_snapshot_id, experiment_id, items[0].candidate_id, code_version),
        n_groups=6,
        n_test_groups=3,
        embargo=timedelta(days=max(5, holding_sessions * 2)),
    )
    findings = audit_manifest(manifest, samples)
    train_scores: dict[str, dict[str, float]] = {}
    test_scores: dict[str, dict[str, float]] = {}
    for item in items:
        values = {period.date: period.net_excess_return for period in portfolios[item.candidate_id].periods}
        train_scores[item.candidate_id] = {
            fold.fold_id: mean(values[day] for day in fold.train_ids if day in values)
            for fold in manifest.folds
        }
        test_scores[item.candidate_id] = {
            fold.fold_id: mean(values[day] for day in fold.test_ids if day in values)
            for fold in manifest.folds
        }
    identifiable = assess_pbo_identifiability(train_scores, test_scores)
    if identifiable.status != "IDENTIFIABLE":
        return identifiable, None
    result = probability_of_fold_selection_overfitting(
        manifest, train_scores, test_scores, findings
    )
    return identifiable, result.probability


def _failed_gates(
    candidate: V11EpochCandidate,
    report: PortfolioNativeReport,
    robustness: UniverseRobustness,
    signal_null: NullPlacebo,
    return_null: NullPlacebo,
    construction_null: NullPlacebo,
    dsr: float,
    pbo_identifiability: PboIdentifiability,
    pbo: float | None,
) -> tuple[str, ...]:
    failed = []
    if candidate.negative_control:
        failed.append("NEGATIVE_CONTROL_NOT_ELIGIBLE")
    if report.net_excess_total_return <= 0:
        failed.append("DEVELOPMENT_RETURN")
    if report.double_cost_total_return <= 0:
        failed.append("DOUBLE_COST")
    if not report.capacity_passed:
        failed.append("CAPACITY")
    if any(item.net_excess_return <= 0 for item in report.year_attribution):
        failed.append("YEAR_STABILITY")
    if any(item.net_excess_total_return <= 0 for item in _regime_attribution(report)):
        failed.append("REGIME_STABILITY")
    if robustness.q25_return <= 0:
        failed.append("UNIVERSE_ROBUSTNESS")
    for name, placebo in (
        ("SIGNAL_NULL", signal_null),
        ("RETURN_NULL", return_null),
        ("UNIVERSE_CONSTRUCTION_NULL", construction_null),
    ):
        if placebo.status != "IDENTIFIABLE" or placebo.p_value is None:
            failed.append(f"{name}_NOT_IDENTIFIABLE")
        elif placebo.p_value > 0.05:
            failed.append(name)
    if dsr < 0.95:
        failed.append("DSR")
    if pbo_identifiability.status != "IDENTIFIABLE" or pbo is None:
        failed.append("PBO_NOT_IDENTIFIABLE")
    elif pbo > 0.05:
        failed.append("PBO")
    return tuple(failed)


def run_v11_bounded_epoch(
    warehouse_root: str | Path,
    *,
    feature_snapshot_id: str,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    contract_decision: str,
) -> V11EpochReport:
    if contract_decision != "READY_FOR_BOUNDED_EPOCH":
        raise ValueError("V11 bounded epoch requires a passing machine Gate A")
    candidates = frozen_epoch_candidates()
    root = Path(warehouse_root).resolve()
    from stephen_quant.qmt.multisource_warehouse import latest_multisource_snapshot

    multisource = latest_multisource_snapshot(root)
    snapshot = registry.register_snapshot(
        build_composite_snapshot_manifest(
            {"minute_features": feature_snapshot_id, "multisource": multisource}
        ),
        vendor_version=V11_EPOCH_VERSION,
    )
    experiment = registry.create_experiment_deterministic(
        ExperimentSpec(
            "v11_one_shot_mechanism_horizon",
            "Twelve preregistered development-only mechanism-horizon candidates",
            snapshot,
            code_version,
            json.dumps([asdict(item) for item in candidates], sort_keys=True),
        ),
        f"{V11_EPOCH_VERSION}|{snapshot}|{code_version}",
    )
    trials = {}
    for item in candidates:
        trials[item.candidate_id] = registry.create_trial_deterministic(
            TrialSpec(
                experiment,
                "v11_mechanism_horizon",
                item.candidate_id,
                json.dumps(asdict(item), sort_keys=True),
                11,
                "2022-01-01",
                "2024-12-31",
                "DEVELOPMENT_ONLY",
                "DEVELOPMENT_ONLY",
                "SEALED",
                "SEALED",
            ),
            f"{V11_EPOCH_VERSION}|{experiment}|{item.candidate_id}",
        )
    rows_by_horizon = {
        horizon: _cross_source_panel(
            root,
            "2022-01-01",
            "2024-12-31",
            holding_sessions=horizon,
        )[0]
        for horizon in (3, 5, 10, 20)
    }
    policy_by_horizon = {
        horizon: PortfolioPolicy(
            initial_nav_cny=3_000_000,
            top_k=40,
            rank_buffer=10,
            round_trip_cost_bps=41.0,
            periods_per_year=max(1, 252 // horizon),
        )
        for horizon in rows_by_horizon
    }
    portfolios = {}
    observations = {}
    for item in candidates:
        obs = _observations(rows_by_horizon[item.primary_horizon], item.as_v10_candidate())
        observations[item.candidate_id] = obs
        portfolios[item.candidate_id] = evaluate_portfolio_native(
            obs, policy=policy_by_horizon[item.primary_horizon]
        )
    family_pbo = {}
    for mechanism in sorted({item.mechanism for item in candidates}):
        family = tuple(item for item in candidates if item.mechanism == mechanism)
        horizon = family[0].primary_horizon
        family_pbo[mechanism] = _family_pbo(
            mechanism,
            family,
            portfolios,
            rows_by_horizon[horizon],
            feature_snapshot_id,
            experiment,
            code_version,
            horizon,
        )
    sharpes = [
        portfolios[item.candidate_id].annualized_net_excess_sharpe
        / math.sqrt(portfolios[item.candidate_id].policy.periods_per_year)
        for item in candidates
    ]
    evidence = []
    for item in candidates:
        report = portfolios[item.candidate_id]
        obs = observations[item.candidate_id]
        policy = policy_by_horizon[item.primary_horizon]
        robustness = universe_robustness(obs, policy, samples=49)
        signal_null = null_placebo(obs, policy, mode="stratified_signal", samples=49)
        return_null = null_placebo(obs, policy, mode="stratified_return", samples=49)
        construction_null = null_placebo(
            obs, policy, mode="universe_construction", samples=49
        )
        dsr = deflated_sharpe_ratio(
            observed_sharpe=report.annualized_net_excess_sharpe
            / math.sqrt(report.policy.periods_per_year),
            trial_sharpes=sharpes,
            recorded_trial_count=RAW_GLOBAL_TRIALS_AT_FREEZE + len(candidates),
            observations=len(report.periods),
        ).probability
        identifiable, pbo = family_pbo[item.mechanism]
        failed = _failed_gates(
            item,
            report,
            robustness,
            signal_null,
            return_null,
            construction_null,
            dsr,
            identifiable,
            pbo,
        )
        trial_id, trial_number = trials[item.candidate_id]
        item_evidence = V11EpochEvidence(
            item,
            trial_id,
            trial_number,
            report,
            signal_portfolio_bridge(report),
            robustness,
            signal_null,
            return_null,
            construction_null,
            dsr,
            pbo,
            identifiable,
            failed,
        )
        evidence.append(item_evidence)
        registry.record_trial_result(trial_id, json.dumps(asdict(item_evidence), sort_keys=True))
    eligible = tuple(
        item.candidate.candidate_id
        for item in evidence
        if not item.failed_gates
    )
    decision = (
        "ELIGIBLE_FOR_INDEPENDENT_FORWARD_EVIDENCE"
        if eligible
        else "NO_CANDIDATE_FOR_FORWARD_OBSERVATION"
    )
    payload = {
        "method_version": V11_EPOCH_VERSION,
        "experiment_id": experiment,
        "decision": decision,
        "frozen_budget": 12,
        "inferential_trials_added": 12,
        "raw_global_trials_after": RAW_GLOBAL_TRIALS_AT_FREEZE + 12,
        "selected_candidate_ids": eligible,
        "candidates": [asdict(item) for item in evidence],
        "unauthorized_sealed_label_reads": 0,
        "forced_stop": True,
    }
    report = V11EpochReport(
        V11_EPOCH_VERSION,
        experiment,
        decision,
        12,
        12,
        RAW_GLOBAL_TRIALS_AT_FREEZE + 12,
        eligible,
        tuple(evidence),
        0,
        True,
        _sha(payload),
    )
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "V11_BOUNDED_EPOCH_RESULT.json").write_text(report.to_json() + "\n", encoding="utf-8")
    (output / "V11_BOUNDED_EPOCH_RESULT.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (output / "V11_BOUNDED_EPOCH_RESULT.en.md").write_text(report.to_markdown("en"), encoding="utf-8")
    return report
