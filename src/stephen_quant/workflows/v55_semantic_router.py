from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from stephen_quant.discovery.semantic_catalog import (
    SEMANTIC_CATALOG_VERSION,
    CandidateRoutingDecision,
    build_semantic_catalog,
    route_factor_schema,
)

from .v43_domain_breadth import _schemas, generation_plans
from .v54_alpha_conversion import constrained_schemas

V55_VERSION = "v5.5-semantic-router-1.0.0"


@dataclass(frozen=True)
class RouteCoverage:
    research_form: str
    candidates: int


@dataclass(frozen=True)
class V55Report:
    method_version: str
    catalog_version: str
    catalog_fields: int
    proposed_schemas: int
    unique_semantic_candidates: int
    duplicate_schemas: int
    route_coverage: tuple[RouteCoverage, ...]
    decisions: tuple[CandidateRoutingDecision, ...]
    event_sources_correctly_routed: bool
    margin_dual_role_ready: bool
    missing_zero_semantics_distinct: bool
    decision: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        lines = [
            "# V5.5 字段语义与研究用途路由" if zh else "# V5.5 Field Semantics and Research-form Routing",
            "",
            f"**{'结论' if zh else 'Decision'}: `{self.decision}`**",
            "",
            f"- {'字段语义' if zh else 'Field semantics'}: {self.catalog_fields}",
            f"- {'原始 schemas' if zh else 'Raw schemas'}: {self.proposed_schemas}",
            f"- {'唯一语义候选' if zh else 'Unique semantic candidates'}: {self.unique_semantic_candidates}",
            f"- {'重复 schemas' if zh else 'Duplicate schemas'}: {self.duplicate_schemas}",
            "",
            "| Research form | Candidates |",
            "|---|---:|",
        ]
        lines.extend(f"| {item.research_form} | {item.candidates} |" for item in self.route_coverage)
        lines.extend(
            [
                "",
                f"- Event routing: {self.event_sources_correctly_routed}",
                f"- Margin ranking/filter roles: {self.margin_dual_role_ready}",
                f"- Missing/zero distinction: {self.missing_zero_semantics_distinct}",
                "",
            ]
        )
        return "\n".join(lines)


def _candidate_catalog() -> tuple:
    schemas = list(_schemas(generation_plans()))
    schemas.extend(schema for _, schema in constrained_schemas())
    return tuple(schemas)


def run_v55_semantic_router(output_dir: str | Path) -> V55Report:
    catalog = build_semantic_catalog()
    schemas = _candidate_catalog()
    decisions = [route_factor_schema(schema, catalog=catalog) for schema in schemas]
    first_by_identity: dict[str, CandidateRoutingDecision] = {}
    for item in decisions:
        first_by_identity.setdefault(item.semantic_identity, item)
    unique = tuple(sorted(first_by_identity.values(), key=lambda item: item.semantic_identity))
    forms = tuple(
        RouteCoverage(form, sum(item.primary_form == form for item in unique))
        for form in ("continuous_ranking", "event_study", "portfolio_filter", "regime_switch")
    )
    event_ok = all(
        item.primary_form == "event_study"
        for item in unique
        if "qd_auction" in item.sources or "qd_limit_event" in item.sources
    )
    margin = [item for item in unique if "qd_margin" in item.sources]
    margin_ok = bool(margin) and all(
        {"continuous_ranking", "portfolio_filter"} <= set(item.allowed_forms) for item in margin
    )
    semantics = {(item.source, item.field): item for item in catalog}
    missing_ok = (
        semantics[("qd_limit_event", "kpl_limit_up_flag")].missing_meaning
        == "structural_zero"
        and semantics[("qd_limit_event", "kpl_close_seal_amount")].missing_meaning
        == "not_applicable"
        and semantics[("qd_auction", "auction_return")].missing_meaning == "unknown"
    )
    checks = (event_ok, margin_ok, missing_ok)
    report = V55Report(
        V55_VERSION,
        SEMANTIC_CATALOG_VERSION,
        len(catalog),
        len(schemas),
        len(unique),
        len(schemas) - len(unique),
        forms,
        unique,
        event_ok,
        margin_ok,
        missing_ok,
        "READY_FOR_TYPED_DSL" if all(checks) else "SEMANTIC_ROUTING_BLOCKED",
    )
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "v5.5-semantic-router.json").write_text(report.to_json() + "\n", encoding="utf-8")
    (output / "v5.5-semantic-router.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (output / "v5.5-semantic-router.en.md").write_text(report.to_markdown("en"), encoding="utf-8")
    (output / "v5.5-field-catalog.json").write_text(
        json.dumps([asdict(item) for item in catalog], indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report
