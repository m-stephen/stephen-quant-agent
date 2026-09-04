from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean

from stephen_quant.discovery.portfolio_native import (
    PortfolioObservation,
    PortfolioPolicy,
    evaluate_portfolio_native,
)
from stephen_quant.discovery.v10_generator import V10Field
from stephen_quant.falsification import deflated_sharpe_ratio
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest
from stephen_quant.qmt.data_warehouse import _duckdb
from stephen_quant.qmt.multisource_warehouse import latest_multisource_snapshot

from .v10_empirical import _cross_source_panel, _panel, _rank
from .v11_bounded_epoch import (
    V11EpochCandidate,
    V11EpochEvidence,
    _failed_gates,
    _family_pbo,
    signal_portfolio_bridge,
)
from .v11_research_reset import (
    _sha,
    null_placebo,
    universe_robustness,
)

V111_VERSION = "v11.1-bounded-mechanism-discovery-1.0.0"
RAW_GLOBAL_TRIALS_BEFORE_V111 = 755
V111_BUDGET = 15


@dataclass(frozen=True)
class LabelFreeScreen:
    candidate_id: str
    feature_dates: int
    eligible_dates: int
    coverage_ratio: float
    variable_date_ratio: float
    estimated_turnover: float
    estimated_capacity_cny: float
    score_fingerprint: str
    passed: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class V111Report:
    method_version: str
    experiment_id: str
    decision: str
    frozen_budget: int
    inferential_trials_added: int
    raw_global_trials_after: int
    label_free_screens: tuple[LabelFreeScreen, ...]
    selected_candidate_ids: tuple[str, ...]
    candidates: tuple[V11EpochEvidence, ...]
    unauthorized_sealed_label_reads: int
    forced_stop: bool
    report_sha256: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True)

    def to_markdown(self, language: str) -> str:
        zh = language == "zh"
        lines = [
            "# V11.1 机制化 Alpha 研究" if zh else "# V11.1 Mechanism Discovery Epoch",
            "",
            f"**{'结论' if zh else 'Decision'}: `{self.decision}`**",
            "",
            (
                f"- {'标签读取前预筛通过' if zh else 'Passed label-free screens'}: "
                f"{sum(item.passed for item in self.label_free_screens)}/"
                f"{len(self.label_free_screens)}"
            ),
            (
                f"- {'新增 inferential Trial' if zh else 'Inferential Trials added'}: "
                f"{self.inferential_trials_added}"
            ),
            f"- {'累计原始 Trial' if zh else 'Raw global Trials'}: {self.raw_global_trials_after}",
            f"- {'晋级候选' if zh else 'Eligible candidates'}: {len(self.selected_candidate_ids)}",
            f"- {'强制停止' if zh else 'Forced stop'}: {str(self.forced_stop).lower()}",
            "",
            "| Mechanism | Candidate | H | Coverage | Net excess | Sharpe | Double cost | DSR | PBO | Result |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
        screen = {item.candidate_id: item for item in self.label_free_screens}
        for item in self.candidates:
            pbo = "N/I" if item.pbo_probability is None else f"{item.pbo_probability:.3f}"
            lines.append(
                f"| {item.candidate.mechanism} | `{item.candidate.expression}` | "
                f"{item.candidate.primary_horizon} | "
                f"{screen[item.candidate.candidate_id].coverage_ratio:.1%} | "
                f"{item.portfolio.net_excess_total_return:.2%} | "
                f"{item.portfolio.annualized_net_excess_sharpe:.3f} | "
                f"{item.portfolio.double_cost_total_return:.2%} | "
                f"{item.dsr_probability:.3f} | {pbo} | "
                f"{', '.join(item.failed_gates) or 'PASS'} |"
            )
        lines.extend(
            [
                "",
                (
                    "> 2022–2024 are development-only. The run stopped after the frozen "
                    "budget and did not read 2025–2026 historical return labels."
                    if not zh
                    else "> 2022–2024 仅为开发数据。本轮在冻结预算后停止，未读取 2025–2026 历史收益标签。"
                ),
                "",
            ]
        )
        return "\n".join(lines)


def _identity(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _field(name: str, source: str, unit: str = "ratio", availability: str = "T+1_OPEN") -> V10Field:
    return V10Field(name, source, unit, availability)


def _expression(operator: str, fields: tuple[V10Field, ...], direction: int) -> str:
    names = [item.name for item in fields]
    if operator == "rank":
        base = f"rank({names[0]})"
    elif operator == "divergence":
        base = f"rank({names[0]})-rank({names[1]})"
    elif operator == "centered_interaction":
        base = "*".join(f"(2*rank({name})-1)" for name in names)
    else:
        raise ValueError(f"unsupported V11.1 operator: {operator}")
    return base if direction > 0 else f"-({base})"


def _candidate(
    mechanism: str,
    horizon: int,
    operator: str,
    fields: tuple[V10Field, ...],
    direction: int,
    *,
    negative_control: bool = False,
) -> V11EpochCandidate:
    payload = {
        "version": V111_VERSION,
        "mechanism": mechanism,
        "horizon": horizon,
        "operator": operator,
        "fields": [asdict(item) for item in fields],
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


def frozen_v111_candidates() -> tuple[V11EpochCandidate, ...]:
    concentration = _field("concentration", "qd_chip")
    concentration_change = _field("concentration_change", "qd_chip", "change")
    profit_change = _field("profit_ratio_change", "qd_chip", "change")
    close_share = _field("closing_volume_share", "minute_features")
    vwap = _field("vwap_deviation", "minute_features", "return")
    main_flow = _field("main_inflow_ratio", "qd_fund_flow")
    main_flow_persist = _field("main_inflow_ratio_persistence", "qd_fund_flow")
    net_flow_persist = _field("net_inflow_ratio_persistence", "qd_fund_flow")
    net_flow_change = _field("net_inflow_ratio_change", "qd_fund_flow", "change")
    ret20 = _field("ret_20", "qd_daily", "return")
    auction = _field("auction_return", "qd_auction", "return", "T_OPEN")
    late = _field("late_30_return", "minute_features", "return")
    intraday = _field("intraday_return", "minute_features", "return")
    realized = _field("realized_volatility", "minute_features", "volatility")
    candidates = (
        _candidate("chip_state_transition", 20, "divergence", (concentration_change, profit_change), 1),
        _candidate("chip_state_transition", 20, "centered_interaction", (concentration_change, close_share), 1),
        _candidate("chip_state_transition", 20, "centered_interaction", (concentration_change, vwap), -1),
        _candidate("chip_state_transition", 20, "centered_interaction", (concentration_change, main_flow), 1),
        _candidate(
            "chip_state_transition",
            20,
            "centered_interaction",
            (concentration, profit_change),
            1,
            negative_control=True,
        ),
        _candidate("flow_price_mismatch", 10, "divergence", (net_flow_persist, ret20), 1),
        _candidate("flow_price_mismatch", 10, "divergence", (main_flow_persist, ret20), 1),
        _candidate("flow_price_mismatch", 10, "centered_interaction", (net_flow_persist, close_share), 1),
        _candidate("flow_price_mismatch", 10, "centered_interaction", (main_flow_persist, vwap), -1),
        _candidate(
            "flow_price_mismatch",
            10,
            "rank",
            (net_flow_change,),
            1,
            negative_control=True,
        ),
        _candidate("auction_close_absorption", 5, "divergence", (close_share, auction), 1),
        _candidate("auction_close_absorption", 5, "divergence", (late, auction), 1),
        _candidate("auction_close_absorption", 5, "centered_interaction", (auction, intraday), -1),
        _candidate("auction_close_absorption", 5, "divergence", (vwap, auction), 1),
        _candidate(
            "auction_close_absorption",
            5,
            "rank",
            (realized,),
            1,
            negative_control=True,
        ),
    )
    if len(candidates) != V111_BUDGET or len({item.candidate_id for item in candidates}) != V111_BUDGET:
        raise RuntimeError("V11.1 must contain exactly fifteen unique frozen candidates")
    for mechanism in {item.mechanism for item in candidates}:
        family = tuple(item for item in candidates if item.mechanism == mechanism)
        if len(family) != 5 or sum(item.negative_control for item in family) != 1:
            raise RuntimeError("each V11.1 family must contain four candidates and one control")
    return candidates


def _attach_industry(
    root: Path, rows: tuple[dict[str, object], ...]
) -> tuple[dict[str, object], ...]:
    connection = _duckdb().connect(str(root / "catalog" / "warehouse.duckdb"), read_only=True)
    try:
        exists = connection.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name='qd_sw_l2_membership_current'"
        ).fetchone()[0]
        memberships = (
            connection.execute(
                "SELECT CAST(snapshot_year AS VARCHAR),instrument,industry_code "
                "FROM qd_sw_l2_membership_current"
            ).fetchall()
            if exists
            else ()
        )
    finally:
        connection.close()
    index = {(str(year), str(instrument)): str(industry) for year, instrument, industry in memberships}
    result = []
    for source in rows:
        row = dict(source)
        row["industry_code"] = index.get((str(row["signal_date"])[:4], str(row["instrument"])), "UNKNOWN")
        result.append(row)
    return tuple(result)


def _attach_labels(
    root: Path,
    feature_rows: tuple[dict[str, object], ...],
    *,
    holding_sessions: int,
) -> tuple[dict[str, object], ...]:
    """Attach only the frozen forward-return columns after Trial registration."""

    label_rows = _panel(
        root,
        "2022-01-01",
        "2024-12-31",
        holding_sessions=holding_sessions,
        include_labels=True,
    )
    labels = {
        (str(row["signal_date"]), str(row["instrument"])): (
            row["exit_date"],
            row["forward_return"],
        )
        for row in label_rows
    }
    result = []
    for source in feature_rows:
        key = (str(source["signal_date"]), str(source["instrument"]))
        label = labels.get(key)
        if label is None:
            continue
        row = dict(source)
        row["exit_date"], row["forward_return"] = label
        result.append(row)
    return tuple(result)


def _raw_scores(
    cross: list[dict[str, object]], candidate: V11EpochCandidate
) -> dict[str, float]:
    usable = [
        row
        for row in cross
        if all(
            row.get(field.name) is not None and math.isfinite(float(row[field.name]))
            for field in candidate.fields
        )
        and row.get("amount_rank_20") is not None
        and row.get("volatility_20") is not None
    ]
    if len(usable) < 40:
        return {}
    ranks = {
        field.name: _rank([float(row[field.name]) for row in usable])
        for field in candidate.fields
    }
    scores: list[float] = []
    for index in range(len(usable)):
        values = [ranks[field.name][index] for field in candidate.fields]
        if candidate.operator == "rank":
            value = values[0]
        elif candidate.operator == "divergence":
            value = values[0] - values[1]
        elif candidate.operator == "centered_interaction":
            value = math.prod(2.0 * item - 1.0 for item in values)
        else:
            raise ValueError(f"unsupported V11.1 operator: {candidate.operator}")
        scores.append(candidate.direction * value)

    by_industry: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(usable):
        by_industry[str(row.get("industry_code", "UNKNOWN"))].append(index)
    global_mean = mean(scores)
    industry_adjusted = scores[:]
    for indices in by_industry.values():
        group_mean = mean(scores[index] for index in indices) if len(indices) >= 3 else global_mean
        for index in indices:
            industry_adjusted[index] -= group_mean

    x1 = [float(row["amount_rank_20"]) for row in usable]
    x2 = _rank([float(row["volatility_20"]) for row in usable])
    x1_mean, x2_mean = mean(x1), mean(x2)
    centered_x1 = [value - x1_mean for value in x1]
    centered_x2 = [value - x2_mean for value in x2]
    s11 = sum(value * value for value in centered_x1)
    s22 = sum(value * value for value in centered_x2)
    s12 = sum(left * right for left, right in zip(centered_x1, centered_x2, strict=True))
    sy1 = sum(left * value for left, value in zip(centered_x1, industry_adjusted, strict=True))
    sy2 = sum(left * value for left, value in zip(centered_x2, industry_adjusted, strict=True))
    determinant = s11 * s22 - s12 * s12
    beta1 = beta2 = 0.0
    if abs(determinant) > 1e-12:
        beta1 = (sy1 * s22 - sy2 * s12) / determinant
        beta2 = (sy2 * s11 - sy1 * s12) / determinant
    return {
        str(row["instrument"]): industry_adjusted[index]
        - beta1 * centered_x1[index]
        - beta2 * centered_x2[index]
        for index, row in enumerate(usable)
    }


def label_free_screen(
    rows: tuple[dict[str, object], ...], candidate: V11EpochCandidate
) -> LabelFreeScreen:
    by_day: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_day[str(row["execution_date"])].append(row)
    eligible = 0
    variable = 0
    previous: tuple[str, ...] = ()
    turnover = 0.0
    capacity = math.inf
    fingerprint_rows: list[tuple[str, str, float]] = []
    for day in sorted(by_day):
        scores = _raw_scores(by_day[day], candidate)
        if len(scores) < 40:
            continue
        eligible += 1
        if len({round(value, 12) for value in scores.values()}) >= 20:
            variable += 1
        ranked = sorted(scores, key=lambda name: (-scores[name], name))
        ranks = {name: index + 1 for index, name in enumerate(ranked)}
        retained = [name for name in previous if ranks.get(name, 51) <= 50]
        selected = retained[:40] + [name for name in ranked if name not in retained][: 40 - len(retained)]
        holdings = tuple(sorted(selected))
        old_weight = 1.0 / len(previous) if previous else 0.0
        new_weight = 1.0 / len(holdings)
        turnover += 0.5 * sum(
            abs((new_weight if name in holdings else 0.0) - (old_weight if name in previous else 0.0))
            for name in set(previous) | set(holdings)
        )
        row_index = {str(row["instrument"]): row for row in by_day[day]}
        capacity = min(
            capacity,
            min(float(row_index[name]["prior_adv"]) * 0.05 / new_weight for name in holdings),
        )
        fingerprint_rows.extend((day, name, round(scores[name], 10)) for name in sorted(scores))
        previous = holdings
    total_dates = len(by_day)
    coverage = eligible / total_dates if total_dates else 0.0
    variable_ratio = variable / eligible if eligible else 0.0
    reasons = []
    if coverage < 0.70:
        reasons.append("FEATURE_DATE_COVERAGE")
    if variable_ratio < 0.90:
        reasons.append("CROSS_SECTION_VARIATION")
    if not math.isfinite(capacity) or capacity < 3_000_000:
        reasons.append("ESTIMATED_CAPACITY")
    return LabelFreeScreen(
        candidate.candidate_id,
        total_dates,
        eligible,
        coverage,
        variable_ratio,
        turnover,
        0.0 if not math.isfinite(capacity) else capacity,
        _identity(fingerprint_rows),
        not reasons,
        tuple(reasons),
    )


def _observations(
    rows: tuple[dict[str, object], ...], candidate: V11EpochCandidate
) -> tuple[PortfolioObservation, ...]:
    by_day: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_day[str(row["execution_date"])].append(row)
    result: list[PortfolioObservation] = []
    for day in sorted(by_day):
        cross = by_day[day]
        scores = _raw_scores(cross, candidate)
        if len(scores) < 40:
            continue
        usable = [row for row in cross if str(row["instrument"]) in scores]
        benchmark = mean(float(row["forward_return"]) for row in usable)
        for row in usable:
            result.append(
                PortfolioObservation(
                    day,
                    str(row["instrument"]),
                    scores[str(row["instrument"])],
                    float(row["forward_return"]),
                    benchmark,
                    float(row["prior_adv"]),
                    f"{row['signal_date']}T18:00:00+08:00",
                    f"{day}T09:30:00+08:00",
                )
            )
    return tuple(result)


def _write_report(report: V111Report, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "V11_1_MECHANISM_RESULT.json").write_text(report.to_json() + "\n", encoding="utf-8")
    (output / "V11_1_MECHANISM_RESULT.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (output / "V11_1_MECHANISM_RESULT.en.md").write_text(report.to_markdown("en"), encoding="utf-8")


def run_v111_mechanism_epoch(
    warehouse_root: str | Path,
    *,
    feature_snapshot_id: str,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
) -> V111Report:
    root = Path(warehouse_root).resolve()
    output = Path(output_dir).resolve()
    if (output / "V11_1_MECHANISM_RESULT.json").exists():
        raise ValueError("V11.1 result already exists; the bounded epoch is not replayable")
    candidates = frozen_v111_candidates()
    feature_rows = {
        horizon: _attach_industry(
            root,
            _cross_source_panel(
                root,
                "2022-01-01",
                "2024-12-31",
                holding_sessions=horizon,
                include_labels=False,
            )[0],
        )
        for horizon in (5, 10, 20)
    }
    screens = tuple(
        label_free_screen(feature_rows[item.primary_horizon], item) for item in candidates
    )
    fingerprints = [item.score_fingerprint for item in screens]
    duplicate_fingerprints = {value for value in fingerprints if fingerprints.count(value) > 1}
    if duplicate_fingerprints:
        screens = tuple(
            LabelFreeScreen(
                item.candidate_id,
                item.feature_dates,
                item.eligible_dates,
                item.coverage_ratio,
                item.variable_date_ratio,
                item.estimated_turnover,
                item.estimated_capacity_cny,
                item.score_fingerprint,
                False,
                item.reasons + ("NUMERIC_DUPLICATE",),
            )
            if item.score_fingerprint in duplicate_fingerprints
            else item
            for item in screens
        )
    if not all(item.passed for item in screens):
        payload = {
            "method_version": V111_VERSION,
            "experiment_id": "NOT_CREATED",
            "decision": "LABEL_FREE_PREFILTER_NOT_READY",
            "frozen_budget": V111_BUDGET,
            "inferential_trials_added": 0,
            "raw_global_trials_after": RAW_GLOBAL_TRIALS_BEFORE_V111,
            "label_free_screens": [asdict(item) for item in screens],
            "selected_candidate_ids": [],
            "candidates": [],
            "unauthorized_sealed_label_reads": 0,
            "forced_stop": True,
        }
        report = V111Report(
            V111_VERSION,
            "NOT_CREATED",
            "LABEL_FREE_PREFILTER_NOT_READY",
            V111_BUDGET,
            0,
            RAW_GLOBAL_TRIALS_BEFORE_V111,
            screens,
            (),
            (),
            0,
            True,
            _sha(payload),
        )
        _write_report(report, output)
        return report

    multisource = latest_multisource_snapshot(root)
    snapshot = registry.register_snapshot(
        build_composite_snapshot_manifest(
            {"minute_features": feature_snapshot_id, "multisource": multisource}
        ),
        vendor_version=V111_VERSION,
    )
    experiment = registry.create_experiment_deterministic(
        ExperimentSpec(
            "v11_1_bounded_mechanism_discovery",
            "Fifteen preregistered candidates after label-free screening",
            snapshot,
            code_version,
            json.dumps([asdict(item) for item in candidates], sort_keys=True),
        ),
        f"{V111_VERSION}|{snapshot}|{code_version}",
    )
    trials = {
        item.candidate_id: registry.create_trial_deterministic(
            TrialSpec(
                experiment,
                "v11_1_mechanism",
                item.candidate_id,
                json.dumps(asdict(item), sort_keys=True),
                111,
                "2022-01-01",
                "2024-12-31",
                "DEVELOPMENT_ONLY",
                "DEVELOPMENT_ONLY",
                "SEALED",
                "SEALED",
            ),
            f"{V111_VERSION}|{experiment}|{item.candidate_id}",
        )
        for item in candidates
    }

    label_rows = {
        horizon: _attach_labels(
            root,
            feature_rows[horizon],
            holding_sessions=horizon,
        )
        for horizon in (5, 10, 20)
    }
    policies = {
        horizon: PortfolioPolicy(
            initial_nav_cny=3_000_000,
            top_k=40,
            rank_buffer=10,
            round_trip_cost_bps=41.0,
            participation_rate=0.05,
            periods_per_year=max(1, 252 // horizon),
        )
        for horizon in label_rows
    }
    observations = {
        item.candidate_id: _observations(label_rows[item.primary_horizon], item)
        for item in candidates
    }
    portfolios = {
        item.candidate_id: evaluate_portfolio_native(
            observations[item.candidate_id], policy=policies[item.primary_horizon]
        )
        for item in candidates
    }
    family_pbo = {}
    for mechanism in sorted({item.mechanism for item in candidates}):
        family = tuple(item for item in candidates if item.mechanism == mechanism)
        horizon = family[0].primary_horizon
        family_pbo[mechanism] = _family_pbo(
            mechanism,
            family,
            portfolios,
            label_rows[horizon],
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
        portfolio = portfolios[item.candidate_id]
        rows = observations[item.candidate_id]
        policy = policies[item.primary_horizon]
        robustness = universe_robustness(rows, policy, samples=49)
        signal_null = null_placebo(rows, policy, mode="stratified_signal", samples=49)
        return_null = null_placebo(rows, policy, mode="stratified_return", samples=49)
        construction_null = null_placebo(rows, policy, mode="universe_construction", samples=49)
        dsr = deflated_sharpe_ratio(
            observed_sharpe=portfolio.annualized_net_excess_sharpe
            / math.sqrt(portfolio.policy.periods_per_year),
            trial_sharpes=sharpes,
            recorded_trial_count=RAW_GLOBAL_TRIALS_BEFORE_V111 + V111_BUDGET,
            observations=len(portfolio.periods),
        ).probability
        identifiable, pbo = family_pbo[item.mechanism]
        failed = _failed_gates(
            item,
            portfolio,
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
            portfolio,
            signal_portfolio_bridge(portfolio),
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
    selected = tuple(item.candidate.candidate_id for item in evidence if not item.failed_gates)
    decision = (
        "ELIGIBLE_FOR_INDEPENDENT_FORWARD_EVIDENCE"
        if selected
        else "NO_CANDIDATE_FOR_FORWARD_OBSERVATION"
    )
    payload = {
        "method_version": V111_VERSION,
        "experiment_id": experiment,
        "decision": decision,
        "frozen_budget": V111_BUDGET,
        "inferential_trials_added": V111_BUDGET,
        "raw_global_trials_after": RAW_GLOBAL_TRIALS_BEFORE_V111 + V111_BUDGET,
        "label_free_screens": [asdict(item) for item in screens],
        "selected_candidate_ids": selected,
        "candidates": [asdict(item) for item in evidence],
        "unauthorized_sealed_label_reads": 0,
        "forced_stop": True,
    }
    report = V111Report(
        V111_VERSION,
        experiment,
        decision,
        V111_BUDGET,
        V111_BUDGET,
        RAW_GLOBAL_TRIALS_BEFORE_V111 + V111_BUDGET,
        screens,
        selected,
        tuple(evidence),
        0,
        True,
        _sha(payload),
    )
    _write_report(report, output)
    return report
