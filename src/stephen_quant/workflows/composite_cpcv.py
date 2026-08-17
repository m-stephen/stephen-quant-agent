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
from stephen_quant.evaluation import spearman_correlation
from stephen_quant.factors import build_seed_registry
from stephen_quant.falsification import PBOResult, probability_of_backtest_overfitting
from stephen_quant.integrity import ExperimentRegistry
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.snapshot import build_selected_files_snapshot_manifest
from stephen_quant.qmt import (
    build_qmt_factor_observations,
    combine_qmt_factor_observations,
    load_qd_daily_directory,
    select_qd_daily_files,
)

COMPOSITE_CPCV_VERSION = "qd-composite-cpcv-1.0.0"
COMPONENT_IDS = (
    "mom_120_skip_20",
    "trend_efficiency_20",
    "range_position_20",
    "volume_surprise_5_20",
    "parkinson_vol_20",
)


@dataclass(frozen=True)
class CompositeConfiguration:
    configuration_id: str
    components: tuple[str, ...]
    weighting: str
    fixed_weights: tuple[tuple[str, float], ...] = ()


PREDECLARED_CONFIGURATIONS = (
    CompositeConfiguration(
        "volume_control",
        ("volume_surprise_5_20",),
        "fixed",
        (("volume_surprise_5_20", 1.0),),
    ),
    CompositeConfiguration(
        "volume_trend_lowvol_equal",
        ("volume_surprise_5_20", "trend_efficiency_20", "parkinson_vol_20"),
        "fixed",
        (
            ("volume_surprise_5_20", 1 / 3),
            ("trend_efficiency_20", 1 / 3),
            ("parkinson_vol_20", 1 / 3),
        ),
    ),
    CompositeConfiguration(
        "volume_trend_lowvol_train_ic",
        ("volume_surprise_5_20", "trend_efficiency_20", "parkinson_vol_20"),
        "train_positive_rank_ic",
    ),
    CompositeConfiguration(
        "all_five_train_ic",
        COMPONENT_IDS,
        "train_positive_rank_ic",
    ),
)


@dataclass(frozen=True)
class CompositeCpcvConfig:
    data_start: str
    research_start: str
    research_end: str
    validation_start: str
    validation_end: str
    test_start: str
    test_end: str
    instruments: tuple[str, ...]
    adjustment: str = "back_ratio"
    n_groups: int = 6
    n_test_groups: int = 3
    embargo_days: int = 5
    seed: int = 42
    minimum_mean_rank_ic: float = 0.02
    minimum_positive_paths: int = 8
    maximum_pbo: float = 0.20


@dataclass(frozen=True)
class ConfigurationScore:
    configuration_id: str
    trial_id: str
    trial_number: int
    mean_path_rank_ic: float
    positive_paths: int
    path_scores: dict[str, float]
    fold_weights: dict[str, dict[str, float]]


@dataclass(frozen=True)
class CompositeCpcvReport:
    method_version: str
    experiment_id: str
    snapshot_id: str
    manifest_sha256: str
    configurations: tuple[ConfigurationScore, ...]
    selected_configuration: str
    pbo: PBOResult
    hygiene_passed: bool
    decision: str
    validation_window_opened: bool

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self) -> str:
        selected = next(
            item for item in self.configurations
            if item.configuration_id == self.selected_configuration
        )
        lines = [
            "# V1.8.10 composite CPCV research",
            "",
            f"**Decision: {self.decision}**",
            "",
            f"- Experiment: `{self.experiment_id}`",
            f"- Snapshot: `{self.snapshot_id}`",
            f"- CPCV manifest: `{self.manifest_sha256}`",
            f"- Selected configuration: `{self.selected_configuration}`",
            f"- Selected mean path RankIC: {selected.mean_path_rank_ic:.6f}",
            f"- Selected positive paths: {selected.positive_paths}/{len(selected.path_scores)}",
            f"- PBO: {self.pbo.probability:.6f}",
            f"- CPCV hygiene passed: {self.hygiene_passed}",
            f"- 2025 validation opened: {self.validation_window_opened}",
            "",
            "| Trial | Configuration | Mean path RankIC | Positive paths |",
            "|---:|---|---:|---:|",
        ]
        lines.extend(
            f"| {item.trial_number} | `{item.configuration_id}` | "
            f"{item.mean_path_rank_ic:.6f} | {item.positive_paths}/{len(item.path_scores)} |"
            for item in self.configurations
        )
        return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class CompositeCpcvRun:
    report: CompositeCpcvReport
    json_path: Path
    markdown_path: Path


def _sample_id(row: BaselineObservation) -> str:
    return f"{row.execution_at}|{row.instrument}"


def _index(rows: Sequence[BaselineObservation]) -> dict[str, BaselineObservation]:
    return {_sample_id(row): row for row in rows}


