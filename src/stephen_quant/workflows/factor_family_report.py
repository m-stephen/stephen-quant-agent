from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

from stephen_quant.falsification import DeflatedSharpeResult, deflated_sharpe_ratio
from stephen_quant.integrity import ExperimentRegistry

FACTOR_FAMILY_REPORT_VERSION = "factor-family-validation-report-1.0.0"


@dataclass(frozen=True)
class FactorFamilyTrialSummary:
    trial_number: int
    trial_id: str
    factor_set: str
    status: str
    net_total_return: float | None
    net_sharpe: float | None
    max_drawdown: float | None
    benchmark_excess_total_return: float | None
    signal_shuffle_p_value: float | None
    return_permutation_p_value: float | None
    placebo_passed: bool | None


@dataclass(frozen=True)
class FactorFamilyValidationReport:
    method_version: str
    experiment_id: str
    recorded_trial_count: int
    accepted_trial_count: int
    selected_trial_id: str | None
    selected_factor_set: str | None
    deflated_sharpe: DeflatedSharpeResult | None
    decision: str
    trials: tuple[FactorFamilyTrialSummary, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self) -> str:
        lines = [
            "# Factor family validation",
            "",
            f"**Decision: {self.decision}**",
            "",
            f"- Method: `{self.method_version}`",
            f"- Experiment: `{self.experiment_id}`",
            f"- Recorded Trials: {self.recorded_trial_count}",
            f"- Accepted executions: {self.accepted_trial_count}",
            f"- Selected factor: `{self.selected_factor_set or 'none'}`",
        ]
        if self.deflated_sharpe is not None:
            lines.extend(
                (
                    f"- DSR probability: {self.deflated_sharpe.probability:.6f}",
                    f"- DSR benchmark Sharpe: {self.deflated_sharpe.benchmark_sharpe:.6f}",
                )
            )
        else:
            lines.append("- DSR: unavailable")
        lines.extend(
            (
                "",
                "| Trial | Factor | Status | Net return | Sharpe | Excess | Signal p | Return p |",
                "|---:|---|---|---:|---:|---:|---:|---:|",
            )
        )
        for trial in self.trials:
            values = (
                trial.net_total_return,
                trial.net_sharpe,
                trial.benchmark_excess_total_return,
                trial.signal_shuffle_p_value,
                trial.return_permutation_p_value,
            )
            formatted = ["N/A" if value is None else f"{value:.6f}" for value in values]
            lines.append(
                f"| {trial.trial_number} | `{trial.factor_set}` | {trial.status} | "
                f"{formatted[0]} | {formatted[1]} | {formatted[2]} | "
                f"{formatted[3]} | {formatted[4]} |"
            )
        return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class FactorFamilyReportArtifacts:
    json_path: Path
    markdown_path: Path
    json_sha256: str
    markdown_sha256: str


def _moments(values: list[float]) -> tuple[float, float]:
    center = sum(values) / len(values)
    variance = sum((value - center) ** 2 for value in values) / len(values)
    if variance == 0:
        return 0.0, 0.0
    scale = math.sqrt(variance)
    skewness = sum(((value - center) / scale) ** 3 for value in values) / len(values)
    excess_kurtosis = (
        sum(((value - center) / scale) ** 4 for value in values) / len(values) - 3
    )
    return skewness, excess_kurtosis


