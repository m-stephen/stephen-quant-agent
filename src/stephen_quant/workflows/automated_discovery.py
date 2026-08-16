from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from stephen_quant.discovery import (
    CampaignBudget,
    CampaignSpec,
    DiscoveryCpcvConfig,
    DiscoveryCpcvReport,
    GenerationPlan,
    ScreeningConfig,
    ScreeningReport,
    ScreeningWindow,
    SearchCampaign,
    generate_candidates,
    run_discovery_cpcv,
    run_training_screen,
    seed_generation_plan,
)
from stephen_quant.integrity.models import ExperimentSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_selected_files_snapshot_manifest
from stephen_quant.qmt import (
    QdAlternativeAudit,
    QdAlternativeConfig,
    build_qmt_factor_observations,
    load_qd_alternative_directory,
    load_qd_daily_directory,
    select_qd_daily_files,
)

AUTOMATED_DISCOVERY_VERSION = "v1.8.16-automated-discovery-1.0.0"
HORIZON_SESSIONS = {"next_open": 1, "1d": 1, "5d": 5, "20d": 20}


@dataclass(frozen=True)
class AutomatedDiscoveryConfig:
    data_start: str
    research_start: str
    research_end: str
    validation_start: str
    validation_end: str
    test_start: str
    test_end: str
    horizon: str
    windows: tuple[int, ...]
    schema_budget: int
    cpcv_budget: int
    execution_budget: int
    minimum_coverage: float = 0.90
    screen_minimum_mean_rank_ic: float = 0.0
    maximum_peer_rank_correlation: float = 0.80
    groups: int = 6
    test_groups: int = 3
    embargo_days: int = 5
    minimum_mean_path_rank_ic: float = 0.02
    minimum_positive_paths: int = 8
    maximum_pbo: float = 0.20
    seed: int = 42

    def validate(self) -> None:
        window = ScreeningWindow(
            self.research_start,
            self.research_end,
            self.validation_start,
            self.validation_end,
            self.test_start,
            self.test_end,
        )
        window.validate()
        if self.data_start > self.research_start:
            raise ValueError("data_start must provide history before research_start")
        if self.horizon not in HORIZON_SESSIONS:
            raise ValueError(f"unsupported automated-discovery horizon: {self.horizon}")
        if not self.windows or any(window < 2 for window in self.windows):
            raise ValueError("automated-discovery windows must contain values >= 2")
        CampaignBudget(
            self.schema_budget, self.cpcv_budget, self.execution_budget
        ).validate()


@dataclass(frozen=True)
class AutomatedDiscoveryReport:
    method_version: str
    experiment_id: str
    campaign_id: str
    snapshot_id: str
    source_snapshot_sha256: str
    generated_candidates: int
    unique_candidates: int
    screening: ScreeningReport
    cpcv: DiscoveryCpcvReport | None
    alternative_audits: tuple[QdAlternativeAudit, ...]
    validation_window_opened: bool
    test_window_opened: bool
    decision: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"en", "zh"}:
            raise ValueError("report language must be en or zh")
        zh = language == "zh"
        title = "# V1.8.16 自动因子发现与回测报告" if zh else "# V1.8.16 Automated Factor Discovery and Backtest"
        decision_label = "结论" if zh else "Decision"
        generated_label = "生成候选" if zh else "Generated candidates"
        shortlist_label = "CPCV 入围" if zh else "CPCV shortlist"
        source_label = "数据快照" if zh else "Data snapshot"
        validation_label = "验证期是否打开" if zh else "Validation window opened"
        test_label = "最终测试期是否打开" if zh else "Final test window opened"
        lines = [
            title,
            "",
            f"**{decision_label}: {self.decision}**",
            "",
            f"- Experiment: `{self.experiment_id}`",
            f"- Campaign: `{self.campaign_id}`",
            f"- Snapshot: `{self.snapshot_id}`",
            f"- {source_label}: `{self.source_snapshot_sha256}`",
            f"- {generated_label}: {self.generated_candidates} ({self.unique_candidates} unique)",
            f"- {shortlist_label}: {len(self.screening.shortlisted_fingerprints)}",
            f"- {validation_label}: {self.validation_window_opened}",
            f"- {test_label}: {self.test_window_opened}",
            "",
            "## Screening / 筛选",
            "",
            "| Trial | Schema | Coverage | Mean RankIC | Decision |",
            "|---:|---|---:|---:|---|",
        ]
        for score in self.screening.scores:
            rank_ic = "N/A" if score.mean_rank_ic is None else f"{score.mean_rank_ic:.6f}"
            lines.append(
                f"| {score.trial_number} | `{score.schema_id}` | {score.coverage:.2%} | "
                f"{rank_ic} | {score.decision} |"
            )
        if self.cpcv is not None:
            lines.extend(["", self.cpcv.to_markdown(language=language).strip(), ""])
        if self.alternative_audits:
            lines.extend(
                [
                    "",
                    "## Alternative data readiness / 替代数据就绪情况",
                    "",
                    "| Source | Files | Rows | Instruments | Snapshot |",
                    "|---|---:|---:|---:|---|",
                ]
            )
            lines.extend(
                f"| {audit.source_kind} | {audit.source_files} | {audit.rows} | "
                f"{audit.instruments} | `{audit.source_sha256}` |"
                for audit in self.alternative_audits
            )
        return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class AutomatedDiscoveryRun:
    report: AutomatedDiscoveryReport
    json_path: Path
    markdown_en_path: Path
    markdown_zh_path: Path
    schemas_path: Path


