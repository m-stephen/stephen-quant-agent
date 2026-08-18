from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

from stephen_quant.discovery.generator import (
    GenerationPlan,
    flow_stress_generation_plan,
    normalized_generation_plan,
    seed_generation_plan,
    v21_mechanism_generation_plan,
    v30_continuous_generation_plan,
    v30_epoch_five_generation_plan,
    v30_epoch_four_generation_plan,
    v30_epoch_three_generation_plan,
    v30_epoch_two_generation_plan,
)
from stephen_quant.discovery.models import FactorSchema

V43_VERSION = "v4.3-information-domain-breadth-1.0.0"
FORWARD_SHADOW_START = date(2026, 8, 19)
DOMAIN_ORDER = (
    "price",
    "auction",
    "fund_flow",
    "margin",
    "chip",
    "limit_event",
    "cross_source",
)
SOURCE_TO_DOMAIN = {
    "qd_daily": "price",
    "qd_auction": "auction",
    "qd_fund_flow": "fund_flow",
    "qd_margin": "margin",
    "qd_chip": "chip",
    "qd_limit_event": "limit_event",
}
PATH_KEYS = {
    "price": "qd_daily_dir",
    "auction": "qd_auction_dir",
    "fund_flow": "qd_fund_flow_dir",
    "margin": "qd_margin_dir",
    "chip": "qd_chip_dir",
    "limit_event": "qd_limit_event_dir",
}


def generation_plans() -> tuple[GenerationPlan, ...]:
    """Return every predeclared formula plan in historical creation order."""

    return (
        seed_generation_plan(),
        normalized_generation_plan(),
        v21_mechanism_generation_plan(),
        v30_continuous_generation_plan(),
        v30_epoch_two_generation_plan(),
        v30_epoch_three_generation_plan(),
        v30_epoch_four_generation_plan(),
        v30_epoch_five_generation_plan(),
        flow_stress_generation_plan(),
    )


def _schemas(plans: Iterable[GenerationPlan]) -> tuple[FactorSchema, ...]:
    result: list[FactorSchema] = []
    for plan in plans:
        plan.validate()
        for template in sorted(plan.templates, key=lambda item: item.template_id):
            for window in sorted(set(plan.windows)):
                for horizon in sorted(set(plan.horizons)):
                    result.append(template.render(window=window, horizon=horizon))
    return tuple(result)


def information_domain(schema: FactorSchema) -> str:
    alternatives = [SOURCE_TO_DOMAIN[item] for item in schema.data_sources if item != "qd_daily"]
    if len(alternatives) > 1:
        return "cross_source"
    return alternatives[0] if alternatives else "price"


@dataclass(frozen=True)
class DomainCandidate:
    schema_id: str
    fingerprint: str
    domain: str
    data_sources: tuple[str, ...]
    status: str
    duplicate_of: str | None
    reason: str | None


@dataclass(frozen=True)
class DomainCoverage:
    domain: str
    proposed: int
    unique: int
    admitted: int
    cross_source: int
    quota: int


@dataclass(frozen=True)
class SourceReadiness:
    domain: str
    path_key: str
    status: str
    files: int
    reason: str


