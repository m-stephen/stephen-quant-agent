from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from stephen_quant.baseline import (
    BaselineConfig,
    BaselineLineage,
    BaselineReport,
    run_momentum_topk,
    write_baseline_report,
)
from stephen_quant.factors import build_seed_registry
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_file_snapshot_manifest
from stephen_quant.qmt import build_qmt_factor_observations, load_qmt_daily_csv

WORKFLOW_VERSION = "qmt-backtest-workflow-1.0.0"


@dataclass(frozen=True)
class QmtBacktestRunConfig:
    factor_id: str
    factor_version: str
    adjustment: str
    train_start: str
    train_end: str
    validation_start: str
    validation_end: str
    test_start: str
    test_end: str
    portfolio: BaselineConfig
    adv_lookback: int = 20
    initial_nav: float = 1_000_000.0
    seed: int = 42

    def hyperparams_json(self) -> str:
        payload = {
            "workflow_version": WORKFLOW_VERSION,
            "adjustment": self.adjustment,
            "adv_lookback": self.adv_lookback,
            "initial_nav": self.initial_nav,
            "portfolio": asdict(self.portfolio),
        }
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


@dataclass(frozen=True)
class QmtBacktestRun:
    workflow_version: str
    snapshot_id: str
    experiment_id: str
    trial_id: str
    trial_number: int
    report: BaselineReport
    output_dir: Path
    data_audit_path: Path
    data_audit_sha256: str
    report_json_sha256: str
    report_markdown_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "workflow_version": self.workflow_version,
            "snapshot_id": self.snapshot_id,
            "experiment_id": self.experiment_id,
            "trial_id": self.trial_id,
            "trial_number": self.trial_number,
            "output_dir": str(self.output_dir),
            "data_audit_path": str(self.data_audit_path),
            "data_audit_sha256": self.data_audit_sha256,
            "report_json_sha256": self.report_json_sha256,
            "report_markdown_sha256": self.report_markdown_sha256,
            "metrics": asdict(self.report.metrics),
        }


def _validate_split_dates(config: QmtBacktestRunConfig) -> None:
    windows = (
        (config.train_start, config.train_end, "train"),
        (config.validation_start, config.validation_end, "validation"),
        (config.test_start, config.test_end, "test"),
    )
    parsed: list[tuple[date, date, str]] = []
    for start, end, name in windows:
        try:
            parsed_start, parsed_end = date.fromisoformat(start), date.fromisoformat(end)
        except ValueError as exc:
            raise ValueError(f"{name} boundaries must be ISO dates") from exc
        if parsed_start > parsed_end:
            raise ValueError(f"{name} start must not be after end")
        parsed.append((parsed_start, parsed_end, name))
    if parsed[0][1] >= parsed[1][0]:
        raise ValueError("training and validation windows must not overlap")
    if parsed[1][1] >= parsed[2][0]:
        raise ValueError("validation and test windows must not overlap")
    if config.adv_lookback < 1:
        raise ValueError("adv_lookback must be positive")
    if config.initial_nav <= 0:
        raise ValueError("initial_nav must be positive")


def _write_audit(path: Path, content: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = content + "\n"
    path.write_text(payload, encoding="utf-8", newline="\n")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _result_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def run_qmt_backtest_workflow(
    source: str | Path,
    *,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    config: QmtBacktestRunConfig,
    code_version: str,
    experiment_id: str | None = None,
) -> QmtBacktestRun:
    """Register first, then execute an auditable QMT-backed baseline attempt."""

    _validate_split_dates(config)
    if not code_version:
        raise ValueError("code_version cannot be empty")
    manifest = build_file_snapshot_manifest(source)
    snapshot_id = registry.register_snapshot(
        manifest,
        vendor_version=f"Guojin QMT / {config.adjustment}",
        notes="Exact local CSV export used by the V1.8 backtest workflow.",
    )
    if experiment_id is None:
        experiment_id = registry.create_experiment(
            ExperimentSpec(
                name=f"qmt_{config.factor_id}_topk",
                hypothesis=(
                    f"{config.factor_id} has positive out-of-sample net performance "
                    "under declared QMT execution costs."
                ),
                dataset_snapshot_id=snapshot_id,
                code_version=code_version,
                search_space="{}",
            )
        )
    trial_id, trial_number = registry.create_trial(
        TrialSpec(
            experiment_id=experiment_id,
            model_name="momentum_topk_baseline",
            factor_set=f"{config.factor_id}@{config.factor_version}",
            hyperparams=config.hyperparams_json(),
            seed=config.seed,
            train_start=config.train_start,
            train_end=config.train_end,
            validation_start=config.validation_start,
            validation_end=config.validation_end,
            test_start=config.test_start,
            test_end=config.test_end,
        )
    )

    try:
        expected_snapshot = registry.experiment_snapshot_id(experiment_id)
        if expected_snapshot != snapshot_id:
            raise ValueError(
                f"experiment snapshot {expected_snapshot} does not match source {snapshot_id}"
            )
        dataset = load_qmt_daily_csv(source, adjustment=config.adjustment)
        definition = build_seed_registry().get(config.factor_id, config.factor_version)
        observations = build_qmt_factor_observations(
            dataset.bars,
            definition,
            test_start=config.test_start,
            test_end=config.test_end,
            adv_lookback=config.adv_lookback,
        )
        report = run_momentum_topk(
            observations,
            BaselineLineage(
                factor_id=definition.factor_id,
                factor_version=definition.version,
                snapshot_id=snapshot_id,
                experiment_id=experiment_id,
                trial_id=trial_id,
                code_version=code_version,
            ),
            config.portfolio,
            initial_nav=config.initial_nav,
        )
        trial_output = Path(output_dir).expanduser().resolve() / trial_id
        artifacts = write_baseline_report(report, trial_output)
        audit_path = trial_output / "qmt-data-audit.json"
        audit_sha256 = _write_audit(audit_path, dataset.audit.to_json())
        artifact_specs = (
            ("qmt_data_audit", audit_path, audit_sha256),
            ("baseline_report_json", artifacts.json_path, artifacts.json_sha256),
            ("baseline_report_markdown", artifacts.markdown_path, artifacts.markdown_sha256),
        )
        for kind, path, digest in artifact_specs:
            registry.register_artifact(
                trial_id=trial_id,
                kind=kind,
                path=str(path),
                sha256=digest,
            )
        run = QmtBacktestRun(
            workflow_version=WORKFLOW_VERSION,
            snapshot_id=snapshot_id,
            experiment_id=experiment_id,
            trial_id=trial_id,
            trial_number=trial_number,
            report=report,
            output_dir=trial_output,
            data_audit_path=audit_path,
            data_audit_sha256=audit_sha256,
            report_json_sha256=artifacts.json_sha256,
            report_markdown_sha256=artifacts.markdown_sha256,
        )
        registry.record_trial_result(
            trial_id,
            _result_json({"status": "accepted", **run.to_dict()}),
        )
        return run
    except Exception as exc:
        registry.record_trial_result(
            trial_id,
            _result_json(
                {
                    "status": "rejected",
                    "workflow_version": WORKFLOW_VERSION,
                    "snapshot_id": snapshot_id,
                    "experiment_id": experiment_id,
                    "trial_id": trial_id,
                    "trial_number": trial_number,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            ),
        )
        raise
