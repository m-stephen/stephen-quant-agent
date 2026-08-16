from __future__ import annotations

import json
from pathlib import Path

from stephen_quant.integrity import ExperimentRegistry
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.snapshot import build_file_snapshot_manifest
from stephen_quant.workflows import (
    build_factor_family_validation_report,
    write_factor_family_validation_report,
)


def test_factor_family_report_uses_full_trial_count_and_dsr(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    source.write_text("fixture\n", encoding="utf-8")
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    snapshot_id = registry.register_snapshot(build_file_snapshot_manifest(source))
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            name="factor_family",
            hypothesis="One predeclared factor survives.",
            dataset_snapshot_id=snapshot_id,
            code_version="test-sha",
            search_space='{"factors":["a","b","c"]}',
        )
    )

    for index, (factor, sharpe, passed) in enumerate(
        (("a", 0.2, False), ("b", 1.0, True), ("c", 0.5, False)), start=1
    ):
        trial_id, trial_number = registry.create_trial(
            TrialSpec(
                experiment_id=experiment_id,
                model_name="baseline",
                factor_set=f"{factor}@1.0.0",
                hyperparams="{}",
                seed=42,
                train_start="2022-01-01",
                train_end="2023-12-31",
                validation_start="2024-01-01",
                validation_end="2024-12-31",
                test_start="2026-01-01",
                test_end="2026-12-31",
            )
        )
        assert trial_number == index
        directory = tmp_path / trial_id
        directory.mkdir()
        baseline = directory / "baseline-report.json"
        baseline.write_text(
            json.dumps(
                {
                    "periods": [
                        {"net_return": value}
                        for value in (0.01, -0.005, 0.02, 0.0, 0.015, -0.01)
                    ]
                }
            ),
            encoding="utf-8",
        )
        placebo = directory / "placebo.json"
        placebo.write_text(
            json.dumps(
                {
                    "passed": passed,
                    "signal_shuffle": {"empirical_p_value": 0.01 if passed else 0.5},
                    "return_permutation": {
                        "empirical_p_value": 0.01 if passed else 0.5
                    },
                }
            ),
            encoding="utf-8",
        )
        benchmark = directory / "benchmark.json"
        benchmark.write_text(
            json.dumps({"excess_total_return": 0.1 if factor == "b" else -0.1}),
            encoding="utf-8",
        )
        registry.register_artifact(
            trial_id=trial_id,
            kind="baseline_report_json",
            path=str(baseline),
        )
        registry.record_trial_result(
            trial_id,
            json.dumps(
                {
                    "status": "accepted",
                    "metrics": {
                        "net_total_return": sharpe / 10,
                        "net_sharpe": sharpe,
                        "max_drawdown": -0.1,
                    },
                    "benchmark_comparison_path": str(benchmark),
                    "placebo_audit_path": str(placebo),
                }
            ),
        )

    report = build_factor_family_validation_report(registry, experiment_id)
    artifacts = write_factor_family_validation_report(report, tmp_path / "family")

    assert report.recorded_trial_count == 3
    assert report.accepted_trial_count == 3
    assert report.selected_factor_set == "b@1.0.0"
    assert report.deflated_sharpe is not None
    assert report.deflated_sharpe.recorded_trial_count == 3
    assert artifacts.json_path.exists()
    assert artifacts.markdown_path.exists()
