from __future__ import annotations

import hashlib
import json
import os
import re
from collections import defaultdict
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
from stephen_quant.falsification import PBOResult, probability_of_backtest_overfitting
from stephen_quant.integrity import ExperimentRegistry
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.snapshot import build_selected_files_snapshot_manifest
from stephen_quant.qmt import (
    FUNDAMENTAL_COMPONENTS,
    build_fundamental_factor_observations,
    load_qd_confirmed_fundamentals,
    load_qd_daily_directory,
    read_dynamic_memberships,
    select_qd_daily_files,
)

from .dynamic_cpcv import DynamicCandidate, DynamicCandidateScore, _date_groups, _fit_weights

FUNDAMENTAL_CPCV_VERSION = "qd-dynamic-fundamental-cpcv-1.0.0"
_PARTITION = re.compile(r"^(\d{8})\.csv$", re.IGNORECASE)


@dataclass(frozen=True)
class FundamentalCpcvDesign:
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
    confirmation_sessions: int
    warmup_sessions: int
    minimum_industry_members: int
    winsor_tail: float
    groups: int
    test_groups: int
    embargo_days: int
    purge: str
    candidates: tuple[DynamicCandidate, ...]
    minimum_mean_path_rank_ic: float
    minimum_positive_paths: int
    maximum_pbo: float


@dataclass(frozen=True)
class FundamentalCpcvReport:
    method_version: str
    experiment_id: str
    snapshot_id: str
    combined_source_snapshot_sha256: str
    daily_source_snapshot_sha256: str
    fundamental_source_snapshot_sha256: str
    membership_sha256: str
    candidate_manifest_sha256: str
    cpcv_manifest_sha256: str
    research_start: str
    research_end: str
    membership_sessions: int
    evaluated_dates: int
    common_observations: int
    component_valid_rows: dict[str, int]
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

    def _markdown(self, *, zh: bool) -> str:
        title = (
            "V1.8.15 动态股票池基本面 CPCV 信号门禁"
            if zh
            else "V1.8.15 Dynamic-Universe Fundamental CPCV Signal Gate"
        )
        headers = (
            ("候选", "路径平均 RankIC", "正路径")
            if zh
            else ("Candidate", "Mean path RankIC", "Positive paths")
        )
        lines = [f"# {title}", "", f"**{'结论' if zh else 'Decision'}: {self.decision}**", ""]
        lines += [
            f"- Experiment: `{self.experiment_id}`",
            f"- Snapshot: `{self.snapshot_id}`",
            f"- {'合并数据快照' if zh else 'Combined source snapshot'}: `{self.combined_source_snapshot_sha256}`",
            f"- {'基本面快照' if zh else 'Fundamental snapshot'}: `{self.fundamental_source_snapshot_sha256}`",
            f"- {'研究区间' if zh else 'Research window'}: {self.research_start} to {self.research_end}",
            f"- {'评估日期 / 共同观测' if zh else 'Evaluated dates / common observations'}: {self.evaluated_dates} / {self.common_observations}",
            f"- {'2025 验证期已打开' if zh else '2025 validation opened'}: {'否' if zh else 'no'}",
            f"- {'2026 最终测试已打开' if zh else '2026 final test opened'}: {'否' if zh else 'no'}",
            "",
            f"| Trial | {headers[0]} | {headers[1]} | {headers[2]} |",
            "|---:|---|---:|---:|",
        ]
        lines.extend(
            f"| {item.trial_number} | `{item.candidate_id}` | {item.mean_path_rank_ic:.6f} | {item.positive_paths}/{len(item.path_scores)} |"
            for item in self.configurations
        )
        lines += [
            "",
            f"- {'入选候选' if zh else 'Selected candidate'}: `{self.selected_configuration}`",
            f"- PBO: {self.pbo.probability:.6f}",
            f"- {'完整性通过' if zh else 'Hygiene passed'}: {self.hygiene_passed}",
            f"- {'信号门禁通过' if zh else 'Signal gate passed'}: {self.signal_gate_passed}",
            "",
        ]
        return "\n".join(lines)

    def to_markdown_en(self) -> str:
        return self._markdown(zh=False)

    def to_markdown_zh(self) -> str:
        return self._markdown(zh=True)


@dataclass(frozen=True)
class FundamentalCpcvRun:
    report: FundamentalCpcvReport
    json_path: Path
    markdown_en_path: Path
    markdown_zh_path: Path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, content: str) -> str:
    path.write_text(content, encoding="utf-8", newline="\n")
    return hashlib.sha256(content.encode()).hexdigest()


