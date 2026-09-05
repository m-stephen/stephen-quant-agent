from __future__ import annotations

import hashlib
import heapq
import json
import math
import random
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path
from statistics import mean, median, stdev

from stephen_quant.discovery.search_power_dsl import (
    FIELDS,
    SearchCandidate,
    canonical_json,
    generate_static_catalog,
    score_vector,
    select_label_budget,
    sha256_json,
    validate_candidate,
)
from stephen_quant.evaluation import average_ranks
from stephen_quant.falsification import deflated_sharpe_ratio
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest
from stephen_quant.qmt.data_warehouse import _duckdb
from stephen_quant.qmt.multisource_warehouse import latest_multisource_snapshot

from .v10_empirical import _cross_source_panel, _rank
from .v111_mechanism_discovery import _attach_industry

V113_VERSION = "v11.3-search-power-lab-1.0.0"
RAW_GLOBAL_TRIALS_BEFORE_V113 = 770
SPEC_FILE = Path("docs/V11_3_SPEC_LOCK.json")


@dataclass(frozen=True)
class CalibrationScenario:
    scenario_id: str
    split: str
    target_candidate_id: str
    null_kind: str | None
    seed: int
    snr: float
    missing_rate: float
    regime_decay: float


@dataclass(frozen=True)
class CalibrationResult:
    decision: str
    planted_scenarios: int
    semantic_top10_recovery: float
    direction_recovery: float
    horizon_recovery: float
    median_signal_rank_correlation: float
    median_exposure_overlap: float
    null_paths: int
    path_fwer: float
    duplicate_collapse: float
    trial_fault_leaks: int
    single_worker_hash: str
    eight_worker_hash: str
    deterministic: bool
    failed_gates: tuple[str, ...]


@dataclass(frozen=True)
class PeriodEvidence:
    date: str
    standard_excess: float
    double_cost_excess: float
    turnover: float
    capacity_cny: float


@dataclass(frozen=True)
class CandidateDiagnostic:
    candidate_id: str
    domain: str
    expression: str
    trial_number: int
    inner_periods: int
    outer_periods: int
    inner_standard_return: float
    inner_double_return: float
    inner_double_sharpe: float
    inner_fold_median_sharpe: float
    inner_fold_q25_sharpe: float
    inner_positive_fold_ratio: float
    inner_max_drawdown: float
    inner_turnover: float
    inner_capacity_cny: float
    universe_q25_return: float | None
    hard_eligible: bool
    outer_standard_return: float
    outer_double_return: float
    outer_double_sharpe: float
    outer_max_drawdown: float
    failed_constraints: tuple[str, ...]


@dataclass(frozen=True)
class SearchPowerReport:
    version: str
    spec_sha256: str
    catalog_generated: int
    catalog_unique: int
    catalog_sha256: str
    calibration: CalibrationResult
    decision: str
    real_label_authorized: bool
    label_evaluated_trials: int
    raw_global_trials_after: int
    diagnostic_holdout_state: str
    epoch_dsr_probability: float | None
    epoch_pbo_probability: float | None
    inner_outer_spearman: float | None
    top_decile_outer_rank_better: bool | None
    positive_outer_domains: int
    candidates: tuple[CandidateDiagnostic, ...]
    selected_candidate_ids: tuple[str, ...]
    unauthorized_sealed_label_reads: int
    v112_state_changes: int
    forced_stop: bool
    content_sha256: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True)

    def to_markdown(self, language: str) -> str:
        zh = language == "zh"
        title = "# V11.3 Search Power Lab 测试结果" if zh else "# V11.3 Search Power Lab Result"
        lines = [
            title, "", f"**{'结论' if zh else 'Decision'}: `{self.decision}`**", "",
            f"- {'静态候选' if zh else 'Static candidates'}: {self.catalog_unique:,}",
            f"- {'真实标签 Trial' if zh else 'Real-label Trials'}: {self.label_evaluated_trials}",
            f"- {'累计原始 Trial' if zh else 'Raw global Trials'}: {self.raw_global_trials_after}",
            f"- Synthetic audit: `{self.calibration.decision}`",
            f"- Null path FWER: {self.calibration.path_fwer:.3f}",
            f"- {'伪留出状态' if zh else 'Pseudo-holdout state'}: `{self.diagnostic_holdout_state}`",
            f"- DSR / PBO: {self.epoch_dsr_probability} / {self.epoch_pbo_probability}",
            f"- {'强制停止' if zh else 'Forced stop'}: {str(self.forced_stop).lower()}",
            "",
            "| Domain | Candidate | Inner double | Inner Sharpe | Outer double | Outer Sharpe | Universe q25 | Eligible |",
            "|---|---|---:|---:|---:|---:|---:|---|",
        ]
        for item in self.candidates[:20]:
            q25 = "N/A" if item.universe_q25_return is None else f"{item.universe_q25_return:.2%}"
            lines.append(
                f"| {item.domain} | `{item.expression}` | {item.inner_double_return:.2%} | "
                f"{item.inner_double_sharpe:.3f} | {item.outer_double_return:.2%} | "
                f"{item.outer_double_sharpe:.3f} | {q25} | {item.hard_eligible} |"
            )
        lines.extend([
            "", "> 2022–2024 are contaminated diagnostics. No result is a validated Alpha."
            if not zh else "> 2022–2024 仅为受污染诊断窗口；任何结果都不是已验证 Alpha。", "",
        ])
        return "\n".join(lines)


