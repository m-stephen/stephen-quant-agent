from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
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
    PortfolioObservation,
    PortfolioPolicy,
    evaluate_portfolio_native,
)
from stephen_quant.discovery.v10_generator import V10Candidate, generate_v10_candidates
from stephen_quant.evaluation import average_ranks
from stephen_quant.falsification import (
    deflated_sharpe_ratio,
    probability_of_fold_selection_overfitting,
)
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest
from stephen_quant.qmt.data_warehouse import _duckdb

V10_EMPIRICAL_VERSION = "v10.1-bounded-daily-minute-court-1.1.0"


@dataclass(frozen=True)
class V10CandidateEvidence:
    candidate_id: str
    expression: str
    trial_id: str
    trial_number: int
    portfolio: PortfolioNativeReport


@dataclass(frozen=True)
class V10EmpiricalReport:
    method_version: str
    experiment_id: str
    candidates: tuple[V10CandidateEvidence, ...]
    selected_candidate_id: str
    selected_validation: PortfolioNativeReport
    total_recorded_trials: int
    dsr_probability: float
    pbo_probability: float
    signal_placebo_p_value: float
    return_placebo_p_value: float
    universe_placebo_p_value: float
    cpcv_hygiene_passed: bool
    eligible_predictor_fields: tuple[str, ...]
    rejected_predictor_fields: tuple[str, ...]
    decision: str
    failed_gates: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True)

    def to_markdown(self, language: str) -> str:
        zh = language == "zh"
        winner = next(
            item for item in self.candidates if item.candidate_id == self.selected_candidate_id
        )
        return "\n".join(
            [
                "# V10.0 有界真实候选测试" if zh else "# V10.0 Bounded Real-candidate Test",
                "",
                f"**{'结论' if zh else 'Decision'}: `{self.decision}`**",
                "",
                f"- {'候选' if zh else 'Candidates'}: {len(self.candidates)}",
                f"- {'累计 Trial' if zh else 'Cumulative trials'}: {self.total_recorded_trials}",
                f"- {'入选表达式' if zh else 'Selected expression'}: `{winner.expression}`",
                f"- DSR: {self.dsr_probability:.6f}",
                f"- PBO: {self.pbo_probability:.6f}",
                f"- Signal / return / universe placebo p: {self.signal_placebo_p_value:.6f} / {self.return_placebo_p_value:.6f} / {self.universe_placebo_p_value:.6f}",
                f"- {'验证期净超额收益' if zh else 'Validation net excess return'}: {self.selected_validation.net_excess_total_return:.2%}",
                f"- Validation Sharpe: {self.selected_validation.annualized_net_excess_sharpe:.3f}",
                f"- {'验证期双倍成本收益' if zh else 'Validation double-cost return'}: {self.selected_validation.double_cost_total_return:.2%}",
                f"- {'容量' if zh else 'Capacity'}: CNY {self.selected_validation.capacity_cny:,.0f}",
                f"- {'拒绝的退化字段' if zh else 'Rejected degenerate fields'}: {', '.join(self.rejected_predictor_fields) or 'none'}",
                f"- {'失败门禁' if zh else 'Failed gates'}: {', '.join(self.failed_gates) or 'none'}",
                "",
                "> 2025–2026 未被读取；该结果不是冻结前向 PASS。"
                if zh
                else "> 2025–2026 were not read; this is not a sealed-forward PASS.",
                "",
            ]
        )