def _load_design(path: Path) -> FundamentalCpcvDesign:
    payload = json.loads(path.read_text(encoding="utf-8"))
    window, universe, fundamentals = (
        payload["research_window"],
        payload["universe"],
        payload["fundamentals"],
    )
    cpcv, gates = payload["cpcv"], payload["research_gates"]
    candidates = tuple(
        DynamicCandidate(item["candidate_id"], tuple(item["components"]), item["weighting"])
        for item in payload["candidates"]
    )
    result = FundamentalCpcvDesign(
        payload["manifest_version"],
        window["data_start"],
        window["research_start"],
        window["research_end"],
        window["validation_start"],
        window["validation_end"],
        window["test_start"],
        window["test_end"],
        universe["membership_sha256"],
        int(universe["top_n"]),
        int(fundamentals["confirmation_sessions"]),
        int(fundamentals["warmup_sessions"]),
        int(fundamentals["minimum_industry_members"]),
        float(fundamentals["winsor_tail"]),
        int(cpcv["groups"]),
        int(cpcv["test_groups"]),
        int(cpcv["embargo_days"]),
        cpcv["purge"],
        candidates,
        float(gates["minimum_mean_path_rank_ic"]),
        int(gates["minimum_positive_paths"]),
        float(gates["maximum_pbo"]),
    )
    if not (
        result.data_start
        <= result.research_start
        <= result.research_end
        < result.validation_start
        <= result.validation_end
        < result.test_start
        <= result.test_end
    ):
        raise ValueError("candidate manifest date reservations must be strictly ordered")
    components = {component for candidate in candidates for component in candidate.components}
    if components - set(FUNDAMENTAL_COMPONENTS) or len(candidates) < 2:
        raise ValueError("candidate manifest contains unsupported fundamental components")
    if result.purge != "closed_next_open_label_intervals":
        raise ValueError("unsupported purge rule")
    return result


def _fundamental_files(root: Path, start: str, end: str, warmup: int) -> list[Path]:
    partitions = []
    for path in root.iterdir():
        match = _PARTITION.fullmatch(path.name)
        if path.is_file() and match:
            raw = match[1]
            partitions.append((f"{raw[:4]}-{raw[4:6]}-{raw[6:]}", path))
    partitions.sort()
    positions = [index for index, (day, _) in enumerate(partitions) if start <= day <= end]
    if not positions:
        raise ValueError("fundamental window contains no partitions")
    return [path for _, path in partitions[max(positions[0] - warmup, 0) : positions[-1] + 1]]


def _rank_components(observations):
    indexes = {
        component: {(row.execution_at, row.instrument): row for row in rows}
        for component, rows in observations.items()
    }
    common = set.intersection(*(set(indexed) for indexed in indexes.values()))
    anchor_key = min(indexes)
    anchor = {key: indexes[anchor_key][key] for key in common}
    by_date = defaultdict(list)
    for key in common:
        by_date[key[0]].append(key)
    valid_dates = {day for day, keys in by_date.items() if len(keys) >= 3}
    anchor = {key: row for key, row in anchor.items() if key[0] in valid_dates}
    ranked = {component: {} for component in indexes}
    daily_ic = {component: {} for component in indexes}
    for day in sorted(valid_dates):
        keys = sorted(key for key in anchor if key[0] == day)
        returns = [anchor[key].forward_return for key in keys]
        for component, indexed in indexes.items():
            ranks = average_ranks([indexed[key].signal for key in keys])
            scale = max(len(ranks) - 1, 1)
            normalized = [(rank - 1) / scale for rank in ranks]
            for key, value in zip(keys, normalized, strict=True):
                ranked[component][key] = value
            daily_ic[component][day] = spearman_correlation(normalized, returns)
    return ranked, anchor, daily_ic