def _mean_rank_ic(rows: Sequence[BaselineObservation]) -> float:
    by_date: dict[str, list[BaselineObservation]] = defaultdict(list)
    for row in rows:
        by_date[row.execution_at].append(row)
    values = [
        spearman_correlation(
            [row.signal for row in by_date[day]],
            [row.forward_return for row in by_date[day]],
        )
        for day in sorted(by_date)
    ]
    return sum(values) / len(values)


def _fit_weights(
    configuration: CompositeConfiguration,
    component_rows: Mapping[str, Mapping[str, BaselineObservation]],
    train_ids: Sequence[str],
    directions: Mapping[str, int],
) -> dict[str, float]:
    if configuration.weighting == "fixed":
        return dict(configuration.fixed_weights)
    raw: dict[str, float] = {}
    for component in configuration.components:
        rows = [component_rows[component][sample_id] for sample_id in train_ids]
        directed = [
            BaselineObservation(**{**asdict(row), "signal": directions[component] * row.signal})
            for row in rows
        ]
        raw[component] = max(_mean_rank_ic(directed), 0.0)
    total = sum(raw.values())
    if total == 0:
        return {component: 1 / len(raw) for component in raw}
    return {component: value / total for component, value in raw.items()}


def _date_groups(rows: Sequence[BaselineObservation], n_groups: int) -> dict[str, int]:
    dates = sorted({row.execution_at for row in rows})
    size, remainder = divmod(len(dates), n_groups)
    result: dict[str, int] = {}
    offset = 0
    for group_id in range(n_groups):
        width = size + (1 if group_id < remainder else 0)
        for day in dates[offset : offset + width]:
            result[day] = group_id
        offset += width
    return result


