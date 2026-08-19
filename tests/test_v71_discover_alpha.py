from __future__ import annotations

from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.path_config import LocalPathConfig
from stephen_quant.workflows.v71_discover_alpha import V71_VERSION, run_v71_discover_alpha


def test_v71_metadata_run_expands_direction_complete_batch(tmp_path) -> None:
    report = run_v71_discover_alpha(
        LocalPathConfig(None, {}),
        registry=ExperimentRegistry(tmp_path / "registry.sqlite3"),
        output_dir=tmp_path / "output",
        code_version="test",
        metadata_only=True,
    )
    assert report.method_version == V71_VERSION
    assert report.generated_direction_complete_candidates == 32
    assert report.alpha_status == "NO_VALIDATED_ALPHA"
    assert not report.validation_window_opened
    assert not report.test_window_opened
    assert (tmp_path / "output" / "v7.1-report.json").is_file()
    assert "V7.1" in report.to_markdown("zh")
