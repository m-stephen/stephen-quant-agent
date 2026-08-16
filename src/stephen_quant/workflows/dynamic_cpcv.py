from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path

from stephen_quant.baseline import BaselineObservation
from stephen_quant.cross_validation import (
    SampleInterval,
    SplitLineage,
    audit_manifest,
    generate_cpcv_manifest,
    write_split_artifacts,
)
from stephen_quant.evaluation import average_ranks, spearman_correlation
from stephen_quant.factors import FactorDefinition, FactorError, build_seed_registry, compute_factor
from stephen_quant.falsification import PBOResult, probability_of_backtest_overfitting
from stephen_quant.integrity import ExperimentRegistry
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.snapshot import build_selected_files_snapshot_manifest
from stephen_quant.qmt import load_qd_daily_directory, select_qd_daily_files

DYNAMIC_CPCV_VERSION = "qd-dynamic-microstructure-cpcv-1.0.0"


@dataclass(frozen=True)
class DynamicCandidate:
    candidate_id: str
    components: tuple[str, ...]
    weighting: str


@dataclass(frozen=True)
class DynamicCpcvDesign:
    manifest_version: str
    data_start: str
    research_start: str
    research_end: str
    validation_start: str
    validation_end: str
    test_start: str
    test_end: str
    membership_sha256: str
    top_n: int
    groups: int
    test_groups: int
    embargo_days: int
    purge: str
    candidates: tuple[DynamicCandidate, ...]
    minimum_mean_path_rank_ic: float
    minimum_positive_paths: int
    maximum_pbo: float
    minimum_dsr_probability: float
    maximum_placebo_p_value: float


@dataclass(frozen=True)
class DynamicCandidateScore:
    candidate_id: str
    trial_id: str
    trial_number: int
    mean_path_rank_ic: float
    positive_paths: int
    path_scores: dict[str, float]
    fold_weights: dict[str, dict[str, float]]


