from __future__ import annotations

from pathlib import Path

from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.path_config import LocalPathConfig

from .v70_discover_alpha import V70Config, V70Report, run_v70_discover_alpha

V71_VERSION = "v7.1-nondegenerate-automatic-alpha-discovery-1.0.0"


def run_v71_discover_alpha(
    paths_config: str | Path | LocalPathConfig,
    *,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    metadata_only: bool = False,
) -> V70Report:
    return run_v70_discover_alpha(
        paths_config,
        registry=registry,
        output_dir=output_dir,
        code_version=code_version,
        metadata_only=metadata_only,
        config=V70Config(formula_pairs=16, search_profile="v7.1"),
        method_version=V71_VERSION,
        report_stem="v7.1-report",
    )