def build_factor_family_validation_report(
    registry: ExperimentRegistry,
    experiment_id: str,
) -> FactorFamilyValidationReport:
    with registry.connect() as connection:
        experiment = connection.execute(
            "SELECT 1 FROM experiments WHERE experiment_id = ?", (experiment_id,)
        ).fetchone()
        if experiment is None:
            raise ValueError(f"unknown experiment: {experiment_id}")
        rows = connection.execute(
            "SELECT trial_number, trial_id, factor_set, result_json FROM trials "
            "WHERE experiment_id = ? ORDER BY trial_number",
            (experiment_id,),
        ).fetchall()
        artifact_rows = connection.execute(
            "SELECT trial_id, kind, path FROM artifacts WHERE trial_id IN "
            "(SELECT trial_id FROM trials WHERE experiment_id = ?)",
            (experiment_id,),
        ).fetchall()
    artifact_paths = {
        (str(row["trial_id"]), str(row["kind"])): Path(str(row["path"]))
        for row in artifact_rows
    }

    summaries: list[FactorFamilyTrialSummary] = []
    accepted_payloads: dict[str, dict[str, object]] = {}
    for row in rows:
        payload = json.loads(row["result_json"]) if row["result_json"] else {}
        status = str(payload.get("status", "pending"))
        metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
        benchmark: dict[str, object] = {}
        placebo: dict[str, object] = {}
        if status == "accepted":
            accepted_payloads[str(row["trial_id"])] = payload
            benchmark_path = Path(str(payload.get("benchmark_comparison_path", "")))
            placebo_path = Path(str(payload.get("placebo_audit_path", "")))
            if benchmark_path.is_file():
                benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
            if placebo_path.is_file():
                placebo = json.loads(placebo_path.read_text(encoding="utf-8"))
        signal = placebo.get("signal_shuffle", {})
        returns = placebo.get("return_permutation", {})
        summaries.append(
            FactorFamilyTrialSummary(
                trial_number=int(row["trial_number"]),
                trial_id=str(row["trial_id"]),
                factor_set=str(row["factor_set"]),
                status=status,
                net_total_return=metrics.get("net_total_return"),
                net_sharpe=metrics.get("net_sharpe"),
                max_drawdown=metrics.get("max_drawdown"),
                benchmark_excess_total_return=benchmark.get("excess_total_return"),
                signal_shuffle_p_value=signal.get("empirical_p_value"),
                return_permutation_p_value=returns.get("empirical_p_value"),
                placebo_passed=placebo.get("passed"),
            )
        )

    accepted = [item for item in summaries if item.status == "accepted"]
    winner = max(
        (item for item in accepted if item.net_sharpe is not None),
        key=lambda item: item.net_sharpe,
        default=None,
    )
    dsr = None
    if winner is not None and len(accepted) >= 2:
        annualized = [
            item.net_sharpe for item in accepted if item.net_sharpe is not None
        ]
        if len(annualized) >= 2 and len(set(annualized)) > 1:
            report_path = artifact_paths[(winner.trial_id, "baseline_report_json")]
            report = json.loads(report_path.read_text(encoding="utf-8"))
            net_returns = [float(period["net_return"]) for period in report["periods"]]
            skewness, excess_kurtosis = _moments(net_returns)
            per_period = [value / math.sqrt(252) for value in annualized]
            dsr = deflated_sharpe_ratio(
                observed_sharpe=winner.net_sharpe / math.sqrt(252),
                trial_sharpes=per_period,
                recorded_trial_count=len(rows),
                observations=len(net_returns),
                skewness=skewness,
                excess_kurtosis=excess_kurtosis,
            )

    decision = "REJECT"
    if (
        winner is not None
        and winner.net_sharpe is not None
        and winner.net_sharpe > 0
        and winner.benchmark_excess_total_return is not None
        and winner.benchmark_excess_total_return > 0
        and winner.placebo_passed is True
        and dsr is not None
        and dsr.probability >= 0.95
    ):
        decision = "PASS_VALIDATION"
    return FactorFamilyValidationReport(
        method_version=FACTOR_FAMILY_REPORT_VERSION,
        experiment_id=experiment_id,
        recorded_trial_count=len(rows),
        accepted_trial_count=len(accepted),
        selected_trial_id=winner.trial_id if winner else None,
        selected_factor_set=winner.factor_set if winner else None,
        deflated_sharpe=dsr,
        decision=decision,
        trials=tuple(summaries),
    )


def _write(path: Path, content: str) -> str:
    path.write_text(content, encoding="utf-8", newline="\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def write_factor_family_validation_report(
    report: FactorFamilyValidationReport,
    output_dir: str | Path,
) -> FactorFamilyReportArtifacts:
    directory = Path(output_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "factor-family-validation.json"
    markdown_path = directory / "factor-family-validation.md"
    json_content = report.to_json() + "\n"
    markdown_content = report.to_markdown()
    return FactorFamilyReportArtifacts(
        json_path=json_path,
        markdown_path=markdown_path,
        json_sha256=_write(json_path, json_content),
        markdown_sha256=_write(markdown_path, markdown_content),
    )
