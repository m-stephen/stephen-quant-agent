from pathlib import Path

from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_snapshot_manifest


def test_trial_counter_is_monotonic(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "prices.csv").write_text("date,close\n2026-01-01,1\n", encoding="utf-8")

    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    snapshot_id = registry.register_snapshot(build_snapshot_manifest(data_dir))
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            name="momentum_seed",
            hypothesis="Momentum should have positive rank IC.",
            dataset_snapshot_id=snapshot_id,
            code_version="test",
        )
    )

    spec = TrialSpec(
        experiment_id=experiment_id,
        model_name="baseline",
        factor_set="ret60",
        hyperparams="{}",
        seed=42,
        train_start="2020-01-01",
        train_end="2022-12-31",
        validation_start="2023-01-01",
        validation_end="2023-12-31",
        test_start="2024-01-01",
        test_end="2024-12-31",
    )
    _, n1 = registry.create_trial(spec)
    _, n2 = registry.create_trial(spec)
    assert (n1, n2) == (1, 2)