@dataclass(frozen=True)
class DynamicCpcvReport:
    method_version: str
    experiment_id: str
    snapshot_id: str
    source_snapshot_sha256: str
    membership_sha256: str
    candidate_manifest_sha256: str
    cpcv_manifest_sha256: str
    research_start: str
    research_end: str
    membership_sessions: int
    evaluated_dates: int
    common_observations: int
    component_failures: dict[str, int]
    configurations: tuple[DynamicCandidateScore, ...]
    selected_configuration: str
    pbo: PBOResult
    hygiene_passed: bool
    signal_gate_passed: bool
    execution_falsification_run: bool
    validation_window_opened: bool
    decision: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self) -> str:
        selected = next(
            item for item in self.configurations
            if item.candidate_id == self.selected_configuration
        )
        lines = [
            "# V1.8.14 Dynamic-Universe CPCV Signal Gate",
            "",
            f"**Decision: {self.decision}**",
            "",
            "## Lineage and scope",
            "",
            f"- Experiment: `{self.experiment_id}`",
            f"- Snapshot: `{self.snapshot_id}`",
            f"- Source snapshot SHA-256: `{self.source_snapshot_sha256}`",
            f"- Membership SHA-256: `{self.membership_sha256}`",
            f"- Candidate manifest SHA-256: `{self.candidate_manifest_sha256}`",
            f"- CPCV manifest SHA-256: `{self.cpcv_manifest_sha256}`",
            f"- Research window: {self.research_start} through {self.research_end}",
            (
                f"- Evaluated dates / observations: {self.evaluated_dates} / "
                f"{self.common_observations}"
            ),
            "- 2025 validation opened: no",
            "- 2026 final test opened: no",
            "",
            "## Candidate results",
            "",
            "| Trial | Candidate | Mean path RankIC | Positive paths |",
            "|---:|---|---:|---:|",
        ]
        lines.extend(
            f"| {item.trial_number} | `{item.candidate_id}` | "
            f"{item.mean_path_rank_ic:.6f} | {item.positive_paths}/{len(item.path_scores)} |"
            for item in self.configurations
        )
        lines.extend(
            [
                "",
                "## Gate evaluation",
                "",
                f"- Selected candidate: `{selected.candidate_id}`",
                f"- Selected mean path RankIC: {selected.mean_path_rank_ic:.6f}",
                f"- Selected positive paths: {selected.positive_paths}/{len(selected.path_scores)}",
                f"- PBO: {self.pbo.probability:.6f}",
                f"- CPCV hygiene passed: {self.hygiene_passed}",
                f"- Signal gate passed: {self.signal_gate_passed}",
                "- Cost-aware DSR and placebo gate: not run unless the signal gate passes",
                "",
                (
                    "This stage cannot authorize validation by itself. A passing signal gate "
                    "only authorizes in-research-window execution falsification."
                ),
                "",
            ]
        )
        return "\n".join(lines)

    def to_markdown_zh(self) -> str:
        selected = next(
            item for item in self.configurations
            if item.candidate_id == self.selected_configuration
        )
        lines = [
            "# V1.8.14 动态股票池 CPCV 信号门禁",
            "",
            f"**结论：{self.decision}**",
            "",
            "## 血缘与范围",
            "",
            f"- Experiment：`{self.experiment_id}`",
            f"- Snapshot：`{self.snapshot_id}`",
            f"- 数据快照 SHA-256：`{self.source_snapshot_sha256}`",
            f"- 股票池 SHA-256：`{self.membership_sha256}`",
            f"- 候选清单 SHA-256：`{self.candidate_manifest_sha256}`",
            f"- CPCV 清单 SHA-256：`{self.cpcv_manifest_sha256}`",
            f"- 研究区间：{self.research_start} 至 {self.research_end}",
            f"- 评估日期 / 共同观测：{self.evaluated_dates} / {self.common_observations}",
            "- 是否打开 2025 验证期：否",
            "- 是否打开 2026 最终测试期：否",
            "",
            "## 候选结果",
            "",
            "| Trial | 候选 | 路径平均 RankIC | 正 RankIC 路径 |",
            "|---:|---|---:|---:|",
        ]
        lines.extend(
            f"| {item.trial_number} | `{item.candidate_id}` | "
            f"{item.mean_path_rank_ic:.6f} | {item.positive_paths}/{len(item.path_scores)} |"
            for item in self.configurations
        )
        lines.extend(
            [
                "",
                "## 门禁判断",
                "",
                f"- 入选候选：`{selected.candidate_id}`",
                f"- 入选路径平均 RankIC：{selected.mean_path_rank_ic:.6f}",
                f"- 入选正路径：{selected.positive_paths}/{len(selected.path_scores)}",
                f"- PBO：{self.pbo.probability:.6f}",
                f"- CPCV 完整性通过：{self.hygiene_passed}",
                f"- 信号门禁通过：{self.signal_gate_passed}",
                "- 含成本 DSR 与安慰剂门禁：只有信号门禁通过后才运行",
                "",
                "本阶段不能直接授权验证。信号门禁通过，只能授权在研究期内继续执行证伪。",
                "",
            ]
        )
        return "\n".join(lines)


