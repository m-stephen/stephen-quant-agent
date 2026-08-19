from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from stephen_quant.discovery.research_memory_v2 import (
    RESEARCH_MEMORY_V2_VERSION,
    ResearchMemorySummary,
    summarize_research_memory,
)

V61_VERSION = "v6.1-research-memory-1.0.0"


@dataclass(frozen=True)
class V61Report:
    method_version: str
    memory_version: str
    summary: ResearchMemorySummary
    validation_or_test_feedback_accepted: bool
    inferential_trial_delta: int
    decision: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        lines = [
            "# V6.1 研究记忆" if zh else "# V6.1 Research Memory",
            "",
            f"**{'结论' if zh else 'Decision'}: `{self.decision}`**",
            "",
            f"- Entries: {self.summary.entries}",
            f"- Chain head: `{self.summary.chain_head}`",
            f"- Recorded Trial delta: {self.summary.total_recorded_trial_delta}",
            f"- Recommended action: `{self.summary.recommended_action}`",
            f"- Validation/final-test feedback accepted: {self.validation_or_test_feedback_accepted}",
            f"- Memory operation Trial delta: {self.inferential_trial_delta}",
            "",
        ]
        return "\n".join(lines)


def run_v61_research_memory(
    output_dir: str | Path,
    *,
    ledger_path: str | Path | None = None,
) -> V61Report:
    source = ledger_path or Path(output_dir) / "nonexistent-memory-ledger.jsonl"
    summary = summarize_research_memory(source)
    report = V61Report(
        V61_VERSION,
        RESEARCH_MEMORY_V2_VERSION,
        summary,
        False,
        0,
        "READY_FOR_RESEARCH_EXPERIENCES" if summary.entries == 0 else "MEMORY_REPLAYED",
    )
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "v6.1-research-memory.json").write_text(report.to_json() + "\n", encoding="utf-8")
    (output / "v6.1-research-memory.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (output / "v6.1-research-memory.en.md").write_text(report.to_markdown("en"), encoding="utf-8")
    return report
