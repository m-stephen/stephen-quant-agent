from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.qmt import DatExportConfig, DatExportResult, export_qmt_dat_daily_csv

from .qmt_backtest import QmtBacktestRun, QmtBacktestRunConfig, run_qmt_backtest_workflow

VALIDATION_VERSION = "qmt-dat-backtest-validation-1.1.0"
MINIMUM_RESEARCH_UNIVERSE = 30


@dataclass(frozen=True)
class QmtDatValidationConfig:
    data_start: str
    data_end: str
    stocks: tuple[str, ...]
    backtest: QmtBacktestRunConfig
    overwrite: bool = False


@dataclass(frozen=True)
class QmtDatValidationRun:
    validation_version: str
    export: DatExportResult
    backtest: QmtBacktestRun
    summary_json_path: Path
    summary_json_sha256: str
    summary_markdown_path: Path
    summary_markdown_sha256: str
    engineering_validated: bool
    research_claim_eligible: bool
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "validation_version": self.validation_version,
            "export": self.export.to_dict(),
            "backtest": self.backtest.to_dict(),
            "summary_json_path": str(self.summary_json_path),
            "summary_json_sha256": self.summary_json_sha256,
            "summary_markdown_path": str(self.summary_markdown_path),
            "summary_markdown_sha256": self.summary_markdown_sha256,
            "engineering_validated": self.engineering_validated,
            "research_claim_eligible": self.research_claim_eligible,
            "limitations": list(self.limitations),
        }


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_atomic(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return _sha256(payload)


def _limitations(instruments: int, adjustment: str) -> tuple[str, ...]:
    items = []
    if adjustment == "none":
        items.append("Direct DAT prices are unadjusted; corporate actions are not reconstructed.")
    items.extend(
        [
            "The instrument universe is operator-supplied and may contain survivorship bias.",
            "A successful run validates engineering integrity, not factor profitability.",
        ]
    )
    if instruments < MINIMUM_RESEARCH_UNIVERSE:
        items.append(
            f"The universe has {instruments} instruments, below the "
            f"{MINIMUM_RESEARCH_UNIVERSE}-instrument research floor."
        )
    return tuple(items)


def _summary_payload(
    export: DatExportResult,
    run: QmtBacktestRun,
    limitations: tuple[str, ...],
) -> dict[str, object]:
    return {
        "validation_version": VALIDATION_VERSION,
        "status": "engineering_validated",
        "engineering_validated": True,
        "research_claim_eligible": False,
        "gates": [
            {"name": "dat_schema_and_semantics", "passed": True},
            {"name": "raw_source_hashes", "passed": True},
            {
                "name": "corporate_action_snapshot",
                "passed": True,
                "available": export.adjustment == "back_ratio",
                "required_for_research": True,
            },
            {"name": "canonical_csv_snapshot", "passed": True},
            {"name": "trial_registered_before_backtest", "passed": True},
            {"name": "point_in_time_execution", "passed": True},
            {"name": "explicit_cost_model", "passed": True},
        ],
        "data": {
            "adjustment": export.adjustment,
            "instruments": export.exported_instruments,
            "rows": export.rows,
            "start_date": export.start_date,
            "end_date": export.end_date,
            "csv_sha256": export.output_sha256,
            "schema_sha256": export.schema_sha256,
            "provenance_manifest_sha256": run.provenance_manifest_sha256,
        },
        "lineage": {
            "snapshot_id": run.snapshot_id,
            "experiment_id": run.experiment_id,
            "trial_id": run.trial_id,
            "trial_number": run.trial_number,
        },
        "metrics": asdict(run.report.metrics),
        "limitations": list(limitations),
    }


def _summary_markdown(payload: dict[str, object]) -> str:
    data = payload["data"]
    lineage = payload["lineage"]
    metrics = payload["metrics"]
    assert isinstance(data, dict)
    assert isinstance(lineage, dict)
    assert isinstance(metrics, dict)
    lines = [
        "# QMT DAT Backtest Validation",
        "",
        "## Verdict",
        "",
        "- Engineering validation: **PASS**",
        "- Research-claim eligibility: **NO**",
        "- Reason: operator-supplied universe may contain survivorship bias",
        "",
        "## Data and lineage",
        "",
        f"- Instruments: {data['instruments']}",
        f"- Rows: {data['rows']}",
        f"- Data window: {data['start_date']} to {data['end_date']}",
        f"- CSV SHA-256: `{data['csv_sha256']}`",
        f"- Schema SHA-256: `{data['schema_sha256']}`",
        f"- Snapshot: `{lineage['snapshot_id']}`",
        f"- Experiment: `{lineage['experiment_id']}`",
        f"- Trial: `{lineage['trial_id']}` (#{lineage['trial_number']})",
        "",
        "## Net-of-cost pilot result",
        "",
        f"- Periods: {metrics['periods']}",
        f"- Net total return: {float(metrics['net_total_return']):.6%}",
        f"- Net Sharpe: {metrics['net_sharpe']}",
        f"- Maximum drawdown: {float(metrics['max_drawdown']):.6%}",
        f"- Total cost: {float(metrics['total_cost']):.6f}",
        "",
        "## Limitations",
        "",
    ]
    lines.extend(f"- {item}" for item in payload["limitations"])
    return "\n".join(lines) + "\n"


def run_qmt_dat_backtest_validation(
    datadir: str | Path,
    *,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    config: QmtDatValidationConfig,
    code_version: str,
    experiment_id: str | None = None,
) -> QmtDatValidationRun:
    """Execute the direct-DAT engineering validation as one auditable command."""

    root = Path(output_dir).expanduser().resolve()
    adjustment = config.backtest.adjustment
    if adjustment not in {"none", "back_ratio"}:
        raise ValueError("direct DAT validation requires adjustment='none' or 'back_ratio'")
    dataset_csv = root / "data" / f"qmt-daily-{adjustment}.csv"
    summary_json = root / "validation-summary.json"
    summary_markdown = root / "validation-summary.md"
    if not config.overwrite:
        existing = [path for path in (dataset_csv, summary_json, summary_markdown) if path.exists()]
        if existing:
            raise ValueError(f"validation output already exists: {existing[0]}")

    export = export_qmt_dat_daily_csv(
        DatExportConfig(
            datadir=str(datadir),
            output_csv=str(dataset_csv),
            start_date=config.data_start,
            end_date=config.data_end,
            stocks=config.stocks,
            adjustment=adjustment,
            overwrite=config.overwrite,
        )
    )
    run = run_qmt_backtest_workflow(
        dataset_csv,
        registry=registry,
        output_dir=root / "trials",
        config=config.backtest,
        code_version=code_version,
        experiment_id=experiment_id,
    )
    limitations = _limitations(export.exported_instruments, export.adjustment)
    summary = _summary_payload(export, run, limitations)
    json_payload = (
        json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    markdown_payload = _summary_markdown(summary).encode("utf-8")
    json_sha256 = _write_atomic(summary_json, json_payload)
    markdown_sha256 = _write_atomic(summary_markdown, markdown_payload)
    registry.register_artifact(
        trial_id=run.trial_id,
        kind="qmt_dat_validation_json",
        path=str(summary_json),
        sha256=json_sha256,
    )
    registry.register_artifact(
        trial_id=run.trial_id,
        kind="qmt_dat_validation_markdown",
        path=str(summary_markdown),
        sha256=markdown_sha256,
    )
    return QmtDatValidationRun(
        validation_version=VALIDATION_VERSION,
        export=export,
        backtest=run,
        summary_json_path=summary_json,
        summary_json_sha256=json_sha256,
        summary_markdown_path=summary_markdown,
        summary_markdown_sha256=markdown_sha256,
        engineering_validated=True,
        research_claim_eligible=False,
        limitations=limitations,
    )