def load_automated_discovery_config(source: str | Path) -> AutomatedDiscoveryConfig:
    path = Path(source).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"automated-discovery manifest does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("automated-discovery manifest is not valid JSON") from exc
    if not isinstance(payload, dict) or payload.pop("manifest_version", None) != "1.0.0":
        raise ValueError("automated-discovery manifest_version must be 1.0.0")
    if "windows" in payload and isinstance(payload["windows"], list):
        payload["windows"] = tuple(payload["windows"])
    try:
        config = AutomatedDiscoveryConfig(**payload)
    except TypeError as exc:
        raise ValueError("automated-discovery manifest fields are invalid") from exc
    config.validate()
    return config


def _write(path: Path, content: str) -> str:
    path.write_text(content, encoding="utf-8", newline="\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _alternative_audits(
    paths: dict[str, str], config: AutomatedDiscoveryConfig, *, ingested_at: str
) -> tuple[QdAlternativeAudit, ...]:
    mapping = {
        "qd_fund_flow_dir": "fund_flow",
        "qd_auction_dir": "auction",
        "qd_margin_dir": "margin",
        "qd_industry_dir": "industry",
    }
    audits: list[QdAlternativeAudit] = []
    for key, kind in mapping.items():
        if key not in paths:
            continue
        dataset = load_qd_alternative_directory(
            paths[key],
            QdAlternativeConfig(
                source_kind=kind,  # type: ignore[arg-type]
                start_date=config.research_start,
                end_date=config.research_end,
                ingested_at=ingested_at,
            ),
        )
        audits.append(dataset.audit)
    return tuple(audits)