@dataclass(frozen=True)
class V43BreadthReport:
    method_version: str
    proposed_candidates: int
    unique_candidates: int
    duplicate_candidates: int
    admitted_candidates: int
    semantic_domain_count: int
    coverage: tuple[DomainCoverage, ...]
    sources: tuple[SourceReadiness, ...]
    candidates: tuple[DomainCandidate, ...]
    deferred_domains: tuple[str, ...]
    retrospective_windows: tuple[str, ...]
    sealed_windows: tuple[str, ...]
    forward_shadow_start: str
    decision: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        lines = [
            "# V4.3 信息域广度审计" if zh else "# V4.3 Information-domain Breadth Audit",
            "",
            f"**{'结论' if zh else 'Decision'}: `{self.decision}`**",
            "",
            f"- {'原始候选' if zh else 'Raw proposals'}: {self.proposed_candidates}",
            f"- {'规范化唯一候选' if zh else 'Canonical unique candidates'}: {self.unique_candidates}",
            f"- {'分域准入候选' if zh else 'Domain-budget admissions'}: {self.admitted_candidates}",
            f"- {'独立信息域' if zh else 'Independent information domains'}: {self.semantic_domain_count}",
            f"- {'前向影子起始日' if zh else 'Forward shadow start'}: {self.forward_shadow_start}",
            "",
            f"## {'覆盖情况' if zh else 'Coverage'}",
            "",
            "| Domain | Proposed | Unique | Admitted | Cross-source | Quota |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        lines.extend(
            f"| {item.domain} | {item.proposed} | {item.unique} | {item.admitted} | "
            f"{item.cross_source} | {item.quota} |" for item in self.coverage
        )
        lines.extend([
            "",
            f"## {'数据就绪' if zh else 'Data readiness'}",
            "",
            "| Domain | Status | Files | Reason |",
            "|---|---|---:|---|",
        ])
        lines.extend(
            f"| {item.domain} | {item.status} | {item.files} | {item.reason} |"
            for item in self.sources
        )
        lines.extend([
            "",
            f"- {'延期域' if zh else 'Deferred domains'}: {', '.join(self.deferred_domains)}",
            f"- {'回顾性窗口' if zh else 'Retrospective windows'}: {', '.join(self.retrospective_windows)}",
            f"- {'封存窗口' if zh else 'Sealed windows'}: {', '.join(self.sealed_windows)}",
            "",
        ])
        return "\n".join(lines)


def build_domain_catalog(
    *,
    quotas: Mapping[str, int] | None = None,
    plans: Iterable[GenerationPlan] | None = None,
) -> tuple[tuple[DomainCandidate, ...], tuple[DomainCoverage, ...]]:
    quotas = dict(quotas or {domain: 24 for domain in DOMAIN_ORDER})
    if set(quotas) != set(DOMAIN_ORDER) or any(type(value) is not int or value < 1 for value in quotas.values()):
        raise ValueError("domain quotas must provide a positive integer for every domain")
    schemas = _schemas(plans or generation_plans())
    first_by_fingerprint: dict[str, str] = {}
    admitted: dict[str, int] = {domain: 0 for domain in DOMAIN_ORDER}
    candidates: list[DomainCandidate] = []
    for schema in schemas:
        domain = information_domain(schema)
        if domain not in admitted:
            raise ValueError(f"unsupported information domain: {domain}")
        duplicate_of = first_by_fingerprint.get(schema.fingerprint)
        if duplicate_of is not None:
            status, reason = "duplicate", "canonical fingerprint already proposed"
        else:
            first_by_fingerprint[schema.fingerprint] = schema.schema_id
            if admitted[domain] >= quotas[domain]:
                status, reason = "over_budget", "deterministic domain quota exhausted"
            else:
                status, reason = "admitted", None
                admitted[domain] += 1
        candidates.append(
            DomainCandidate(
                schema.schema_id,
                schema.fingerprint,
                domain,
                schema.data_sources,
                status,
                duplicate_of,
                reason,
            )
        )
    coverage = []
    for domain in DOMAIN_ORDER:
        rows = [item for item in candidates if item.domain == domain]
        coverage.append(
            DomainCoverage(
                domain,
                len(rows),
                sum(item.status != "duplicate" for item in rows),
                sum(item.status == "admitted" for item in rows),
                sum(len(item.data_sources) > 1 for item in rows),
                quotas[domain],
            )
        )
    return tuple(candidates), tuple(coverage)


