from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from stephen_quant.discovery.semantic_catalog import route_factor_schema
from stephen_quant.discovery.typed_dsl import TYPED_DSL_VERSION, type_check_schema
from stephen_quant.research_agent.models import ResearchAgentError

from .v55_semantic_router import _candidate_catalog

V56_VERSION = "v5.6-typed-dsl-1.0.0"


@dataclass(frozen=True)
class TypedCandidateResult:
    schema_id: str
    schema_fingerprint: str
    semantic_identity: str
    research_form: str
    status: str
    output_unit: str | None
    lookback_periods: int | None
    reason: str | None


@dataclass(frozen=True)
class V56Report:
    method_version: str
    typed_dsl_version: str
    unique_semantic_candidates: int
    accepted_candidates: int
    rejected_candidates: int
    output_unit_coverage: tuple[tuple[str, int], ...]
    candidates: tuple[TypedCandidateResult, ...]
    inferential_trial_delta: int
    decision: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        lines = [
            "# V5.6 类型安全因子 DSL" if zh else "# V5.6 Typed Factor DSL",
            "",
            f"**{'结论' if zh else 'Decision'}: `{self.decision}`**",
            "",
            f"- {'唯一语义候选' if zh else 'Unique semantic candidates'}: {self.unique_semantic_candidates}",
            f"- {'通过静态类型检查' if zh else 'Accepted by static type checking'}: {self.accepted_candidates}",
            f"- {'失败关闭' if zh else 'Failed closed'}: {self.rejected_candidates}",
            f"- Inferential Trial delta: {self.inferential_trial_delta}",
            "",
            "| Output unit | Accepted candidates |",
            "|---|---:|",
        ]
        lines.extend(f"| {unit} | {count} |" for unit, count in self.output_unit_coverage)
        lines.extend(["", "## Rejected expressions", ""])
        rejected = [item for item in self.candidates if item.status == "REJECTED"]
        if rejected:
            lines.extend(f"- `{item.schema_id}`: {item.reason}" for item in rejected)
        else:
            lines.append("- None")
        lines.append("")
        return "\n".join(lines)


def run_v56_typed_dsl(output_dir: str | Path) -> V56Report:
    schemas_by_identity = {}
    for schema in _candidate_catalog():
        route = route_factor_schema(schema)
        schemas_by_identity.setdefault(route.semantic_identity, (schema, route))
    results: list[TypedCandidateResult] = []
    for identity, (schema, route) in sorted(schemas_by_identity.items()):
        try:
            analysis = type_check_schema(schema, route=route)
            item = TypedCandidateResult(
                schema.schema_id,
                schema.fingerprint,
                identity,
                route.primary_form,
                "ACCEPTED",
                analysis.output.unit,
                analysis.lookback_periods,
                None,
            )
        except ResearchAgentError as exc:
            item = TypedCandidateResult(
                schema.schema_id,
                schema.fingerprint,
                identity,
                route.primary_form,
                "REJECTED",
                None,
                None,
                str(exc),
            )
        results.append(item)
    accepted = [item for item in results if item.status == "ACCEPTED"]
    units = tuple(
        (unit, sum(item.output_unit == unit for item in accepted))
        for unit in sorted({item.output_unit for item in accepted if item.output_unit is not None})
    )
    report = V56Report(
        V56_VERSION,
        TYPED_DSL_VERSION,
        len(results),
        len(accepted),
        len(results) - len(accepted),
        units,
        tuple(results),
        0,
        "READY_FOR_AUTOMATIC_PROPOSALS" if accepted else "TYPED_DSL_BLOCKED",
    )
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "v5.6-typed-dsl.json").write_text(report.to_json() + "\n", encoding="utf-8")
    (output / "v5.6-typed-dsl.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (output / "v5.6-typed-dsl.en.md").write_text(report.to_markdown("en"), encoding="utf-8")
    return report