def run_automated_discovery(
    daily_dir: str | Path,
    instruments: tuple[str, ...],
    *,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    config: AutomatedDiscoveryConfig,
    alternative_paths: dict[str, str] | None = None,
    ingested_at: str = "1970-01-01T00:00:00+00:00",
) -> AutomatedDiscoveryRun:
    """Run bounded generation, training-only screening and CPCV without opening reserves."""

    config.validate()
    if len(instruments) < 3:
        raise ValueError("automated discovery requires at least three instruments")
    root = Path(daily_dir).expanduser().resolve()
    files = select_qd_daily_files(
        root, start_date=config.data_start, end_date=config.research_end
    )
    source_manifest = build_selected_files_snapshot_manifest(root, files)
    snapshot_id = registry.register_snapshot(
        source_manifest,
        vendor_version="QD daily back-ratio research partitions",
        notes="V1.8.16 research files only; validation and final test remain sealed.",
    )
    plan_seed = seed_generation_plan()
    plan = GenerationPlan(
        templates=plan_seed.templates,
        windows=config.windows,
        horizons=(config.horizon,),  # type: ignore[arg-type]
    )
    planned_count = len(plan.templates) * len(set(plan.windows))
    if planned_count > config.schema_budget:
        raise ValueError("generation plan exceeds the frozen schema budget")
    search_space = json.dumps(
        {
            "method_version": AUTOMATED_DISCOVERY_VERSION,
            "config": asdict(config),
            "planned_candidates": planned_count,
        },
        indent=2,
        sort_keys=True,
    )
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            name="v1.8.16_automated_factor_discovery",
            hypothesis="A bounded structured search can identify stable factor candidates.",
            dataset_snapshot_id=snapshot_id,
            code_version=code_version,
            search_space=search_space,
        )
    )
    campaign = SearchCampaign(
        registry,
        CampaignSpec(
            name="v1.8.16 structured search",
            experiment_id=experiment_id,
            budget=CampaignBudget(
                config.schema_budget, config.cpcv_budget, config.execution_budget
            ),
            horizons=(config.horizon,),
            ranking_metric="training_mean_rank_ic_then_cpcv_mean_path_rank_ic",
            stopping_rule="fixed schema and shortlist budgets",
            sealed_windows=(
                f"validation:{config.validation_start}:{config.validation_end}",
                f"test:{config.test_start}:{config.test_end}",
            ),
        ),
    )
    candidates = generate_candidates(campaign, plan)
    dataset = load_qd_daily_directory(
        root,
        start_date=config.data_start,
        end_date=config.research_end,
        instruments=tuple(sorted(set(instruments))),
        adjustment="back_ratio",
    )
    observations = {
        item.schema.fingerprint: build_qmt_factor_observations(
            dataset.bars,
            item.schema.compile(),
            test_start=config.research_start,
            test_end=config.research_end,
            horizon_sessions=HORIZON_SESSIONS[config.horizon],
        )
        for item in candidates
        if item.unique
    }
    window = ScreeningWindow(
        config.research_start,
        config.research_end,
        config.validation_start,
        config.validation_end,
        config.test_start,
        config.test_end,
    )
    screening = run_training_screen(
        registry,
        campaign,
        candidates,
        observations,
        window=window,
        config=ScreeningConfig(
            minimum_coverage=config.minimum_coverage,
            minimum_mean_rank_ic=config.screen_minimum_mean_rank_ic,
            maximum_peer_rank_correlation=config.maximum_peer_rank_correlation,
        ),
        seed=config.seed,
    )
    cpcv: DiscoveryCpcvReport | None = None
    if len(screening.shortlisted_fingerprints) >= 2:
        cpcv = run_discovery_cpcv(
            registry,
            campaign,
            screening,
            candidates,
            {
                fingerprint: observations[fingerprint]
                for fingerprint in screening.shortlisted_fingerprints
            },
            snapshot_id=snapshot_id,
            code_version=code_version,
            window=window,
            config=DiscoveryCpcvConfig(
                groups=config.groups,
                test_groups=config.test_groups,
                embargo_days=config.embargo_days,
                minimum_mean_path_rank_ic=config.minimum_mean_path_rank_ic,
                minimum_positive_paths=config.minimum_positive_paths,
                maximum_pbo=config.maximum_pbo,
            ),
            seed=config.seed,
        )
    alternative_audits = _alternative_audits(
        alternative_paths or {}, config, ingested_at=ingested_at
    )
    decision = (
        cpcv.decision
        if cpcv is not None
        else "REJECT_SCREEN_INSUFFICIENT_CPCV_CANDIDATES"
    )
    report = AutomatedDiscoveryReport(
        method_version=AUTOMATED_DISCOVERY_VERSION,
        experiment_id=experiment_id,
        campaign_id=campaign.campaign_id,
        snapshot_id=snapshot_id,
        source_snapshot_sha256=source_manifest.snapshot_sha256,
        generated_candidates=len(candidates),
        unique_candidates=sum(item.unique for item in candidates),
        screening=screening,
        cpcv=cpcv,
        alternative_audits=alternative_audits,
        validation_window_opened=False,
        test_window_opened=False,
        decision=decision,
    )
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "automated-discovery.json"
    markdown_en_path = output / "automated-discovery.en.md"
    markdown_zh_path = output / "automated-discovery.zh.md"
    schemas_path = output / "generated-schemas.json"
    json_sha = _write(json_path, report.to_json() + "\n")
    en_sha = _write(markdown_en_path, report.to_markdown("en"))
    zh_sha = _write(markdown_zh_path, report.to_markdown("zh"))
    schemas_sha = _write(
        schemas_path,
        json.dumps(
            [json.loads(item.schema.to_json()) for item in candidates],
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n",
    )
    first_trial = screening.scores[0].trial_id
    for kind, path, digest in (
        ("automated_discovery_json", json_path, json_sha),
        ("automated_discovery_markdown_en", markdown_en_path, en_sha),
        ("automated_discovery_markdown_zh", markdown_zh_path, zh_sha),
        ("automated_discovery_schemas", schemas_path, schemas_sha),
    ):
        registry.register_artifact(trial_id=first_trial, kind=kind, path=str(path), sha256=digest)
    return AutomatedDiscoveryRun(
        report, json_path, markdown_en_path, markdown_zh_path, schemas_path
    )