def run_fundamental_cpcv_research(
    daily_dir,
    fundamental_dir,
    membership_jsonl,
    candidate_manifest,
    *,
    registry: ExperimentRegistry,
    output_dir,
    code_version,
) -> FundamentalCpcvRun:
    daily_root, fundamental_root = Path(daily_dir).resolve(), Path(fundamental_dir).resolve()
    membership_path, candidate_path = (
        Path(membership_jsonl).resolve(),
        Path(candidate_manifest).resolve(),
    )
    design = _load_design(candidate_path)
    membership_sha = _sha(membership_path)
    if membership_sha != design.membership_sha256:
        raise ValueError("membership hash does not match candidate manifest")
    all_memberships = read_dynamic_memberships(membership_path)
    memberships = {
        day: members
        for day, members in all_memberships.items()
        if design.research_start <= day <= design.research_end
    }
    dates = sorted(memberships)
    if dates[0] != design.research_start or dates[-1] != design.research_end:
        raise ValueError("memberships must exactly reach research boundaries")
    union = tuple(sorted({item for members in memberships.values() for item in members}))
    daily_files = select_qd_daily_files(
        daily_root, start_date=design.data_start, end_date=design.research_end
    )
    fundamental_files = _fundamental_files(
        fundamental_root, design.research_start, design.research_end, design.warmup_sessions
    )
    common_root = Path(os.path.commonpath((daily_root, fundamental_root)))
    source_manifest = build_selected_files_snapshot_manifest(
        common_root, (*daily_files, *fundamental_files)
    )
    snapshot_id = registry.register_snapshot(
        source_manifest,
        vendor_version="QD daily + confirmed fundamentals",
        notes="V1.8.15 research only; 2025/2026 sealed",
    )
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            "qd_v1_8_15_fundamental_cpcv",
            "Neutralized value and quality factors have stable positive next-open RankIC.",
            snapshot_id,
            code_version,
            candidate_path.read_text(encoding="utf-8"),
        )
    )
    trials = {
        candidate.candidate_id: registry.create_trial(
            TrialSpec(
                experiment_id,
                "fundamental_cpcv",
                candidate.candidate_id,
                json.dumps(asdict(candidate), sort_keys=True),
                42,
                design.research_start,
                design.research_end,
                design.validation_start,
                design.validation_end,
                design.test_start,
                design.test_end,
            )
        )
        for candidate in design.candidates
    }
    try:
        daily = load_qd_daily_directory(
            daily_root,
            start_date=design.data_start,
            end_date=design.research_end,
            instruments=union,
            adjustment="back_ratio",
        )
        fundamentals = load_qd_confirmed_fundamentals(
            fundamental_root,
            memberships,
            confirmation_sessions=design.confirmation_sessions,
            warmup_sessions=design.warmup_sessions,
        )
        factor_rows, factor_audit = build_fundamental_factor_observations(
            daily.bars,
            fundamentals.observations,
            minimum_industry_members=design.minimum_industry_members,
            winsor_tail=design.winsor_tail,
        )
        bars_by_date = defaultdict(dict)
        for bar in daily.bars:
            bars_by_date[bar.trade_date][bar.instrument] = bar
        result = {component: [] for component in FUNDAMENTAL_COMPONENTS}
        failures = {component: 0 for component in FUNDAMENTAL_COMPONENTS}
        date_position = {day: index for index, day in enumerate(dates)}
        for row in factor_rows:
            index = date_position[row.decision_date]
            if index + 2 >= len(dates):
                continue
            execution, return_end = dates[index + 1], dates[index + 2]
            execution_bar = bars_by_date[execution].get(row.instrument)
            return_bar = bars_by_date[return_end].get(row.instrument)
            for component in FUNDAMENTAL_COMPONENTS:
                if component not in row.components or execution_bar is None or return_bar is None:
                    failures[component] += 1
                    continue
                result[component].append(
                    BaselineObservation(
                        row.instrument,
                        row.components[component],
                        f"{row.decision_date}T15:00:00+08:00",
                        row.available_at,
                        1.0,
                        row.available_at,
                        f"{execution}T09:30:00+08:00",
                        f"{return_end}T09:30:00+08:00",
                        return_bar.open / execution_bar.open - 1,
                        execution_bar.can_buy_open,
                        execution_bar.can_sell_open,
                        execution_bar.tradability_reason,
                    )
                )
        ranked, anchor, daily_ic = _rank_components(result)
        evaluation_dates = sorted({key[0] for key in anchor})
        representative = {}
        for key, row in anchor.items():
            representative.setdefault(key[0], row)
        samples = tuple(
            SampleInterval(
                day,
                "CROSS_SECTION",
                representative[day].signal_available_at,
                representative[day].execution_at,
                representative[day].return_end_at,
            )
            for day in evaluation_dates
        )
        first_trial = trials[design.candidates[0].candidate_id][0]
        manifest = generate_cpcv_manifest(
            samples,
            SplitLineage(snapshot_id, experiment_id, first_trial, code_version),
            n_groups=design.groups,
            n_test_groups=design.test_groups,
            embargo=timedelta(days=design.embargo_days),
        )
        findings = audit_manifest(manifest, samples)
        group_by_date, by_date_keys = (
            _date_groups(evaluation_dates, design.groups),
            defaultdict(list),
        )
        for key in anchor:
            by_date_keys[key[0]].append(key)
        fold_by_id = {fold.fold_id: fold for fold in manifest.folds}
        scores, pbo_inputs = [], {}
        for candidate in design.candidates:
            fold_weights, fold_scores = {}, {}
            for fold in manifest.folds:
                weights = _fit_weights(candidate, fold.train_ids, daily_ic)
                fold_weights[fold.fold_id] = weights
                fold_scores[fold.fold_id] = {
                    day: spearman_correlation(
                        [
                            sum(weights[c] * ranked[c][key] for c in weights)
                            for key in sorted(by_date_keys[day])
                        ],
                        [anchor[key].forward_return for key in sorted(by_date_keys[day])],
                    )
                    for day in fold.test_ids
                }
            path_scores = {}
            for path in manifest.paths:
                values = []
                for segment in path.segments:
                    fold = fold_by_id[segment.fold_id]
                    values += [
                        fold_scores[segment.fold_id][day]
                        for day in fold.test_ids
                        if group_by_date[day] == segment.group_id
                    ]
                path_scores[path.path_id] = sum(values) / len(values)
            trial_id, trial_number = trials[candidate.candidate_id]
            score = DynamicCandidateScore(
                candidate.candidate_id,
                trial_id,
                trial_number,
                sum(path_scores.values()) / len(path_scores),
                sum(value > 0 for value in path_scores.values()),
                path_scores,
                fold_weights,
            )
            scores.append(score)
            pbo_inputs[candidate.candidate_id] = path_scores
        pbo = probability_of_backtest_overfitting(manifest, pbo_inputs, findings)
        winner = max(scores, key=lambda item: (item.mean_path_rank_ic, item.candidate_id))
        hygiene = all(item.passed for item in findings)
        passed = (
            hygiene
            and winner.mean_path_rank_ic >= design.minimum_mean_path_rank_ic
            and winner.positive_paths >= design.minimum_positive_paths
            and pbo.probability <= design.maximum_pbo
        )
        decision = (
            "PASS_SIGNAL_GATE_REQUIRES_EXECUTION_FALSIFICATION" if passed else "REJECT_SIGNAL_GATE"
        )
        report = FundamentalCpcvReport(
            FUNDAMENTAL_CPCV_VERSION,
            experiment_id,
            snapshot_id,
            source_manifest.snapshot_sha256,
            daily.audit.source_sha256,
            fundamentals.audit.source_snapshot_sha256,
            membership_sha,
            _sha(candidate_path),
            manifest.manifest_sha256,
            design.research_start,
            design.research_end,
            len(memberships),
            len(evaluation_dates),
            len(anchor),
            factor_audit.component_valid_rows,
            failures,
            tuple(scores),
            winner.candidate_id,
            pbo,
            hygiene,
            passed,
            False,
            False,
            decision,
        )
        directory = Path(output_dir).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        split = write_split_artifacts(manifest, findings, directory)
        json_path, en_path, zh_path = (
            directory / "fundamental-cpcv.json",
            directory / "fundamental-cpcv.en.md",
            directory / "fundamental-cpcv.zh.md",
        )
        artifacts = [
            ("fundamental_cpcv_json", json_path, _write(json_path, report.to_json() + "\n")),
            ("fundamental_cpcv_markdown_en", en_path, _write(en_path, report.to_markdown_en())),
            ("fundamental_cpcv_markdown_zh", zh_path, _write(zh_path, report.to_markdown_zh())),
            ("cpcv_manifest", split.manifest_path, split.manifest_sha256),
            ("cpcv_audit", split.audit_path, split.audit_sha256),
            ("membership", membership_path, membership_sha),
            ("candidate_manifest", candidate_path, _sha(candidate_path)),
        ]
        for kind, path, digest in artifacts:
            registry.register_artifact(
                trial_id=first_trial, kind=kind, path=str(path), sha256=digest
            )
        for score in scores:
            registry.record_trial_result(
                score.trial_id,
                json.dumps(
                    {
                        "status": "accepted_research_measurement",
                        "family_decision": decision,
                        **asdict(score),
                    },
                    sort_keys=True,
                ),
            )
        return FundamentalCpcvRun(report, json_path, en_path, zh_path)
    except Exception as exc:
        for trial_id, _ in trials.values():
            try:
                registry.record_trial_result(
                    trial_id, json.dumps({"status": "failed_engineering", "error": str(exc)})
                )
            except ValueError:
                pass
        raise
