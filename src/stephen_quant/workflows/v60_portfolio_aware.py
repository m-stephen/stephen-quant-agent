from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from stephen_quant.discovery.portfolio_objective import (
    DEFAULT_PORTFOLIO_OBJECTIVE_CONFIG,
    PORTFOLIO_OBJECTIVE_VERSION,
    PairwiseDependence,
    PortfolioCandidateEvidence,
    PortfolioObjectiveConfig,
    PortfolioSelectionReport,
    select_portfolio_candidates,
)

V60_VERSION = "v6.0-portfolio-aware-1.0.0"


@dataclass(frozen=True)
class V60Report:
    method_version: str
    objective_version: str
    config: PortfolioObjectiveConfig
    evidence_candidates: int
    selection: PortfolioSelectionReport | None
    validation_or_test_metrics_used: bool
    inferential_trial_delta: int
    decision: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        lines = [
            "# V6.0 组合感知因子目标" if zh else "# V6.0 Portfolio-aware Factor Objective",
            "",
            f"**{'结论' if zh else 'Decision'}: `{self.decision}`**",
            "",
            f"- {'证据候选' if zh else 'Evidence candidates'}: {self.evidence_candidates}",
            f"- Minimum capacity: CNY {self.config.minimum_capacity_cny:,.0f}",
            f"- Maximum pair correlation: {self.config.maximum_pair_correlation:.2f}",
            f"- Maximum factors: {self.config.maximum_factors}",
            f"- Validation/final-test metrics used: {self.validation_or_test_metrics_used}",
            f"- Trial delta: {self.inferential_trial_delta}",
            "",
        ]
        if self.selection is not None:
            lines.append(f"- Selected: {', '.join(self.selection.selected_proposal_ids) or 'none'}")
            lines.append("")
        return "\n".join(lines)


def _load_evidence(
    path: str | Path,
) -> tuple[tuple[PortfolioCandidateEvidence, ...], tuple[PairwiseDependence, ...]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != {"candidates", "pairs"}:
        raise ValueError("portfolio evidence requires exactly candidates and pairs")
    if not isinstance(payload["candidates"], list) or not isinstance(payload["pairs"], list):
        raise TypeError("portfolio candidates and pairs must be lists")
    return (
        tuple(PortfolioCandidateEvidence(**row) for row in payload["candidates"]),
        tuple(PairwiseDependence(**row) for row in payload["pairs"]),
    )


def run_v60_portfolio_aware(
    output_dir: str | Path,
    *,
    evidence_path: str | Path | None = None,
    config: PortfolioObjectiveConfig = DEFAULT_PORTFOLIO_OBJECTIVE_CONFIG,
) -> V60Report:
    if evidence_path is None:
        selection = None
        count = 0
        decision = "READY_FOR_PORTFOLIO_EVIDENCE"
    else:
        candidates, pairs = _load_evidence(evidence_path)
        selection = select_portfolio_candidates(candidates, pairs, config=config)
        count = len(candidates)
        decision = "PORTFOLIO_SHORTLIST_READY" if selection.selected_proposal_ids else "NO_PORTFOLIO_VALUE"
    report = V60Report(
        V60_VERSION,
        PORTFOLIO_OBJECTIVE_VERSION,
        config,
        count,
        selection,
        False,
        0 if selection is None else selection.inferential_trial_delta,
        decision,
    )
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "v6.0-portfolio-aware.json").write_text(report.to_json() + "\n", encoding="utf-8")
    (output / "v6.0-portfolio-aware.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (output / "v6.0-portfolio-aware.en.md").write_text(report.to_markdown("en"), encoding="utf-8")
    return report