def _write(path: Path, content: str) -> str:
    path.write_text(content, encoding="utf-8", newline="\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def run_composite_cpcv_research(
    daily_dir: str | Path,
    *,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    config: CompositeCpcvConfig,
    code_version: str,
) -> CompositeCpcvRun:
    """Run the predeclared exploratory family without loading the fresh validation window."""

    if not (
        config.data_start <= config.research_start <= config.research_end
        < config.validation_start <= config.validation_end
        < config.test_start <= config.test_end
    ):
        raise ValueError("research, validation, and test date reservations must be ordered")
    if config.embargo_days < 0:
        raise ValueError("embargo_days cannot be negative")

    root = Path(daily_dir).expanduser().resolve()
    selected_files = select_qd_daily_files(
        root,
        start_date=config.data_start,
        end_date=config.research_end,
        include_next_after_end=True,
    )
    snapshot = build_selected_files_snapshot_manifest(root, selected_files)
    snapshot_id = registry.register_snapshot(
        snapshot,
        vendor_version="QD date-partitioned A-share daily CSV / raw",
        notes="V1.8.10 exploratory research data only; 2025 validation remains unopened.",
    )
    search_space = json.dumps(
        [asdict(item) for item in PREDECLARED_CONFIGURATIONS],
        separators=(",", ":"),
        sort_keys=True,
    )
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            name="qd_v1_8_10_composite_cpcv",
            hypothesis=(
                "A fold-local combination of volume surprise, trend, momentum, range position, "
                "and low range volatility has stable positive training CPCV RankIC."
            ),
            dataset_snapshot_id=snapshot_id,
            code_version=code_version,
            search_space=search_space,
        )
    )
    trials: dict[str, tuple[str, int]] = {}
    for candidate in PREDECLARED_CONFIGURATIONS:
        trials[candidate.configuration_id] = registry.create_trial(
            TrialSpec(
                experiment_id=experiment_id,
                model_name="fold_local_rank_composite",
                factor_set=candidate.configuration_id,
                hyperparams=json.dumps(asdict(candidate), separators=(",", ":"), sort_keys=True),
                seed=config.seed,
                train_start=config.research_start,
                train_end=config.research_end,
                validation_start=config.validation_start,
                validation_end=config.validation_end,
                test_start=config.test_start,
                test_end=config.test_end,
            )
        )

    dataset = load_qd_daily_directory(
        root,
        start_date=config.data_start,
        end_date=config.research_end,
        instruments=config.instruments,
        adjustment=config.adjustment,
        include_next_after_end=True,
    )
    definitions = {item: build_seed_registry().get(item) for item in COMPONENT_IDS}
    directions = {item: definitions[item].direction for item in COMPONENT_IDS}
    component_observations = {
        item: build_qmt_factor_observations(
            dataset.bars,
            definitions[item],
            test_start=config.research_start,
            test_end=config.research_end,
        )
        for item in COMPONENT_IDS
    }
    component_rows = {name: _index(rows) for name, rows in component_observations.items()}
    anchor = component_observations[COMPONENT_IDS[0]]
    samples = tuple(
        SampleInterval(
            sample_id=_sample_id(row),
            instrument=row.instrument,
            feature_at=row.signal_available_at,
            label_start_at=row.execution_at,
            label_end_at=row.return_end_at,
        )
        for row in anchor
    )
    first_trial_id = trials[PREDECLARED_CONFIGURATIONS[0].configuration_id][0]
    manifest = generate_cpcv_manifest(
        samples,
        SplitLineage(snapshot_id, experiment_id, first_trial_id, code_version),
        n_groups=config.n_groups,
        n_test_groups=config.n_test_groups,
        embargo=timedelta(days=config.embargo_days),
    )
    findings = audit_manifest(manifest, samples)
    fold_by_id = {fold.fold_id: fold for fold in manifest.folds}
    group_by_date = _date_groups(anchor, config.n_groups)

    configuration_scores: list[ConfigurationScore] = []
    pbo_inputs: dict[str, dict[str, float]] = {}
    for candidate in PREDECLARED_CONFIGURATIONS:
        fold_weights: dict[str, dict[str, float]] = {}
        fold_predictions: dict[str, dict[str, BaselineObservation]] = {}
        for fold in manifest.folds:
            weights = _fit_weights(
                candidate, component_rows, fold.train_ids, directions
            )
            fold_weights[fold.fold_id] = weights
            test_components = {
                component: [component_rows[component][sample_id] for sample_id in fold.test_ids]
                for component in candidate.components
            }
            combined = combine_qmt_factor_observations(
                test_components,
                weights,
                {component: directions[component] for component in candidate.components},
            )
            fold_predictions[fold.fold_id] = _index(combined)

        path_scores: dict[str, float] = {}
        for path in manifest.paths:
            path_rows: list[BaselineObservation] = []
            for segment in path.segments:
                fold = fold_by_id[segment.fold_id]
                path_rows.extend(
                    fold_predictions[segment.fold_id][sample_id]
                    for sample_id in fold.test_ids
                    if group_by_date[component_rows[COMPONENT_IDS[0]][sample_id].execution_at]
                    == segment.group_id
                )
            path_scores[path.path_id] = _mean_rank_ic(path_rows)
        trial_id, trial_number = trials[candidate.configuration_id]
        score = ConfigurationScore(
            configuration_id=candidate.configuration_id,
            trial_id=trial_id,
            trial_number=trial_number,
            mean_path_rank_ic=sum(path_scores.values()) / len(path_scores),
            positive_paths=sum(value > 0 for value in path_scores.values()),
            path_scores=path_scores,
            fold_weights=fold_weights,
        )
        configuration_scores.append(score)
        pbo_inputs[candidate.configuration_id] = path_scores

    pbo = probability_of_backtest_overfitting(manifest, pbo_inputs, findings)
    winner = max(
        configuration_scores,
        key=lambda item: (item.mean_path_rank_ic, item.configuration_id),
    )
    passed = (
        all(finding.passed for finding in findings)
        and winner.mean_path_rank_ic >= config.minimum_mean_rank_ic
        and winner.positive_paths >= config.minimum_positive_paths
        and pbo.probability <= config.maximum_pbo
    )
    report = CompositeCpcvReport(
        method_version=COMPOSITE_CPCV_VERSION,
        experiment_id=experiment_id,
        snapshot_id=snapshot_id,
        manifest_sha256=manifest.manifest_sha256,
        configurations=tuple(configuration_scores),
        selected_configuration=winner.configuration_id,
        pbo=pbo,
        hygiene_passed=all(finding.passed for finding in findings),
        decision="PASS_RESEARCH" if passed else "REJECT",
        validation_window_opened=False,
    )
    directory = Path(output_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    split_artifacts = write_split_artifacts(manifest, findings, directory)
    json_path = directory / "composite-cpcv.json"
    markdown_path = directory / "composite-cpcv.md"
    json_sha = _write(json_path, report.to_json() + "\n")
    markdown_sha = _write(markdown_path, report.to_markdown())
    data_audit_path = directory / "qd-data-audit.json"
    data_audit_sha = _write(data_audit_path, dataset.audit.to_json() + "\n")
    for score in configuration_scores:
        registry.record_trial_result(
            score.trial_id,
            json.dumps(
                {
                    "status": "accepted",
                    "family_decision": report.decision,
                    "selected": score.configuration_id == report.selected_configuration,
                    **asdict(score),
                },
                separators=(",", ":"),
                sort_keys=True,
            ),
        )
    for kind, path, digest in (
        ("composite_cpcv_json", json_path, json_sha),
        ("composite_cpcv_markdown", markdown_path, markdown_sha),
        ("cpcv_manifest", split_artifacts.manifest_path, split_artifacts.manifest_sha256),
        ("cpcv_audit", split_artifacts.audit_path, split_artifacts.audit_sha256),
        ("qd_data_audit", data_audit_path, data_audit_sha),
    ):
        registry.register_artifact(
            trial_id=first_trial_id,
            kind=kind,
            path=str(path),
            sha256=digest,
        )
    return CompositeCpcvRun(report, json_path, markdown_path)
