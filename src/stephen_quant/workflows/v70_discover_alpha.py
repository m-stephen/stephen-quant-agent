from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from stephen_quant.discovery.generator import FactorTemplate, GenerationPlan
from stephen_quant.discovery.proposal_generator import (
    GeneratedProposal,
    generate_symbolic_proposals,
)
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.path_config import LocalPathConfig, load_local_path_config

from .automated_discovery import (
    AutomatedDiscoveryConfig,
    AutomatedDiscoveryReport,
    run_automated_discovery,
)
from .v55_semantic_router import run_v55_semantic_router
from .v56_typed_dsl import run_v56_typed_dsl
from .v57_proposal_generator import run_v57_proposal_generator
from .v58_screening_funnel import run_v58_screening_funnel
from .v59_search_controller import run_v59_search_controller
from .v60_portfolio_aware import run_v60_portfolio_aware
from .v61_research_memory import run_v61_research_memory
from .v62_auto_alpha_court import run_v62_auto_alpha_court
from .v63_forward_shadow import run_v63_forward_shadow

V70_VERSION = "v7.0-automatic-alpha-discovery-1.0.0"
_DATE_TOKEN = re.compile(r"(?<!\d)(20\d{6})(?!\d)")
_SOURCE_KEYS = (
    ("qd_daily", "qd_daily_dir"),
    ("qd_fund_flow", "qd_fund_flow_dir"),
    ("qd_auction", "qd_auction_dir"),
    ("qd_margin", "qd_margin_dir"),
    ("qd_chip", "qd_chip_dir"),
    ("qd_limit_event", "qd_limit_event_dir"),
    ("qd_industry", "qd_industry_dir"),
)


@dataclass(frozen=True)
class SourceCoverage:
    source: str
    status: str
    files: int
    dated_sessions: int
    first_session: str | None
    last_session: str | None
    coverage_manifest_sha256: str | None


@dataclass(frozen=True)
class V70Config:
    data_start: str = "2021-01-01"
    research_start: str = "2022-01-01"
    research_end: str = "2024-12-31"
    validation_start: str = "2025-01-01"
    validation_end: str = "2025-12-31"
    test_start: str = "2026-01-01"
    test_end: str = "2026-12-31"
    dynamic_universe_top_n: int = 300
    formula_pairs: int = 8
    horizon: str = "5d"


@dataclass(frozen=True)
class V70Report:
    method_version: str
    system_status: str
    alpha_status: str
    deployable: bool
    metadata_only: bool
    source_coverage: tuple[SourceCoverage, ...]
    common_core_sessions: int
    first_common_core_session: str | None
    last_common_core_session: str | None
    pipeline_decisions: dict[str, str]
    generated_direction_complete_candidates: int
    recorded_trials: int
    research_candidate_ids: tuple[str, ...]
    research: AutomatedDiscoveryReport | None
    validation_window_opened: bool
    test_window_opened: bool
    integrity_note: str
    decision: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        lines = [
            "# V7.0 自动 Alpha 发现报告" if zh else "# V7.0 Automatic Alpha Discovery Report",
            "",
            f"**{'系统状态' if zh else 'System status'}: `{self.system_status}`**",
            f"**Alpha {'状态' if zh else 'status'}: `{self.alpha_status}`**",
            "",
            f"- {'可部署' if zh else 'Deployable'}: {self.deployable}",
            (
                f"- {'方向完备研究候选' if zh else 'Direction-complete research candidates'}: "
                f"{self.generated_direction_complete_candidates}"
            ),
            f"- {'核心源共同交易日' if zh else 'Common core sessions'}: {self.common_core_sessions}",
            f"- {'本轮已记录 Trials' if zh else 'Recorded Trials in this run'}: {self.recorded_trials}",
            f"- {'验证期是否打开' if zh else 'Validation opened'}: {self.validation_window_opened}",
            f"- {'最终测试期是否打开' if zh else 'Final test opened'}: {self.test_window_opened}",
            "",
            "| Source | Status | Files | Dated sessions | First | Last |",
            "|---|---|---:|---:|---|---|",
        ]
        lines.extend(
            f"| {item.source} | {item.status} | {item.files} | {item.dated_sessions} | "
            f"{item.first_session or '-'} | {item.last_session or '-'} |"
            for item in self.source_coverage
        )
        lines.extend(["", "## Pipeline", ""])
        lines.extend(f"- {name}: `{decision}`" for name, decision in self.pipeline_decisions.items())
        if self.research is not None:
            lines.extend(
                [
                    "",
                    "## 2022–2024 Research-only evidence",
                    "",
                    f"- Experiment: `{self.research.experiment_id}`",
                    f"- Snapshot: `{self.research.source_snapshot_sha256}`",
                    (
                        f"- Generated/unique: {self.research.generated_candidates}/"
                        f"{self.research.unique_candidates}"
                    ),
                    f"- Screen shortlist: {len(self.research.screening.shortlisted_fingerprints)}",
                    f"- CPCV: `{self.research.cpcv.decision if self.research.cpcv else 'NOT_RUN'}`",
                    f"- Research decision: `{self.research.decision}`",
                ]
            )
        lines.extend(["", f"> {self.integrity_note}", ""])
        return "\n".join(lines)


