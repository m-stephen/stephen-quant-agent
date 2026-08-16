from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from stephen_quant.integrity.registry import ExperimentRegistry

from .automated_discovery import (
    AutomatedDiscoveryRun,
    load_automated_discovery_config,
    run_automated_discovery,
)

AUTOMATED_DISCOVERY_SUITE_VERSION = "v1.8.16-multi-horizon-suite-1.0.0"


@dataclass(frozen=True)
class AutomatedDiscoverySuiteItem:
    horizon: str
    experiment_id: str
    campaign_id: str
    decision: str
    report_path: str


@dataclass(frozen=True)
class AutomatedDiscoverySuiteReport:
    method_version: str
    runs: tuple[AutomatedDiscoverySuiteItem, ...]
    global_trial_count: int
    validation_window_opened: bool
    test_window_opened: bool

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"en", "zh"}:
            raise ValueError("suite report language must be en or zh")
        title = (
            "# V1.8.16 多期限自动因子研究汇总"
            if language == "zh"
            else "# V1.8.16 Multi-horizon Automated Factor Research"
        )
        lines = [
            title,
            "",
            f"- Global recorded trials: {self.global_trial_count}",
            f"- Validation window opened: {self.validation_window_opened}",
            f"- Final test window opened: {self.test_window_opened}",
            "",
            "| Horizon | Experiment | Campaign | Decision | Report |",
            "|---|---|---|---|---|",
        ]
        lines.extend(
            f"| {item.horizon} | `{item.experiment_id}` | `{item.campaign_id}` | "
            f"{item.decision} | `{item.report_path}` |"
            for item in self.runs
        )
        return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class AutomatedDiscoverySuiteRun:
    report: AutomatedDiscoverySuiteReport
    runs: tuple[AutomatedDiscoveryRun, ...]
    json_path: Path
    markdown_en_path: Path
    markdown_zh_path: Path


def _manifest_paths(source: str | Path) -> tuple[Path, ...]:
    path = Path(source).expanduser().resolve()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"multi-horizon suite manifest is invalid: {path}") from exc
    if not isinstance(payload, dict) or payload.get("manifest_version") != "1.0.0":
        raise ValueError("suite manifest_version must be 1.0.0")
    manifests = payload.get("search_manifests")
    if not isinstance(manifests, list) or len(manifests) < 2:
        raise ValueError("suite requires at least two search_manifests")
    resolved = tuple((path.parent / str(item)).resolve() for item in manifests)
    if len(set(resolved)) != len(resolved):
        raise ValueError("suite search_manifests must be unique")
    return resolved


def run_automated_discovery_suite(
    daily_dir: str | Path,
    instruments: tuple[str, ...],
    *,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    suite_manifest: str | Path,
    alternative_paths: dict[str, str] | None = None,
    dynamic_membership_path: str | Path | None = None,
    ingested_at: str,
) -> AutomatedDiscoverySuiteRun:
    """Run each horizon as an independent Experiment under one global ledger."""

    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    runs: list[AutomatedDiscoveryRun] = []
    horizons: list[str] = []
    seen_horizons: set[str] = set()
    for manifest in _manifest_paths(suite_manifest):
        config = load_automated_discovery_config(manifest)
        if config.horizon in seen_horizons:
            raise ValueError(f"duplicate suite horizon: {config.horizon}")
        seen_horizons.add(config.horizon)
        horizons.append(config.horizon)
        runs.append(
            run_automated_discovery(
                daily_dir,
                instruments,
                registry=registry,
                output_dir=output / config.horizon,
                code_version=code_version,
                config=config,
                alternative_paths=alternative_paths,
                dynamic_membership_path=dynamic_membership_path,
                ingested_at=ingested_at,
            )
        )
    report = AutomatedDiscoverySuiteReport(
        method_version=AUTOMATED_DISCOVERY_SUITE_VERSION,
        runs=tuple(
            AutomatedDiscoverySuiteItem(
                horizon,
                run.report.experiment_id,
                run.report.campaign_id,
                run.report.decision,
                str(run.json_path),
            )
            for run, horizon in zip(runs, horizons, strict=True)
        ),
        global_trial_count=registry.global_trial_count(),
        validation_window_opened=any(run.report.validation_window_opened for run in runs),
        test_window_opened=any(run.report.test_window_opened for run in runs),
    )
    json_path = output / "automated-discovery-suite.json"
    markdown_en_path = output / "automated-discovery-suite.en.md"
    markdown_zh_path = output / "automated-discovery-suite.zh.md"
    for path, content in (
        (json_path, report.to_json() + "\n"),
        (markdown_en_path, report.to_markdown("en")),
        (markdown_zh_path, report.to_markdown("zh")),
    ):
        path.write_text(content, encoding="utf-8", newline="\n")
    return AutomatedDiscoverySuiteRun(
        report, tuple(runs), json_path, markdown_en_path, markdown_zh_path
    )
