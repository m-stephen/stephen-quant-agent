from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from stephen_quant.discovery.proposal_generator import (
    PROPOSAL_GENERATOR_VERSION,
    GeneratedProposal,
    generate_symbolic_proposals,
    load_llm_proposals,
    merge_proposals,
)

V57_VERSION = "v5.7-proposal-generator-1.0.0"


@dataclass(frozen=True)
class ProposalCoverage:
    dimension: str
    value: str
    candidates: int


@dataclass(frozen=True)
class V57Report:
    method_version: str
    generator_version: str
    proposal_budget: int
    symbolic_candidates: int
    llm_candidates: int
    merged_candidates: int
    deduplicated_candidates: int
    coverage: tuple[ProposalCoverage, ...]
    proposals: tuple[GeneratedProposal, ...]
    llm_boundary: str
    label_access: bool
    inferential_trial_delta: int
    decision: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        lines = [
            "# V5.7 自动候选提案生成器" if zh else "# V5.7 Automatic Candidate Proposal Generator",
            "",
            f"**{'结论' if zh else 'Decision'}: `{self.decision}`**",
            "",
            f"- {'符号候选' if zh else 'Symbolic candidates'}: {self.symbolic_candidates}",
            f"- {'LLM 候选' if zh else 'LLM candidates'}: {self.llm_candidates}",
            f"- {'合并后候选' if zh else 'Merged candidates'}: {self.merged_candidates}",
            f"- {'跨来源去重' if zh else 'Cross-origin duplicates removed'}: {self.deduplicated_candidates}",
            f"- Label access: {self.label_access}",
            f"- Inferential Trial delta: {self.inferential_trial_delta}",
            "",
            "| Dimension | Value | Candidates |",
            "|---|---|---:|",
        ]
        lines.extend(f"| {item.dimension} | {item.value} | {item.candidates} |" for item in self.coverage)
        lines.extend(["", f"LLM boundary: `{self.llm_boundary}`", ""])
        return "\n".join(lines)


def run_v57_proposal_generator(
    output_dir: str | Path,
    *,
    budget: int = 256,
    llm_proposals_path: str | Path | None = None,
    llm_provider_id: str | None = None,
) -> V57Report:
    symbolic = generate_symbolic_proposals(budget=budget)
    if llm_proposals_path is None:
        llm: tuple[GeneratedProposal, ...] = ()
    else:
        if llm_provider_id is None:
            raise ValueError("llm_provider_id is required with llm_proposals_path")
        llm = load_llm_proposals(llm_proposals_path, provider_id=llm_provider_id)
    merged = merge_proposals(symbolic, llm, budget=budget)
    coverage = tuple(
        ProposalCoverage(dimension, value, count)
        for dimension, values in (
            (
                "origin",
                tuple(
                    (origin, sum(item.proposal.origin == origin for item in merged))
                    for origin in ("symbolic", "llm")
                ),
            ),
            (
                "research_form",
                tuple(
                    (form, sum(item.typed.research_form == form for item in merged))
                    for form in ("continuous_ranking", "event_study", "portfolio_filter", "regime_switch")
                ),
            ),
        )
        for value, count in values
    )
    checks = (
        bool(merged),
        all(item.typed.lookback_periods <= 252 for item in merged),
        all(item.proposal.hypothesis.strip() for item in merged),
        any(item.typed.research_form == "event_study" for item in merged),
    )
    report = V57Report(
        V57_VERSION,
        PROPOSAL_GENERATOR_VERSION,
        budget,
        len(symbolic),
        len(llm),
        len(merged),
        len(symbolic) + len(llm) - len(merged),
        coverage,
        merged,
        "untrusted_json_only_no_code_no_labels",
        False,
        0,
        "READY_FOR_STAGED_SCREENING" if all(checks) else "PROPOSAL_GENERATION_BLOCKED",
    )
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "v5.7-proposals.json").write_text(report.to_json() + "\n", encoding="utf-8")
    (output / "v5.7-proposals.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (output / "v5.7-proposals.en.md").write_text(report.to_markdown("en"), encoding="utf-8")
    return report