def _coverage(source: str, root: Path | None) -> tuple[SourceCoverage, set[str]]:
    if root is None or not root.is_dir():
        return SourceCoverage(source, "MISSING", 0, 0, None, None, None), set()
    digest = hashlib.sha256()
    sessions: set[str] = set()
    files = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        files += 1
        relative = path.relative_to(root).as_posix()
        size = path.stat().st_size
        digest.update(f"{relative}\0{size}\n".encode())
        for token in _DATE_TOKEN.findall(relative):
            try:
                sessions.add(date.fromisoformat(f"{token[:4]}-{token[4:6]}-{token[6:]}").isoformat())
            except ValueError:
                continue
    ordered = sorted(sessions)
    return (
        SourceCoverage(
            source,
            "AVAILABLE" if files else "EMPTY",
            files,
            len(ordered),
            ordered[0] if ordered else None,
            ordered[-1] if ordered else None,
            digest.hexdigest(),
        ),
        sessions,
    )


def _direction_complete_plan(formula_pairs: int) -> tuple[GenerationPlan, tuple[str, ...]]:
    proposals = generate_symbolic_proposals(budget=512, include_inverse=True)
    supported = {"open", "high", "low", "close", "volume", "amount"}
    grouped: dict[str, list[GeneratedProposal]] = {}
    for item in proposals:
        if (
            item.proposal.research_form == "continuous_ranking"
            and item.schema.data_sources == ("qd_daily",)
            and set(item.schema.required_fields) <= supported
        ):
            grouped.setdefault(item.schema.formula, []).append(item)
    priority = {
        "symbolic:price-return": 0,
        "symbolic:price-risk": 1,
        "symbolic:field-trend": 2,
        "symbolic:same-unit-ratio": 3,
        "symbolic:field-level": 4,
    }
    ordered = sorted(
        (
            items
            for items in grouped.values()
            if {item.schema.direction for item in items} == {-1, 1}
        ),
        key=lambda items: (priority.get(items[0].proposal.provider_id, 99), items[0].schema.formula),
    )[:formula_pairs]
    selected = tuple(item for pair in ordered for item in sorted(pair, key=lambda row: row.schema.direction))
    if len(selected) != formula_pairs * 2:
        raise ValueError("automatic grammar cannot satisfy the direction-complete research budget")
    templates = tuple(
        FactorTemplate(
            template_id=f"v70_{item.proposal_id[:16]}",
            name=item.schema.name,
            event=item.schema.event,
            context=item.schema.context,
            quality=item.schema.quality,
            output=item.schema.output,
            formula_template=item.schema.formula,
            required_fields=item.schema.required_fields,
            data_sources=item.schema.data_sources,
            direction=item.schema.direction,
            economic_rationale=item.schema.economic_rationale,
        )
        for item in selected
    )
    return GenerationPlan(templates, (5,), ("5d",)), tuple(item.proposal_id for item in selected)