@dataclass(frozen=True)
class DynamicCpcvRun:
    report: DynamicCpcvReport
    json_path: Path
    markdown_en_path: Path
    markdown_zh_path: Path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, content: str) -> str:
    path.write_text(content, encoding="utf-8", newline="\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _load_design(path: Path) -> DynamicCpcvDesign:
    payload = json.loads(path.read_text(encoding="utf-8"))
    window = payload["research_window"]
    universe = payload["universe"]
    cpcv = payload["cpcv"]
    gates = payload["research_gates"]
    candidates = tuple(
        DynamicCandidate(
            candidate_id=item["candidate_id"],
            components=tuple(item["components"]),
            weighting=item["weighting"],
        )
        for item in payload["candidates"]
    )
    design = DynamicCpcvDesign(
        manifest_version=payload["manifest_version"],
        data_start=window["data_start"],
        research_start=window["research_start"],
        research_end=window["research_end"],
        validation_start=window["validation_start"],
        validation_end=window["validation_end"],
        test_start=window["test_start"],
        test_end=window["test_end"],
        membership_sha256=universe["membership_sha256"],
        top_n=int(universe["top_n"]),
        groups=int(cpcv["groups"]),
        test_groups=int(cpcv["test_groups"]),
        embargo_days=int(cpcv["embargo_days"]),
        purge=cpcv["purge"],
        candidates=candidates,
        minimum_mean_path_rank_ic=float(gates["minimum_mean_path_rank_ic"]),
        minimum_positive_paths=int(gates["minimum_positive_paths"]),
        maximum_pbo=float(gates["maximum_pbo"]),
        minimum_dsr_probability=float(gates["minimum_dsr_probability"]),
        maximum_placebo_p_value=float(gates["maximum_placebo_p_value"]),
    )
    if not (
        design.data_start <= design.research_start <= design.research_end
        < design.validation_start <= design.validation_end
        < design.test_start <= design.test_end
    ):
        raise ValueError("candidate manifest date reservations must be strictly ordered")
    if design.purge != "closed_next_open_label_intervals":
        raise ValueError("unsupported candidate-manifest purge rule")
    if len(candidates) < 2 or len({item.candidate_id for item in candidates}) != len(candidates):
        raise ValueError("candidate manifest requires unique multiple candidates")
    return design


def _read_memberships(path: Path, design: DynamicCpcvDesign) -> list[dict[str, object]]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    selected = [
        row
        for row in rows
        if design.research_start <= str(row["decision_date"]) <= design.research_end
    ]
    dates = [str(row["decision_date"]) for row in selected]
    if (
        len(selected) < 3
        or dates != sorted(dates)
        or len(set(dates)) != len(dates)
        or dates[0] != design.research_start
        or dates[-1] != design.research_end
    ):
        raise ValueError("membership JSONL must exactly cover unique chronological research dates")
    if any(len(row["members"]) > design.top_n for row in selected):
        raise ValueError("membership row exceeds the predeclared top_n")
    return selected


def _factor_id(key: str) -> tuple[str, str]:
    factor_id, separator, version = key.partition("@")
    if not separator or not factor_id or not version:
        raise ValueError(f"invalid versioned factor key: {key}")
    return factor_id, version


def _component_observations(
    bars: Sequence[object],
    memberships: Sequence[dict[str, object]],
    definitions: Mapping[str, FactorDefinition],
    *,
    adv_lookback: int = 20,
) -> tuple[dict[str, tuple[BaselineObservation, ...]], dict[str, int]]:
    by_instrument: dict[str, list[object]] = defaultdict(list)
    bars_by_date: dict[str, dict[str, object]] = defaultdict(dict)
    for bar in bars:
        by_instrument[bar.instrument].append(bar)
        bars_by_date[bar.trade_date][bar.instrument] = bar
    indexes = {
        instrument: {bar.trade_date: index for index, bar in enumerate(rows)}
        for instrument, rows in by_instrument.items()
    }
    required_fields = sorted(
        {field for definition in definitions.values() for field in definition.required_fields}
    )
    factor_data = {
        instrument: {
            field: [getattr(bar, field) for bar in rows] for field in required_fields
        }
        for instrument, rows in by_instrument.items()
    }
    availability: dict[str, dict[str, list[str]]] = {}
    for instrument, rows in by_instrument.items():
        timestamps = [f"{bar.trade_date}T15:01:00+08:00" for bar in rows]
        availability[instrument] = {field: timestamps for field in required_fields}
    observation_times = {
        instrument: [f"{bar.trade_date}T15:00:00+08:00" for bar in rows]
        for instrument, rows in by_instrument.items()
    }
    result: dict[str, list[BaselineObservation]] = {key: [] for key in definitions}
    failures = {key: 0 for key in definitions}
    for index in range(len(memberships) - 2):
        decision_date = str(memberships[index]["decision_date"])
        execution_date = str(memberships[index + 1]["decision_date"])
        return_end_date = str(memberships[index + 2]["decision_date"])
        for instrument in sorted(str(item) for item in memberships[index]["members"]):
            rows = by_instrument.get(instrument)
            as_of_index = indexes.get(instrument, {}).get(decision_date)
            execution_bar = bars_by_date.get(execution_date, {}).get(instrument)
            return_end_bar = bars_by_date.get(return_end_date, {}).get(instrument)
            execution_index = indexes.get(instrument, {}).get(execution_date)
            if (
                rows is None
                or as_of_index is None
                or execution_bar is None
                or return_end_bar is None
                or execution_index is None
                or execution_index < adv_lookback
            ):
                for key in failures:
                    failures[key] += 1
                continue
            history = rows[execution_index - adv_lookback : execution_index]
            average_daily_value = sum(item.amount for item in history) / len(history)
            if average_daily_value <= 0:
                for key in failures:
                    failures[key] += 1
                continue
            for key, definition in definitions.items():
                try:
                    signal = compute_factor(
                        definition,
                        factor_data[instrument],
                        availability[instrument],
                        as_of_index=as_of_index,
                        observation_times=observation_times[instrument],
                        decision_at=f"{execution_date}T09:30:00+08:00",
                    )
                except FactorError:
                    failures[key] += 1
                    continue
                result[key].append(
                    BaselineObservation(
                        instrument=instrument,
                        signal=signal.value,
                        signal_at=f"{decision_date}T15:00:00+08:00",
                        signal_available_at=f"{decision_date}T15:01:00+08:00",
                        average_daily_value=average_daily_value,
                        liquidity_available_at=f"{decision_date}T15:01:00+08:00",
                        execution_at=f"{execution_date}T09:30:00+08:00",
                        return_end_at=f"{return_end_date}T09:30:00+08:00",
                        forward_return=return_end_bar.open / execution_bar.open - 1.0,
                        can_buy_open=execution_bar.can_buy_open,
                        can_sell_open=execution_bar.can_sell_open,
                        tradability_reason=execution_bar.tradability_reason,
                    )
                )
    return {key: tuple(rows) for key, rows in result.items()}, failures


def _date_groups(dates: Sequence[str], n_groups: int) -> dict[str, int]:
    size, remainder = divmod(len(dates), n_groups)
    result: dict[str, int] = {}
    offset = 0
    for group_id in range(n_groups):
        width = size + (1 if group_id < remainder else 0)
        for day in dates[offset : offset + width]:
            result[day] = group_id
        offset += width
    return result


def _rank_components(
    observations: Mapping[str, Sequence[BaselineObservation]],
    definitions: Mapping[str, FactorDefinition],
) -> tuple[
    dict[str, dict[tuple[str, str], float]],
    dict[tuple[str, str], BaselineObservation],
    dict[str, dict[str, float]],
]:
    indexes = {
        key: {(row.execution_at, row.instrument): row for row in rows}
        for key, rows in observations.items()
    }
    common = set.intersection(*(set(indexed) for indexed in indexes.values()))
    anchor_key = min(indexes)
    anchor = {key: indexes[anchor_key][key] for key in common}
    by_date: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for key in common:
        by_date[key[0]].append(key)
    valid_dates = {
        day for day, keys in by_date.items() if len(keys) >= 3
    }
    anchor = {key: row for key, row in anchor.items() if key[0] in valid_dates}
    ranked: dict[str, dict[tuple[str, str], float]] = {key: {} for key in indexes}
    daily_ic: dict[str, dict[str, float]] = {key: {} for key in indexes}
    for day in sorted(valid_dates):
        keys = sorted(key for key in anchor if key[0] == day)
        returns = [anchor[key].forward_return for key in keys]
        for component, indexed in indexes.items():
            values = [definitions[component].direction * indexed[key].signal for key in keys]
            ranks = average_ranks(values)
            scale = max(len(ranks) - 1, 1)
            normalized = [(rank - 1) / scale for rank in ranks]
            for key, value in zip(keys, normalized, strict=True):
                ranked[component][key] = value
            daily_ic[component][day] = spearman_correlation(normalized, returns)
    return ranked, anchor, daily_ic


def _fit_weights(
    candidate: DynamicCandidate,
    train_dates: Sequence[str],
    daily_component_ic: Mapping[str, Mapping[str, float]],
) -> dict[str, float]:
    if candidate.weighting == "single":
        if len(candidate.components) != 1:
            raise ValueError("single weighting requires exactly one component")
        return {candidate.components[0]: 1.0}
    if candidate.weighting == "equal_rank":
        return {component: 1 / len(candidate.components) for component in candidate.components}
    if candidate.weighting != "fold_local_positive_rank_ic":
        raise ValueError(f"unsupported candidate weighting: {candidate.weighting}")
    raw = {
        component: max(
            sum(daily_component_ic[component][day] for day in train_dates) / len(train_dates),
            0.0,
        )
        for component in candidate.components
    }
    total = sum(raw.values())
    if total == 0:
        return {component: 1 / len(raw) for component in raw}
    return {component: value / total for component, value in raw.items()}


def run_dynamic_cpcv_research(
    daily_dir: str | Path,
    membership_jsonl: str | Path,
    candidate_manifest: str | Path,
    *,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
) -> DynamicCpcvRun:
    root = Path(daily_dir).expanduser().resolve()
    membership_path = Path(membership_jsonl).expanduser().resolve()
    candidate_path = Path(candidate_manifest).expanduser().resolve()
    design = _load_design(candidate_path)
    membership_sha = _sha256(membership_path)
    if membership_sha != design.membership_sha256:
        raise ValueError("dynamic membership hash does not match the frozen candidate manifest")
    memberships = _read_memberships(membership_path, design)
    union = tuple(sorted({str(item) for row in memberships for item in row["members"]}))
    files = select_qd_daily_files(
        root, start_date=design.data_start, end_date=design.research_end
    )
    source_manifest = build_selected_files_snapshot_manifest(root, files)
    snapshot_id = registry.register_snapshot(
        source_manifest,
        vendor_version="QD date-partitioned A-share daily CSV / back_ratio",
        notes="V1.8.14 research files only; 2025 validation and 2026 test remain sealed.",
    )
    candidate_sha = _sha256(candidate_path)
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            name="qd_v1_8_14_dynamic_microstructure_cpcv",
            hypothesis=(
                "Opening-gap reversal and close-location pressure have stable positive "
                "cross-sectional next-open RankIC on the point-in-time dynamic universe."
            ),
            dataset_snapshot_id=snapshot_id,
            code_version=code_version,
            search_space=candidate_path.read_text(encoding="utf-8"),
        )
    )
    trials = {
        candidate.candidate_id: registry.create_trial(
            TrialSpec(
                experiment_id=experiment_id,
                model_name="dynamic_microstructure_cpcv",
                factor_set=candidate.candidate_id,
                hyperparams=json.dumps(asdict(candidate), separators=(",", ":"), sort_keys=True),
                seed=42,
                train_start=design.research_start,
                train_end=design.research_end,
                validation_start=design.validation_start,
                validation_end=design.validation_end,
                test_start=design.test_start,
                test_end=design.test_end,
            )
        )
        for candidate in design.candidates
    }
    try:
        registry_factors = build_seed_registry()
        component_keys = sorted(
            {component for candidate in design.candidates for component in candidate.components}
        )
        definitions = {
            key: registry_factors.get(*_factor_id(key)) for key in component_keys
        }
        dataset = load_qd_daily_directory(
            root,
            start_date=design.data_start,
            end_date=design.research_end,
            instruments=union,
            adjustment="back_ratio",
        )
        observations, failures = _component_observations(
            dataset.bars, memberships, definitions
        )
        ranked, anchor, component_daily_ic = _rank_components(observations, definitions)
        dates = sorted({key[0] for key in anchor})
        representative: dict[str, BaselineObservation] = {}
        for key, row in anchor.items():
            representative.setdefault(key[0], row)
        samples = tuple(
            SampleInterval(
                sample_id=day,
                instrument="CROSS_SECTION",
                feature_at=representative[day].signal_available_at,
                label_start_at=representative[day].execution_at,
                label_end_at=representative[day].return_end_at,
            )
            for day in dates
        )
        first_trial_id = trials[design.candidates[0].candidate_id][0]
        manifest = generate_cpcv_manifest(
            samples,
            SplitLineage(snapshot_id, experiment_id, first_trial_id, code_version),
            n_groups=design.groups,
            n_test_groups=design.test_groups,
            embargo=timedelta(days=design.embargo_days),
        )
        findings = audit_manifest(manifest, samples)
        group_by_date = _date_groups(dates, design.groups)
        by_date_keys: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for key in anchor:
            by_date_keys[key[0]].append(key)
        scores: list[DynamicCandidateScore] = []
        pbo_inputs: dict[str, dict[str, float]] = {}
        fold_by_id = {fold.fold_id: fold for fold in manifest.folds}
        for candidate in design.candidates:
            fold_weights: dict[str, dict[str, float]] = {}
            fold_daily_scores: dict[str, dict[str, float]] = {}
            for fold in manifest.folds:
                weights = _fit_weights(candidate, fold.train_ids, component_daily_ic)
                fold_weights[fold.fold_id] = weights
                daily_scores: dict[str, float] = {}
                for day in fold.test_ids:
                    keys = sorted(by_date_keys[day])
                    composite = [
                        sum(weights[component] * ranked[component][key] for component in weights)
                        for key in keys
                    ]
                    returns = [anchor[key].forward_return for key in keys]
                    daily_scores[day] = spearman_correlation(composite, returns)
                fold_daily_scores[fold.fold_id] = daily_scores
            path_scores: dict[str, float] = {}
            for path in manifest.paths:
                values: list[float] = []
                for segment in path.segments:
                    fold = fold_by_id[segment.fold_id]
                    values.extend(
                        fold_daily_scores[segment.fold_id][day]
                        for day in fold.test_ids
                        if group_by_date[day] == segment.group_id
                    )
                path_scores[path.path_id] = sum(values) / len(values)
            trial_id, trial_number = trials[candidate.candidate_id]
            score = DynamicCandidateScore(
                candidate_id=candidate.candidate_id,
                trial_id=trial_id,
                trial_number=trial_number,
                mean_path_rank_ic=sum(path_scores.values()) / len(path_scores),
                positive_paths=sum(value > 0 for value in path_scores.values()),
                path_scores=path_scores,
                fold_weights=fold_weights,
            )
            scores.append(score)
            pbo_inputs[candidate.candidate_id] = path_scores
        pbo = probability_of_backtest_overfitting(manifest, pbo_inputs, findings)
        winner = max(scores, key=lambda item: (item.mean_path_rank_ic, item.candidate_id))
        hygiene = all(item.passed for item in findings)
        signal_passed = (
            hygiene
            and winner.mean_path_rank_ic >= design.minimum_mean_path_rank_ic
            and winner.positive_paths >= design.minimum_positive_paths
            and pbo.probability <= design.maximum_pbo
        )
        decision = (
            "PASS_SIGNAL_GATE_REQUIRES_EXECUTION_FALSIFICATION"
            if signal_passed
            else "REJECT_SIGNAL_GATE"
        )
        report = DynamicCpcvReport(
            method_version=DYNAMIC_CPCV_VERSION,
            experiment_id=experiment_id,
            snapshot_id=snapshot_id,
            source_snapshot_sha256=source_manifest.snapshot_sha256,
            membership_sha256=membership_sha,
            candidate_manifest_sha256=candidate_sha,
            cpcv_manifest_sha256=manifest.manifest_sha256,
            research_start=design.research_start,
            research_end=design.research_end,
            membership_sessions=len(memberships),
            evaluated_dates=len(dates),
            common_observations=len(anchor),
            component_failures=failures,
            configurations=tuple(scores),
            selected_configuration=winner.candidate_id,
            pbo=pbo,
            hygiene_passed=hygiene,
            signal_gate_passed=signal_passed,
            execution_falsification_run=False,
            validation_window_opened=False,
            decision=decision,
        )
        directory = Path(output_dir).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
        split_artifacts = write_split_artifacts(manifest, findings, directory)
        json_path = directory / "dynamic-cpcv.json"
        markdown_en_path = directory / "dynamic-cpcv.en.md"
        markdown_zh_path = directory / "dynamic-cpcv.zh.md"
        data_audit_path = directory / "qd-data-audit.json"
        json_sha = _write(json_path, report.to_json() + "\n")
        markdown_en_sha = _write(markdown_en_path, report.to_markdown())
        markdown_zh_sha = _write(markdown_zh_path, report.to_markdown_zh())
        data_audit_sha = _write(data_audit_path, dataset.audit.to_json() + "\n")
        for score in scores:
            registry.record_trial_result(
                score.trial_id,
                json.dumps(
                    {
                        "status": "accepted_research_measurement",
                        "family_decision": decision,
                        "selected": score.candidate_id == winner.candidate_id,
                        **asdict(score),
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            )
        for kind, path, digest in (
            ("dynamic_cpcv_json", json_path, json_sha),
            ("dynamic_cpcv_markdown_en", markdown_en_path, markdown_en_sha),
            ("dynamic_cpcv_markdown_zh", markdown_zh_path, markdown_zh_sha),
            ("cpcv_manifest", split_artifacts.manifest_path, split_artifacts.manifest_sha256),
            ("cpcv_audit", split_artifacts.audit_path, split_artifacts.audit_sha256),
            ("qd_data_audit", data_audit_path, data_audit_sha),
            ("dynamic_membership_jsonl", membership_path, membership_sha),
            ("candidate_manifest", candidate_path, candidate_sha),
        ):
            registry.register_artifact(
                trial_id=first_trial_id, kind=kind, path=str(path), sha256=digest
            )
        return DynamicCpcvRun(report, json_path, markdown_en_path, markdown_zh_path)
    except Exception as exc:
        for trial_id, _ in trials.values():
            registry.record_trial_result(
                trial_id,
                json.dumps(
                    {"status": "failed_engineering", "error": str(exc)},
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            )
        raise