def audit_source_readiness(paths: Mapping[str, Path]) -> tuple[SourceReadiness, ...]:
    result = []
    for domain in DOMAIN_ORDER[:-1]:
        key = PATH_KEYS[domain]
        source = paths.get(key)
        if source is None:
            result.append(SourceReadiness(domain, key, "UNCONFIGURED", 0, "local path not configured"))
            continue
        root = Path(source).expanduser().resolve()
        if not root.is_dir():
            result.append(SourceReadiness(domain, key, "MISSING", 0, "configured directory missing"))
            continue
        files = sum(1 for item in root.rglob("*") if item.is_file())
        status = "READY" if files else "EMPTY"
        reason = "read-only source present" if files else "directory contains no files"
        result.append(SourceReadiness(domain, key, status, files, reason))
    ready_components = [item for item in result[1:] if item.status == "READY"]
    result.append(
        SourceReadiness(
            "cross_source",
            "derived_from_component_paths",
            "READY" if len(ready_components) >= 2 else "UNAVAILABLE",
            sum(item.files for item in ready_components),
            "at least two alternative source domains ready"
            if len(ready_components) >= 2
            else "fewer than two alternative source domains ready",
        )
    )
    return tuple(result)


def run_v43_breadth_audit(
    paths: Mapping[str, Path], output_dir: str | Path, *, quotas: Mapping[str, int] | None = None
) -> V43BreadthReport:
    candidates, coverage = build_domain_catalog(quotas=quotas)
    sources = audit_source_readiness(paths)
    ready = {item.domain for item in sources if item.status == "READY"}
    admitted_domains = {item.domain for item in coverage if item.admitted and item.domain in ready}
    decision = "READY_FOR_BOUNDED_MULTI_DOMAIN_RESEARCH" if len(admitted_domains) >= 5 else "INSUFFICIENT_READY_DOMAINS"
    report = V43BreadthReport(
        V43_VERSION,
        len(candidates),
        sum(item.status != "duplicate" for item in candidates),
        sum(item.status == "duplicate" for item in candidates),
        sum(item.status == "admitted" for item in candidates),
        len(admitted_domains),
        coverage,
        sources,
        candidates,
        ("historical_industry_membership", "fundamental_pit", "news_and_research_text"),
        ("2022 discovery", "2023 confirmation", "2024 one-shot retrospective diagnostic"),
        ("2025", "2026 historical search"),
        FORWARD_SHADOW_START.isoformat(),
        decision,
    )
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "v4.3-domain-breadth.json").write_text(report.to_json() + "\n", encoding="utf-8")
    (output / "v4.3-domain-breadth.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (output / "v4.3-domain-breadth.en.md").write_text(report.to_markdown("en"), encoding="utf-8")
    return report


@dataclass(frozen=True)
class ForwardShadowRecord:
    operation_id: str
    observation_date: str
    recorded_at: str
    payload_sha256: str
    payload: dict[str, object]


class ForwardShadowLedger:
    """Append-only local paper evidence; it never places or simulates an order."""

    def __init__(self, root: str | Path, *, start: date = FORWARD_SHADOW_START) -> None:
        self.root = Path(root).expanduser().resolve()
        self.start = start

    def record(
        self,
        *,
        operation_id: str,
        observation_date: date,
        as_of: date,
        recorded_at: datetime,
        payload: Mapping[str, object],
    ) -> ForwardShadowRecord:
        if not operation_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in operation_id):
            raise ValueError("operation_id must contain only letters, digits, dash, or underscore")
        if observation_date < self.start:
            raise ValueError("observation predates the frozen forward-shadow start")
        if observation_date > as_of:
            raise ValueError("cannot record a future observation")
        if recorded_at.tzinfo is None:
            raise ValueError("recorded_at must include a timezone")
        canonical = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        record = ForwardShadowRecord(
            operation_id,
            observation_date.isoformat(),
            recorded_at.isoformat(),
            digest,
            dict(payload),
        )
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.root / f"{observation_date.isoformat()}--{operation_id}.json"
        with target.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(asdict(record), stream, indent=2, sort_keys=True, ensure_ascii=False)
            stream.write("\n")
        return record