def run_v70_discover_alpha(
    paths_config: str | Path | LocalPathConfig,
    *,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    metadata_only: bool = False,
    config: V70Config | None = None,
) -> V70Report:
    config = config or V70Config()
    local = (
        paths_config
        if isinstance(paths_config, LocalPathConfig)
        else load_local_path_config(paths_config)
    )
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    coverages: list[SourceCoverage] = []
    sessions: dict[str, set[str]] = {}
    for source, key in _SOURCE_KEYS:
        item, dated = _coverage(source, local.paths.get(key))
        coverages.append(item)
        sessions[source] = dated
    core = set.intersection(
        sessions["qd_daily"], sessions["qd_fund_flow"], sessions["qd_auction"]
    )
    common = sorted(core)

    stage_root = output / "pipeline"
    pipeline = {
        "v5.5_semantic_router": run_v55_semantic_router(stage_root / "v5.5").decision,
        "v5.6_typed_dsl": run_v56_typed_dsl(stage_root / "v5.6").decision,
        "v5.7_proposals": run_v57_proposal_generator(stage_root / "v5.7").decision,
        "v5.8_funnel": run_v58_screening_funnel(stage_root / "v5.8").decision,
        "v5.9_controller": run_v59_search_controller(stage_root / "v5.9").status,
        "v6.0_portfolio": run_v60_portfolio_aware(stage_root / "v6.0").decision,
        "v6.1_memory": run_v61_research_memory(stage_root / "v6.1").decision,
        "v6.2_court": run_v62_auto_alpha_court(stage_root / "v6.2").decision,
        "v6.3_forward": run_v63_forward_shadow(stage_root / "v6.3").decision,
    }
    plan, proposal_ids = _direction_complete_plan(config.formula_pairs)
    research = None
    if not metadata_only:
        daily = local.paths.get("qd_daily_dir")
        membership = local.paths.get("dynamic_membership_jsonl")
        if daily is None or membership is None:
            raise ValueError("V7.0 research requires qd_daily_dir and dynamic_membership_jsonl")
        run = run_automated_discovery(
            daily,
            (),
            registry=registry,
            output_dir=output / "research-2022-2024",
            code_version=code_version,
            config=AutomatedDiscoveryConfig(
                data_start=config.data_start,
                research_start=config.research_start,
                research_end=config.research_end,
                validation_start=config.validation_start,
                validation_end=config.validation_end,
                test_start=config.test_start,
                test_end=config.test_end,
                horizon=config.horizon,
                windows=(5,),
                schema_budget=config.formula_pairs * 2,
                cpcv_budget=config.formula_pairs,
                execution_budget=0,
                minimum_coverage=0.80,
                screen_minimum_mean_rank_ic=0.005,
                maximum_peer_rank_correlation=0.70,
                groups=6,
                test_groups=3,
                embargo_days=5,
                minimum_mean_path_rank_ic=0.005,
                minimum_positive_paths=6,
                maximum_pbo=0.20,
                dynamic_universe_top_n=config.dynamic_universe_top_n,
                search_profile="v7.0",
                minimum_positive_year_fraction=2 / 3,
                maximum_rank_turnover=0.80,
                stability_weight=0.01,
                turnover_penalty=0.01,
            ),
            dynamic_membership_path=membership,
            generation_plan=plan,
        )
        research = run.report
        pipeline["v7.0_research"] = research.decision

    alpha_status = (
        "RESEARCH_CANDIDATE_PENDING_EXECUTION"
        if research is not None and research.cpcv is not None and research.cpcv.signal_gate_passed
        else "NO_VALIDATED_ALPHA"
    )
    recorded_trials = 0 if research is None else registry.trial_count(research.experiment_id)
    report = V70Report(
        V70_VERSION,
        "OPERATIONAL",
        alpha_status,
        False,
        metadata_only,
        tuple(coverages),
        len(common),
        common[0] if common else None,
        common[-1] if common else None,
        pipeline,
        len(proposal_ids),
        recorded_trials,
        proposal_ids,
        research,
        False,
        False,
        (
            "2025/2026 labels remained sealed. A research survivor is not deployable until "
            "execution, placebo, DSR, cost/capacity, Alpha Court and new-data forward gates pass."
        ),
        "V7_OPERATIONAL_RESEARCH_COMPLETE" if research is not None else "V7_OPERATIONAL_METADATA_ONLY",
    )
    (output / "v7.0-report.json").write_text(report.to_json() + "\n", encoding="utf-8")
    (output / "v7.0-report.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (output / "v7.0-report.en.md").write_text(report.to_markdown("en"), encoding="utf-8")
    return report
