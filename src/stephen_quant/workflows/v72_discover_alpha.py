from __future__ import annotations

from pathlib import Path

from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.path_config import LocalPathConfig

from .v70_discover_alpha import V70Config, V70Report, run_v70_discover_alpha

V72_VERSION = "v7.2-source-balanced-automatic-alpha-discovery-1.0.0"
V72_SOURCE_PAIR_QUOTAS = (
    ("qd_daily", 4),
    ("qd_fund_flow", 4),
    ("qd_margin", 3),
    ("qd_chip", 4),
    ("qd_fund_flow+qd_margin", 1),
)


def run_v72_discover_alpha(
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
        config=V70Config(
            formula_pairs=16,
            search_profile="v7.2",
            source_pair_quotas=V72_SOURCE_PAIR_QUOTAS,
        ),
        method_version=V72_VERSION,
        report_stem="v7.2-report",
    )