def _panel(root: Path, start: str, end: str) -> tuple[dict[str, object], ...]:
    query = """
    WITH raw AS (
      SELECT trade_date,instrument,close*adjustment_factor close_adj,open*adjustment_factor open_adj,
             amount*1000 amount_cny,
             lag(close*adjustment_factor,1) OVER w previous_close,
             lag(close*adjustment_factor,20) OVER w close_lag20,
             avg(amount*1000) OVER wprior prior_adv,
             lead(open*adjustment_factor,1) OVER w execution_open,
             lead(open*adjustment_factor,21) OVER w exit_open,
             lead(trade_date,1) OVER w execution_date,
             lead(trade_date,21) OVER w exit_date
      FROM qd_daily_current
      WINDOW w AS(PARTITION BY instrument ORDER BY trade_date),
             wprior AS(PARTITION BY instrument ORDER BY trade_date ROWS BETWEEN 60 PRECEDING AND 1 PRECEDING)
    ), d AS (
      SELECT *,stddev_samp(ln(close_adj/previous_close)) OVER(
        PARTITION BY instrument ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
      ) volatility_20 FROM raw
    ), dates AS (
      SELECT trade_date FROM (SELECT trade_date,row_number() OVER(ORDER BY trade_date) n FROM (SELECT DISTINCT trade_date FROM d))
      WHERE (n-1)%20=0
    ), eligible AS (
      SELECT d.*,row_number() OVER(PARTITION BY d.trade_date ORDER BY prior_adv DESC,instrument) liquidity_rank
      FROM d JOIN dates USING(trade_date)
      WHERE d.trade_date BETWEEN ? AND ? AND close_lag20>0 AND execution_open>0 AND exit_open>0 AND prior_adv>0
    )
    SELECT CAST(e.trade_date AS VARCHAR) signal_date,CAST(e.execution_date AS VARCHAR) execution_date,
           CAST(e.exit_date AS VARCHAR) exit_date,e.instrument,
           e.close_adj/e.close_lag20-1 ret_20,e.volatility_20,
           percent_rank() OVER(PARTITION BY e.trade_date ORDER BY e.prior_adv) amount_rank_20,
           f.intraday_return,f.late_30_return,f.realized_volatility,f.vwap_deviation,
           f.opening_volume_share,f.closing_volume_share,f.amihud_intraday,f.multiscale_divergence,
           e.exit_open/e.execution_open-1 forward_return,e.prior_adv
    FROM eligible e JOIN qd_minute_features_current f USING(trade_date,instrument)
    WHERE e.liquidity_rank<=800 AND f.sealed=false
    ORDER BY e.trade_date,e.instrument
    """
    connection = _duckdb().connect(str(root / "catalog" / "warehouse.duckdb"), read_only=True)
    try:
        cursor = connection.execute(query, [start, end])
        names = [item[0] for item in cursor.description]
        return tuple(dict(zip(names, row, strict=True)) for row in cursor.fetchall())
    finally:
        connection.close()


def _rank(values: list[float]) -> list[float]:
    ranks = average_ranks(values)
    return [value / (len(values) + 1) for value in ranks]