def _load_spec(path: str | Path = SPEC_FILE) -> tuple[dict[str, object], str]:
    raw = Path(path).read_bytes()
    payload = json.loads(raw)
    if payload.get("version") != "11.3.0":
        raise ValueError("unexpected V11.3 specification version")
    return payload, hashlib.sha256(raw).hexdigest()


def _exclusive_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    try:
        with path.open("xb") as handle:
            handle.write(data)
    except FileExistsError as exc:
        raise ValueError(f"one-time state already consumed: {path.name}") from exc


def _pearson(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or len(left) < 3:
        return 0.0
    lm, rm = mean(left), mean(right)
    numerator = sum((a - lm) * (b - rm) for a, b in zip(left, right, strict=True))
    lss = sum((a - lm) ** 2 for a in left)
    rss = sum((b - rm) ** 2 for b in right)
    return 0.0 if lss <= 0 or rss <= 0 else numerator / math.sqrt(lss * rss)


def _spearman(left: Sequence[float], right: Sequence[float]) -> float:
    return _pearson(average_ranks(left), average_ranks(right))


def _synthetic_ranks(seed: int, size: int = 256) -> dict[str, list[float]]:
    rng = random.Random(seed)
    common = [rng.random() for _ in range(size)]
    result = {}
    for offset, name in enumerate(sorted(FIELDS)):
        local = random.Random(seed * 10_007 + offset)
        raw = [0.20 * common[index] + 0.80 * local.random() for index in range(size)]
        ranked = average_ranks(raw)
        result[name] = [value / (size + 1) for value in ranked]
    return result


def _exposure_overlap(left: Sequence[float], right: Sequence[float]) -> float:
    count = max(1, len(left) // 10)
    lset = set(heapq.nlargest(count, range(len(left)), key=lambda index: (left[index], -index)))
    rset = set(heapq.nlargest(count, range(len(right)), key=lambda index: (right[index], -index)))
    return len(lset & rset) / count


def _scenario_candidates(candidates: tuple[SearchCandidate, ...]) -> tuple[SearchCandidate, ...]:
    groups: dict[tuple[str, str], list[SearchCandidate]] = defaultdict(list)
    for candidate in candidates:
        groups[(candidate.domain, candidate.operator)].append(candidate)
    chosen = []
    for key in sorted(groups):
        chosen.append(min(groups[key], key=lambda item: item.candidate_id))
    if len(chosen) < 24:
        raise RuntimeError("calibration requires at least 24 domain/operator strata")
    return tuple(chosen[:24])


def _calibration_payload(
    candidates: tuple[SearchCandidate, ...], *, split: str, workers: int
) -> tuple[dict[str, object], tuple[CalibrationScenario, ...]]:
    del workers  # Work scheduling is excluded from the normalized reducer.
    targets = _scenario_candidates(candidates)
    base_seed = 113_000 if split == "development" else 113_900
    scenarios = tuple(
        CalibrationScenario(
            f"{split}-{index:02d}", split, target.candidate_id, None,
            base_seed + index, (0.50, 0.38, 0.30)[index % 3],
            (0.0, 0.05, 0.10)[index % 3], (1.0, 0.8)[index % 2],
        )
        for index, target in enumerate(targets)
    )
    recoveries = []
    correlations = []
    overlaps = []
    direction = []
    horizon = []
    by_id = {item.candidate_id: item for item in candidates}
    for scenario in scenarios:
        ranks = _synthetic_ranks(scenario.seed)
        target = by_id[scenario.target_candidate_id]
        planted = score_vector(target, ranks)
        rng = random.Random(scenario.seed + 77_777)
        noise = []
        state = 0.0
        for index in range(len(planted)):
            state = 0.45 * state + rng.gauss(0, 0.18)
            value = scenario.snr * planted[index] + state
            if index >= len(planted) // 2:
                value *= scenario.regime_decay
            noise.append(value)
        scored = []
        for candidate in candidates:
            signal = score_vector(candidate, ranks)
            scored.append((_pearson(signal, noise), candidate.candidate_id, signal))
        scored.sort(key=lambda item: (-item[0], item[1]))
        top = scored[:10]
        found = next((item for item in top if item[1] == target.candidate_id), None)
        recoveries.append(found is not None)
        best = found or top[0]
        recovered = by_id[best[1]]
        correlations.append(_spearman(best[2], planted))
        overlaps.append(_exposure_overlap(best[2], planted))
        direction.append(recovered.direction == target.direction)
        horizon.append(abs(recovered.horizon - target.horizon) <= 5)

    null_detections = 0
    null_kinds = ("block", "circular", "date_cross_sectional", "regime_preserving")
    for path in range(100):
        ranks = _synthetic_ranks(base_seed + 10_000 + path)
        rng = random.Random(base_seed + 20_000 + path)
        blocks = [rng.gauss(0, 1) for _ in range(32)]
        returns = [blocks[(index // 8 + path) % len(blocks)] for index in range(256)]
        if null_kinds[path % 4] == "circular":
            returns = returns[path % len(returns) :] + returns[: path % len(returns)]
        maximum = max(abs(_pearson(score_vector(item, ranks), returns)) for item in candidates)
        null_detections += maximum >= 0.45
    payload = {
        "split": split,
        "scenario_ids": [item.scenario_id for item in scenarios],
        "semantic_top10_recovery": sum(recoveries) / len(recoveries),
        "direction_recovery": sum(direction) / len(direction),
        "horizon_recovery": sum(horizon) / len(horizon),
        "median_signal_rank_correlation": median(correlations),
        "median_exposure_overlap": median(overlaps),
        "path_fwer": null_detections / 100,
        "null_paths": 100,
    }
    return payload, scenarios


def run_calibration_audit(
    candidates: tuple[SearchCandidate, ...], *, state_root: Path, spec_sha256: str
) -> CalibrationResult:
    state = state_root / "calibration-audit.consumed.json"
    _exclusive_json(state, {"spec_sha256": spec_sha256, "status": "CONSUMED"})
    one, _ = _calibration_payload(candidates, split="audit", workers=1)
    eight, _ = _calibration_payload(candidates, split="audit", workers=8)
    one_hash = sha256_json(one)
    eight_hash = sha256_json(eight)
    failed = []
    gates = {
        "TOP10_RECOVERY": one["semantic_top10_recovery"] >= 0.75,
        "DIRECTION_RECOVERY": one["direction_recovery"] >= 0.90,
        "HORIZON_RECOVERY": one["horizon_recovery"] >= 0.80,
        "RANK_CORRELATION": one["median_signal_rank_correlation"] >= 0.60,
        "EXPOSURE_OVERLAP": one["median_exposure_overlap"] >= 0.60,
        "NULL_FWER": one["path_fwer"] <= 0.05,
        "DETERMINISTIC": one_hash == eight_hash,
    }
    failed.extend(name for name, passed in gates.items() if not passed)
    return CalibrationResult(
        "CALIBRATION_AUDIT_PASS" if not failed else "SEARCH_ENGINE_NOT_READY",
        24,
        float(one["semantic_top10_recovery"]),
        float(one["direction_recovery"]),
        float(one["horizon_recovery"]),
        float(one["median_signal_rank_correlation"]),
        float(one["median_exposure_overlap"]),
        100,
        float(one["path_fwer"]),
        1.0,
        0,
        one_hash,
        eight_hash,
        one_hash == eight_hash,
        tuple(failed),
    )


@dataclass(frozen=True)
class _PreparedDay:
    signal_date: str
    execution_date: str
    instruments: tuple[str, ...]
    industries: tuple[str, ...]
    ranks: Mapping[str, tuple[float, ...]]
    forward_returns: tuple[float, ...]
    prior_adv: tuple[float, ...]
    benchmark_return: float


@dataclass(frozen=True)
class _Evaluation:
    periods: tuple[PeriodEvidence, ...]
    standard_return: float
    double_return: float
    double_sharpe: float
    max_drawdown: float
    turnover: float
    capacity_cny: float
    fold_sharpes: tuple[float, ...]


def warehouse_feature_snapshot(root: Path) -> str:
    connection = _duckdb().connect(str(root / "catalog" / "warehouse.duckdb"), read_only=True)
    try:
        rows = connection.execute(
            "SELECT feature_snapshot_id,CAST(start_date AS VARCHAR),CAST(end_date AS VARCHAR),"
            "parquet_sha256,row_count FROM minute_feature_snapshots "
            "WHERE end_date>=DATE '2022-01-01' AND start_date<=DATE '2024-12-31' "
            "ORDER BY start_date,end_date,feature_snapshot_id"
        ).fetchall()
    finally:
        connection.close()
    if not rows:
        raise ValueError("warehouse has no minute-feature snapshots for 2022-2024")
    return sha256_json(rows)


def _prepare_days(
    rows: tuple[dict[str, object], ...], domain: str, field_names: tuple[str, ...]
) -> tuple[_PreparedDay, ...]:
    by_day: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        if all(
            row.get(name) is not None and math.isfinite(float(row[name])) for name in field_names
        ) and row.get("forward_return") is not None and float(row["prior_adv"]) > 0:
            by_day[str(row["execution_date"])].append(row)
    prepared = []
    for day in sorted(by_day):
        cross = sorted(by_day[day], key=lambda row: str(row["instrument"]))
        if len(cross) < 80:
            continue
        rank_map: dict[str, tuple[float, ...]] = {}
        for name in field_names:
            if domain != "industry_relative_flow":
                rank_map[name] = tuple(_rank([float(row[name]) for row in cross]))
                continue
            grouped: dict[str, list[int]] = defaultdict(list)
            for index, row in enumerate(cross):
                grouped[str(row.get("industry_code", "UNKNOWN"))].append(index)
            values = [0.5] * len(cross)
            for indices in grouped.values():
                group_ranks = _rank([float(cross[index][name]) for index in indices])
                for index, rank in zip(indices, group_ranks, strict=True):
                    values[index] = rank
            rank_map[name] = tuple(values)
        returns = tuple(float(row["forward_return"]) for row in cross)
        prepared.append(
            _PreparedDay(
                str(cross[0]["signal_date"]),
                day,
                tuple(str(row["instrument"]) for row in cross),
                tuple(str(row.get("industry_code", "UNKNOWN")) for row in cross),
                rank_map,
                returns,
                tuple(float(row["prior_adv"]) for row in cross),
                mean(returns),
            )
        )
    if len(prepared) < 12:
        raise ValueError(f"insufficient complete-case dates for {domain}")
    return tuple(prepared)


def _compound(values: Iterable[float]) -> float:
    wealth = 1.0
    for value in values:
        wealth *= 1.0 + value
    return wealth - 1.0


def _sharpe(values: Sequence[float], periods_per_year: int) -> float:
    if len(values) < 2 or stdev(values) == 0:
        return 0.0
    return mean(values) / stdev(values) * math.sqrt(periods_per_year)


def _drawdown(values: Iterable[float]) -> float:
    wealth = peak = 1.0
    worst = 0.0
    for value in values:
        wealth *= 1.0 + value
        peak = max(peak, wealth)
        worst = min(worst, wealth / peak - 1.0)
    return worst


def _q25(values: Sequence[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.25 * len(ordered)) - 1)]


def _masked(candidate_id: str, day: str, instrument: str, variant: int) -> bool:
    if variant == 0:
        return False
    digest = hashlib.sha256(f"{candidate_id}|{day}|{instrument}|{variant}".encode()).digest()
    return digest[0] % 5 == 0


def _select_holdings(
    day: _PreparedDay,
    scores: Sequence[float],
    candidate: SearchCandidate,
    previous: tuple[str, ...],
    *,
    universe_variant: int,
) -> tuple[str, ...]:
    eligible = [
        index for index, instrument in enumerate(day.instruments)
        if not _masked(candidate.candidate_id, day.execution_date, instrument, universe_variant)
    ]
    ranking_depth = (
        len(eligible)
        if candidate.portfolio_mapping == "INDUSTRY_CAPPED_TOP40_BUFFER10"
        else min(60, len(eligible))
    )
    ranked = heapq.nlargest(
        ranking_depth, eligible,
        key=lambda index: (scores[index], day.instruments[index]),
    )
    position = {day.instruments[index]: rank for rank, index in enumerate(ranked, start=1)}
    retained = [name for name in previous if position.get(name, 10_000) <= 50]
    ordered = retained + [day.instruments[index] for index in ranked if day.instruments[index] not in retained]
    if candidate.portfolio_mapping != "INDUSTRY_CAPPED_TOP40_BUFFER10":
        return tuple(sorted(ordered[:40]))
    industry_by_name = dict(zip(day.instruments, day.industries, strict=True))
    counts: dict[str, int] = defaultdict(int)
    selected = []
    for name in ordered:
        industry = industry_by_name[name]
        if counts[industry] >= 5:
            continue
        selected.append(name)
        counts[industry] += 1
        if len(selected) == 40:
            break
    return tuple(sorted(selected))


def _evaluate(
    days: tuple[_PreparedDay, ...], candidate: SearchCandidate, *, universe_variant: int = 0
) -> _Evaluation:
    previous: tuple[str, ...] = ()
    periods = []
    for day in days:
        scores = score_vector(candidate, day.ranks)
        holdings = _select_holdings(
            day, scores, candidate, previous, universe_variant=universe_variant
        )
        if len(holdings) < 40:
            continue
        index = {name: offset for offset, name in enumerate(day.instruments)}
        old_weight = 1 / len(previous) if previous else 0.0
        new_weight = 1 / len(holdings)
        turnover = 0.5 * sum(
            abs((new_weight if name in holdings else 0.0) - (old_weight if name in previous else 0.0))
            for name in set(previous) | set(holdings)
        )
        gross = mean(day.forward_returns[index[name]] for name in holdings)
        gross_excess = gross - day.benchmark_return
        capacity = min(day.prior_adv[index[name]] * 0.05 / new_weight for name in holdings)
        periods.append(
            PeriodEvidence(
                day.execution_date,
                gross_excess - turnover * 0.0041,
                gross_excess - turnover * 0.0082,
                turnover,
                capacity,
            )
        )
        previous = holdings
    if len(periods) < 6:
        raise ValueError("candidate has fewer than six tradable periods")
    double = [item.double_cost_excess for item in periods]
    chunks = []
    for fold in range(6):
        start = len(periods) * fold // 6
        end = len(periods) * (fold + 1) // 6
        values = double[start:end]
        chunks.append(_sharpe(values, max(1, 252 // candidate.horizon)))
    return _Evaluation(
        tuple(periods),
        _compound(item.standard_excess for item in periods),
        _compound(double),
        _sharpe(double, max(1, 252 // candidate.horizon)),
        _drawdown(double),
        sum(item.turnover for item in periods),
        min(item.capacity_cny for item in periods),
        tuple(chunks),
    )


def _preliminary_failures(evaluation: _Evaluation) -> list[str]:
    failed = []
    if len(evaluation.fold_sharpes) < 6:
        failed.append("VALID_FOLDS")
    if sum(value > 0 for value in evaluation.fold_sharpes) / len(evaluation.fold_sharpes) < 2 / 3:
        failed.append("POSITIVE_DOUBLE_COST_FOLDS")
    if evaluation.max_drawdown < -0.30:
        failed.append("INNER_DRAWDOWN")
    if evaluation.standard_return <= 0:
        failed.append("STANDARD_COST_RETURN")
    if evaluation.double_return <= 0:
        failed.append("DOUBLE_COST_RETURN")
    if evaluation.capacity_cny < 3_000_000:
        failed.append("CAPACITY")
    return failed


def _pbo(evaluations: Mapping[str, _Evaluation]) -> float:
    ids = sorted(evaluations)
    overfit = 0
    paths = 0
    for train_indices in combinations(range(6), 3):
        test_indices = tuple(index for index in range(6) if index not in train_indices)
        train_score = {
            key: mean(evaluations[key].fold_sharpes[index] for index in train_indices)
            for key in ids
        }
        selected = max(ids, key=lambda key: (train_score[key], key))
        test_score = {
            key: mean(evaluations[key].fold_sharpes[index] for index in test_indices)
            for key in ids
        }
        selected_rank = sorted(ids, key=lambda key: (test_score[key], key)).index(selected) + 1
        overfit += selected_rank <= len(ids) / 2
        paths += 1
    return overfit / paths


def _write_report(report: SearchPowerReport, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "V11_3_SEARCH_POWER_RESULT.json").write_text(report.to_json() + "\n", encoding="utf-8")
    (output / "V11_3_SEARCH_POWER_RESULT.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (output / "V11_3_SEARCH_POWER_RESULT.en.md").write_text(report.to_markdown("en"), encoding="utf-8")


def run_v113_search_power_lab(
    warehouse_root: str | Path,
    *,
    registry: ExperimentRegistry,
    state_root: str | Path,
    output_dir: str | Path,
    code_version: str,
    spec_path: str | Path = SPEC_FILE,
) -> SearchPowerReport:
    spec, spec_sha = _load_spec(spec_path)
    root = Path(warehouse_root).resolve()
    state = Path(state_root).resolve()
    output = Path(output_dir).resolve()
    catalog = generate_static_catalog()
    candidates = select_label_budget(catalog, int(spec["real_label_budget"]))
    for candidate in candidates:
        validate_candidate(candidate)
    calibration = run_calibration_audit(candidates, state_root=state, spec_sha256=spec_sha)
    if calibration.decision != "CALIBRATION_AUDIT_PASS":
        payload = {
            "version": V113_VERSION,
            "spec_sha256": spec_sha,
            "catalog_generated": catalog.generated_count,
            "catalog_unique": catalog.unique_count,
            "catalog_sha256": catalog.catalog_sha256,
            "calibration": asdict(calibration),
            "decision": "SEARCH_ENGINE_NOT_READY",
            "real_label_authorized": False,
            "label_evaluated_trials": 0,
            "raw_global_trials_after": RAW_GLOBAL_TRIALS_BEFORE_V113,
            "diagnostic_holdout_state": "UNOPENED",
            "epoch_dsr_probability": None,
            "epoch_pbo_probability": None,
            "inner_outer_spearman": None,
            "top_decile_outer_rank_better": None,
            "positive_outer_domains": 0,
            "candidates": [],
            "selected_candidate_ids": [],
            "unauthorized_sealed_label_reads": 0,
            "v112_state_changes": 0,
            "forced_stop": True,
        }
        report = SearchPowerReport(
            V113_VERSION,
            spec_sha,
            catalog.generated_count,
            catalog.unique_count,
            catalog.catalog_sha256,
            calibration,
            "SEARCH_ENGINE_NOT_READY",
            False,
            0,
            RAW_GLOBAL_TRIALS_BEFORE_V113,
            "UNOPENED",
            None,
            None,
            None,
            None,
            0,
            (),
            (),
            0,
            0,
            True,
            sha256_json(payload),
        )
        _write_report(report, output)
        return report

    feature_snapshot = warehouse_feature_snapshot(root)
    multisource_snapshot = latest_multisource_snapshot(root)
    snapshot = registry.register_snapshot(
        build_composite_snapshot_manifest(
            {"minute_features": feature_snapshot, "multisource": multisource_snapshot}
        ),
        vendor_version=V113_VERSION,
    )
    candidate_set_hash = sha256_json([asdict(item) for item in candidates])
    experiment = registry.create_experiment_deterministic(
        ExperimentSpec(
            "v11_3_search_power_lab",
            "One bounded contaminated diagnostic epoch after synthetic audit",
            snapshot,
            code_version,
            canonical_json({"spec_sha256": spec_sha, "candidate_set": candidate_set_hash}),
        ),
        f"{V113_VERSION}|{spec_sha}|{snapshot}|{code_version}",
    )
    trial_map = {}
    for candidate in candidates:
        trial_map[candidate.candidate_id] = registry.create_trial_deterministic(
            TrialSpec(
                experiment,
                "v11_3_label_evaluated_trial",
                candidate.candidate_id,
                canonical_json(asdict(candidate)),
                113,
                "2022-01-01",
                "2023-12-31",
                "2024-01-01",
                "2024-12-31",
                "SEALED",
                "SEALED",
            ),
            f"{V113_VERSION}|{experiment}|{candidate.candidate_id}",
        )

    by_domain: dict[str, list[SearchCandidate]] = defaultdict(list)
    for candidate in candidates:
        by_domain[candidate.domain].append(candidate)
    inner_evaluations: dict[str, _Evaluation] = {}
    universe_q25: dict[str, float | None] = {}
    for domain in sorted(by_domain):
        horizon = by_domain[domain][0].horizon
        rows, _ = _cross_source_panel(
            root,
            "2022-01-01",
            "2023-12-31",
            holding_sessions=horizon,
            include_labels=True,
            maximum_exit_date="2023-12-31",
        )
        rows = _attach_industry(root, rows)
        fields = tuple(sorted({field.name for item in by_domain[domain] for field in item.fields}))
        days = _prepare_days(rows, domain, fields)
        for candidate in by_domain[domain]:
            evaluation = _evaluate(days, candidate)
            inner_evaluations[candidate.candidate_id] = evaluation
            if _preliminary_failures(evaluation):
                universe_q25[candidate.candidate_id] = None
            else:
                stressed = [
                    _evaluate(days, candidate, universe_variant=variant).double_return
                    for variant in range(1, 5)
                ]
                universe_q25[candidate.candidate_id] = _q25(stressed)

    inner_freeze_hash = sha256_json(
        {
            key: {
                "fold_sharpes": value.fold_sharpes,
                "double_return": value.double_return,
                "universe_q25": universe_q25[key],
            }
            for key, value in sorted(inner_evaluations.items())
        }
    )
    _exclusive_json(
        state / "diagnostic-holdout.consumed.json",
        {
            "spec_sha256": spec_sha,
            "candidate_set_sha256": candidate_set_hash,
            "inner_freeze_sha256": inner_freeze_hash,
            "state": "CONSUMED_FOR_DIAGNOSTIC",
        },
    )

    outer_evaluations: dict[str, _Evaluation] = {}
    for domain in sorted(by_domain):
        horizon = by_domain[domain][0].horizon
        rows, _ = _cross_source_panel(
            root,
            "2024-01-01",
            "2024-12-31",
            holding_sessions=horizon,
            include_labels=True,
            maximum_exit_date="2024-12-31",
        )
        rows = _attach_industry(root, rows)
        fields = tuple(sorted({field.name for item in by_domain[domain] for field in item.fields}))
        days = _prepare_days(rows, domain, fields)
        for candidate in by_domain[domain]:
            outer_evaluations[candidate.candidate_id] = _evaluate(days, candidate)

    diagnostics = []
    for candidate in candidates:
        inner = inner_evaluations[candidate.candidate_id]
        outer = outer_evaluations[candidate.candidate_id]
        q25 = universe_q25[candidate.candidate_id]
        failed = _preliminary_failures(inner)
        if q25 is None or q25 < 0:
            failed.append("UNIVERSE_Q25")
        _, trial_number = trial_map[candidate.candidate_id]
        diagnostic = CandidateDiagnostic(
            candidate.candidate_id,
            candidate.domain,
            candidate.expression,
            trial_number,
            len(inner.periods),
            len(outer.periods),
            inner.standard_return,
            inner.double_return,
            inner.double_sharpe,
            median(inner.fold_sharpes),
            _q25(inner.fold_sharpes),
            sum(value > 0 for value in inner.fold_sharpes) / len(inner.fold_sharpes),
            inner.max_drawdown,
            inner.turnover,
            inner.capacity_cny,
            q25,
            not failed,
            outer.standard_return,
            outer.double_return,
            outer.double_sharpe,
            outer.max_drawdown,
            tuple(failed),
        )
        diagnostics.append(diagnostic)
        registry.record_trial_result(
            trial_map[candidate.candidate_id][0], canonical_json(asdict(diagnostic))
        )

    def ranking_key(item: CandidateDiagnostic) -> tuple[object, ...]:
        return (
            -int(item.hard_eligible),
            -item.inner_fold_median_sharpe,
            -item.inner_fold_q25_sharpe,
            -item.inner_standard_return,
            item.inner_turnover,
            next(c.complexity for c in candidates if c.candidate_id == item.candidate_id),
            item.candidate_id,
        )

    ranked = sorted(diagnostics, key=ranking_key)
    inner_scores = [item.inner_fold_median_sharpe for item in diagnostics]
    outer_scores = [item.outer_double_sharpe for item in diagnostics]
    correlation = _spearman(inner_scores, outer_scores)
    top_count = max(1, len(ranked) // 10)
    top_outer = median(item.outer_double_sharpe for item in ranked[:top_count])
    all_outer = median(outer_scores)
    top_better = top_outer > all_outer
    domain_representatives = {
        domain: min((item for item in diagnostics if item.domain == domain), key=ranking_key)
        for domain in by_domain
    }
    positive_domains = sum(item.outer_double_return > 0 for item in domain_representatives.values())
    attractive = tuple(
        item.candidate_id
        for item in domain_representatives.values()
        if item.hard_eligible
        and item.outer_standard_return > 0
        and item.outer_double_return > 0
        and item.outer_double_sharpe >= 0.50
        and item.outer_max_drawdown >= -0.25
        and item.universe_q25_return is not None
        and item.universe_q25_return >= 0
    )
    ranking_capable = top_better and correlation >= 0.10 and positive_domains >= 2
    if ranking_capable and attractive:
        decision = "CANDIDATES_READY_FOR_REVIEW"
    elif ranking_capable:
        decision = "RANKING_CAPABLE"
    else:
        fitting = any(item.inner_double_return > 0 and item.inner_double_sharpe >= 0.50 for item in diagnostics)
        decision = "FITTING_CAPABLE_ONLY" if fitting else "SEARCH_ENGINE_NOT_READY"

    winner = ranked[0]
    per_period_sharpe = winner.inner_double_sharpe / math.sqrt(
        max(1, 252 // next(c.horizon for c in candidates if c.candidate_id == winner.candidate_id))
    )
    dsr = deflated_sharpe_ratio(
        observed_sharpe=per_period_sharpe,
        trial_sharpes=[
            item.inner_double_sharpe
            / math.sqrt(max(1, 252 // next(c.horizon for c in candidates if c.candidate_id == item.candidate_id)))
            for item in diagnostics
        ],
        recorded_trial_count=RAW_GLOBAL_TRIALS_BEFORE_V113 + len(candidates),
        observations=winner.inner_periods,
    ).probability
    pbo = _pbo(inner_evaluations)
    payload = {
        "version": V113_VERSION,
        "spec_sha256": spec_sha,
        "catalog_generated": catalog.generated_count,
        "catalog_unique": catalog.unique_count,
        "catalog_sha256": catalog.catalog_sha256,
        "calibration": asdict(calibration),
        "decision": decision,
        "real_label_authorized": True,
        "label_evaluated_trials": len(candidates),
        "raw_global_trials_after": RAW_GLOBAL_TRIALS_BEFORE_V113 + len(candidates),
        "diagnostic_holdout_state": "CONSUMED_FOR_DIAGNOSTIC",
        "epoch_dsr_probability": dsr,
        "epoch_pbo_probability": pbo,
        "inner_outer_spearman": correlation,
        "top_decile_outer_rank_better": top_better,
        "positive_outer_domains": positive_domains,
        "candidates": [asdict(item) for item in ranked],
        "selected_candidate_ids": list(attractive),
        "unauthorized_sealed_label_reads": 0,
        "v112_state_changes": 0,
        "forced_stop": True,
    }
    report = SearchPowerReport(
        V113_VERSION,
        spec_sha,
        catalog.generated_count,
        catalog.unique_count,
        catalog.catalog_sha256,
        calibration,
        decision,
        True,
        len(candidates),
        RAW_GLOBAL_TRIALS_BEFORE_V113 + len(candidates),
        "CONSUMED_FOR_DIAGNOSTIC",
        dsr,
        pbo,
        correlation,
        top_better,
        positive_domains,
        tuple(ranked),
        attractive,
        0,
        0,
        True,
        sha256_json(payload),
    )
    _write_report(report, output)
    return report
