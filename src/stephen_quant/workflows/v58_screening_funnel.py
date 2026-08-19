from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from stephen_quant.discovery.proposal_generator import generate_symbolic_proposals
from stephen_quant.discovery.staged_screening import (
    DEFAULT_STAGED_SCREENING_CONFIG,
    STAGED_SCREENING_VERSION,
    FunnelEvidence,
    StagedScreeningConfig,
    StagedScreeningReport,
    run_staged_screening,
)

V58_VERSION = "v5.8-screening-funnel-1.0.0"


@dataclass(frozen=True)
class V58Report:
    method_version: str
    funnel_version: str
    config: StagedScreeningConfig
    available_typed_proposals: int
    evidence_rows: int
    screening: StagedScreeningReport | None
    inferential_trial_delta: int
    decision: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        lines = [
            "# V5.8 多阶段候选筛选漏斗" if zh else "# V5.8 Staged Candidate Screening Funnel",
            "",
            f"**{'结论' if zh else 'Decision'}: `{self.decision}`**",
            "",
            f"- {'类型安全提案' if zh else 'Typed proposals'}: {self.available_typed_proposals}",
            f"- {'证据行' if zh else 'Evidence rows'}: {self.evidence_rows}",
            f"- Inferential Trial delta: {self.inferential_trial_delta}",
            "",
            "| Stage | Budget |",
            "|---|---:|",
            f"| proposal | {self.config.proposal_budget} |",
            f"| data quality | {self.config.data_quality_budget} |",
            f"| training | {self.config.training_budget} |",
            f"| CPCV | {self.config.cpcv_budget} |",
            f"| execution | {self.config.execution_budget} |",
            "",
        ]
        if self.screening is not None:
            lines.extend(
                [
                    f"- Survivors: {len(self.screening.survivors)}",
                    f"- Labeled Trial delta: {self.screening.inferential_trial_delta}",
                    "",
                ]
            )
        return "\n".join(lines)


def _load_evidence(path: str | Path) -> tuple[FunnelEvidence, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise TypeError("screening evidence must be a JSON list")
    return tuple(FunnelEvidence(**row) for row in payload)


def run_v58_screening_funnel(
    output_dir: str | Path,
    *,
    evidence_path: str | Path | None = None,
    config: StagedScreeningConfig = DEFAULT_STAGED_SCREENING_CONFIG,
) -> V58Report:
    proposals = generate_symbolic_proposals(budget=config.proposal_budget)
    if evidence_path is None:
        screening = None
        decision = "READY_FOR_DATA_EVIDENCE"
        evidence_rows = 0
        trial_delta = 0
    else:
        evidence = _load_evidence(evidence_path)
        proposal_identities = {item.proposal_id: item.typed.semantic_identity for item in proposals}
        if not {item.proposal_id for item in evidence} <= set(proposal_identities):
            raise ValueError("screening evidence contains proposals outside the frozen V5.7 set")
        if any(
            item.semantic_identity != proposal_identities[item.proposal_id] for item in evidence
        ):
            raise ValueError("screening evidence semantic identity is not bound to its proposal")
        screening = run_staged_screening(evidence, config=config)
        evidence_rows = len(evidence)
        trial_delta = screening.inferential_trial_delta
        decision = "SCREENING_COMPLETE" if screening.survivors else "NO_FUNNEL_SURVIVOR"
    report = V58Report(
        V58_VERSION,
        STAGED_SCREENING_VERSION,
        config,
        len(proposals),
        evidence_rows,
        screening,
        trial_delta,
        decision,
    )
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "v5.8-screening-funnel.json").write_text(report.to_json() + "\n", encoding="utf-8")
    (output / "v5.8-screening-funnel.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (output / "v5.8-screening-funnel.en.md").write_text(report.to_markdown("en"), encoding="utf-8")
    return report