def _predictor_quality(
    rows: tuple[dict[str, object], ...], field_names: tuple[str, ...]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Screen predictors without reading returns or any other outcome label."""

    by_day: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_day[str(row["signal_date"])].append(row)
    dates = sorted(by_day)
    eligible: list[str] = []
    rejected: list[str] = []
    for field in field_names:
        variable_days = 0
        covered = 0
        for day in dates:
            values = [
                float(row[field])
                for row in by_day[day]
                if row.get(field) is not None
                and math.isfinite(float(row[field]))
            ]
            covered += bool(values)
            if len(set(values)) >= 20:
                variable_days += 1
        if dates and covered / len(dates) >= 0.8 and variable_days / len(dates) >= 0.8:
            eligible.append(field)
        else:
            rejected.append(field)
    return tuple(sorted(eligible)), tuple(sorted(rejected))


def _robust_discovery_key(report: PortfolioNativeReport) -> tuple[float, float, float, float]:
    """Prefer candidates that survive both halves of discovery before peak Sharpe."""

    periods = report.periods
    if len(periods) < 4:
        raise ValueError("V10 robust selection requires at least four discovery periods")
    middle = len(periods) // 2

    def compound(items) -> float:
        return math.prod(1.0 + item.net_excess_return for item in items) - 1.0

    first_half = compound(periods[:middle])
    second_half = compound(periods[middle:])
    return (
        min(first_half, second_half),
        report.double_cost_total_return,
        report.annualized_net_excess_sharpe,
        -report.total_turnover,
    )


def _observations(
    rows: tuple[dict[str, object], ...],
    candidate: V10Candidate,
    *,
    min_cross_section: int = 40,
) -> tuple[PortfolioObservation, ...]:
    by_day: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        if all(
            row.get(field.name) is not None and math.isfinite(float(row[field.name]))
            for field in candidate.fields
        ):
            by_day[str(row["execution_date"])].append(row)
    result: list[PortfolioObservation] = []
    for day in sorted(by_day):
        cross = by_day[day]
        # A sparse join or a non-finite field can leave a rebalance date with
        # too few tradable names for the frozen portfolio policy.  Such a date
        # is not a valid portfolio observation and must be omitted rather than
        # allowing the evaluator to construct a partial top-k portfolio.
        if len(cross) < min_cross_section:
            continue
        field_ranks = {
            field.name: _rank([float(row[field.name]) for row in cross])
            for field in candidate.fields
        }
        benchmark = mean(float(row["forward_return"]) for row in cross)
        for index, row in enumerate(cross):
            values = [field_ranks[field.name][index] for field in candidate.fields]
            score = (
                values[0]
                if candidate.operator == "rank"
                else values[0] - values[1]
                if candidate.operator == "divergence"
                else math.prod(values)
            )
            result.append(
                PortfolioObservation(
                    day,
                    str(row["instrument"]),
                    candidate.direction * score,
                    float(row["forward_return"]),
                    benchmark,
                    float(row["prior_adv"]),
                    f"{row['signal_date']}T18:00:00+08:00",
                    f"{day}T09:30:00+08:00",
                )
            )
    return tuple(result)


def _placebo(
    rows: tuple[PortfolioObservation, ...],
    observed: PortfolioNativeReport,
    policy: PortfolioPolicy,
    mode: str,
) -> float:
    if mode not in {"signal", "return", "universe"}:
        raise ValueError("unknown V10 placebo mode")
    grouped: dict[str, list[PortfolioObservation]] = defaultdict(list)
    for row in rows:
        grouped[row.date].append(row)
    rng = random.Random({"signal": 10010, "return": 10011, "universe": 10012}[mode])
    exceed = 0
    for _ in range(99):
        shuffled = []
        for day in sorted(grouped):
            cross = grouped[day]
            scores = [item.score for item in cross]
            returns = [item.forward_return for item in cross]
            if mode == "signal":
                rng.shuffle(scores)
            elif mode == "return":
                rng.shuffle(returns)
            if mode == "universe":
                # Perturb membership, not the signal.  Keeping a deterministic
                # 80% sample tests whether the result depends on the exact
                # tradable cross-section while preserving the frozen top-k.
                keep = max(policy.top_k, int(len(cross) * 0.8))
                indices = sorted(rng.sample(range(len(cross)), k=keep))
                shuffled.extend(cross[index] for index in indices)
            else:
                shuffled.extend(
                    replace(item, score=score, forward_return=forward_return)
                    for item, score, forward_return in zip(cross, scores, returns, strict=True)
                )
        exceed += (
            evaluate_portfolio_native(tuple(shuffled), policy=policy).net_excess_total_return
            >= observed.net_excess_total_return
        )
    return (exceed + 1) / 100


def run_v10_empirical(
    warehouse_root: str | Path,
    *,
    feature_snapshot_id: str,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    budget: int = 24,
    prior_trials: int = 533,
) -> V10EmpiricalReport:
    root = Path(warehouse_root).expanduser().resolve()
    rows = _panel(root, "2022-01-01", "2024-12-31")
    if not rows:
        raise ValueError("V10 daily-minute panel is empty")
    discovery_rows = tuple(row for row in rows if str(row["signal_date"]).startswith("2022-"))
    validation_rows = tuple(row for row in rows if str(row["signal_date"]) >= "2023-01-01")
    composite = build_composite_snapshot_manifest({"minute_features": feature_snapshot_id})
    snapshot_id = registry.register_snapshot(composite, vendor_version=V10_EMPIRICAL_VERSION)
    experiment_spec = ExperimentSpec(
        "v10_bounded_daily_minute",
        "Automatically generated daily-minute candidates",
        snapshot_id,
        code_version,
        json.dumps({"budget": budget}),
    )
    experiment_id = registry.create_experiment_deterministic(
        experiment_spec,
        f"v10|{V10_EMPIRICAL_VERSION}|{feature_snapshot_id}|{code_version}|{budget}",
    )
    historical = registry.historical_factor_sets(
        "v10_auto_factor", exclude_experiment_id=experiment_id
    )
    field_names = tuple(
        sorted(
            {
                field.name
                for candidate in generate_v10_candidates(
                    budget=512, enabled_sources=("qd_daily", "minute_features")
                ).candidates
                for field in candidate.fields
            }
        )
    )
    eligible_fields, rejected_fields = _predictor_quality(discovery_rows, field_names)
    candidates = tuple(
        item
        for item in generate_v10_candidates(
            budget=512,
            enabled_sources=("qd_daily", "minute_features"),
            historical_candidate_ids=historical,
        ).candidates
        if len(item.fields) <= 2 and all(field.name in eligible_fields for field in item.fields)
    )[:budget]
    if len(candidates) < budget:
        raise ValueError("V10 candidate space exhausted after historical tombstones")
    policy = PortfolioPolicy(
        initial_nav_cny=3_000_000, top_k=40, rank_buffer=10, round_trip_cost_bps=41.0
    )
    evidence = []
    observation_map = {}
    for candidate in candidates:
        trial_spec = TrialSpec(
            experiment_id,
            "v10_auto_factor",
            candidate.candidate_id,
            json.dumps(asdict(candidate), sort_keys=True),
            42,
            "2022-01-01",
            "2022-12-31",
            "2023-01-01",
            "2024-12-31",
            "2025-01-01",
            "2026-08-16",
        )
        trial_id, number = registry.create_trial_deterministic(
            trial_spec,
            f"v10|{experiment_id}|{candidate.candidate_id}",
        )
        obs = _observations(discovery_rows, candidate)
        observation_map[candidate.candidate_id] = obs
        evidence.append(
            V10CandidateEvidence(
                candidate.candidate_id,
                candidate.expression,
                trial_id,
                number,
                evaluate_portfolio_native(obs, policy=policy),
            )
        )
    selected = max(
        evidence,
        key=lambda item: (_robust_discovery_key(item.portfolio), item.candidate_id),
    )
    selected_obs = observation_map[selected.candidate_id]
    selected_candidate = next(
        item for item in candidates if item.candidate_id == selected.candidate_id
    )
    validation_obs = _observations(validation_rows, selected_candidate)
    validation = evaluate_portfolio_native(validation_obs, policy=policy)
    sharpes = [
        item.portfolio.annualized_net_excess_sharpe / math.sqrt(policy.periods_per_year)
        for item in evidence
    ]
    observed = selected.portfolio.annualized_net_excess_sharpe / math.sqrt(policy.periods_per_year)
    dsr = deflated_sharpe_ratio(
        observed_sharpe=observed,
        trial_sharpes=sharpes,
        recorded_trial_count=prior_trials + registry.global_trial_count(),
        observations=len(selected.portfolio.periods),
    )
    dates = sorted({row.date for row in selected_obs})
    timing = {
        str(row["execution_date"]): (str(row["signal_date"]), str(row["exit_date"]))
        for row in discovery_rows
        if str(row["execution_date"]) in set(dates)
    }
    samples = tuple(
        SampleInterval(
            day,
            "CROSS_SECTION",
            f"{timing[day][0]}T18:00:00+08:00",
            f"{day}T09:30:00+08:00",
            f"{timing[day][1]}T09:30:00+08:00",
        )
        for day in dates
    )
    manifest = generate_cpcv_manifest(
        samples,
        SplitLineage(feature_snapshot_id, experiment_id, evidence[0].trial_id, code_version),
        n_groups=6,
        n_test_groups=3,
        embargo=timedelta(days=5),
    )
    findings = audit_manifest(manifest, samples)
    train_scores = {}
    test_scores = {}
    for item in evidence:
        values = {p.date: p.net_excess_return for p in item.portfolio.periods}
        train_scores[item.candidate_id] = {
            f.fold_id: mean(values[d] for d in f.train_ids if d in values) for f in manifest.folds
        }
        test_scores[item.candidate_id] = {
            f.fold_id: mean(values[d] for d in f.test_ids if d in values) for f in manifest.folds
        }
    pbo = probability_of_fold_selection_overfitting(manifest, train_scores, test_scores, findings)
    signal_placebo = _placebo(validation_obs, validation, policy, "signal")
    return_placebo = _placebo(validation_obs, validation, policy, "return")
    universe_placebo = _placebo(validation_obs, validation, policy, "universe")
    failed = []
    if dsr.probability < 0.95:
        failed.append("DSR")
    if pbo.probability > 0.05:
        failed.append("PBO")
    if max(signal_placebo, return_placebo, universe_placebo) > 0.05:
        failed.append("PLACEBO")
    if validation.net_excess_total_return <= 0:
        failed.append("VALIDATION_RETURN")
    if validation.double_cost_total_return <= 0:
        failed.append("DOUBLE_COST")
    if not validation.capacity_passed:
        failed.append("CAPACITY")
    failed.append("SEALED_FORWARD_NOT_RUN")
    report = V10EmpiricalReport(
        V10_EMPIRICAL_VERSION,
        experiment_id,
        tuple(evidence),
        selected.candidate_id,
        validation,
        prior_trials + registry.global_trial_count(),
        dsr.probability,
        pbo.probability,
        signal_placebo,
        return_placebo,
        universe_placebo,
        all(x.passed for x in findings),
        eligible_fields,
        rejected_fields,
        "NO_RELIABLE_ALPHA",
        tuple(failed),
    )
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "v10-empirical.json").write_text(report.to_json() + "\n", encoding="utf-8")
    (output / "v10-empirical.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (output / "v10-empirical.en.md").write_text(report.to_markdown("en"), encoding="utf-8")
    return report
