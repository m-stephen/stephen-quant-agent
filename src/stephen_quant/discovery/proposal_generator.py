from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from itertools import pairwise
from pathlib import Path
from typing import Literal

from stephen_quant.research_agent.dsl import analyze_formula

from .models import SOURCE_FIELDS, FactorSchema, PredictionHorizon
from .semantic_catalog import (
    FieldSemantic,
    ResearchForm,
    build_semantic_catalog,
    route_factor_schema,
)
from .typed_dsl import TypedFormulaAnalysis, type_check_schema

PROPOSAL_GENERATOR_VERSION = "5.7.0"
ProposalOrigin = Literal["symbolic", "llm"]


@dataclass(frozen=True)
class ProposalSpec:
    formula: str
    hypothesis: str
    research_form: ResearchForm
    horizon: PredictionHorizon
    direction: Literal[-1, 1]
    origin: ProposalOrigin
    provider_id: str


@dataclass(frozen=True)
class GeneratedProposal:
    proposal_id: str
    proposal: ProposalSpec
    schema: FactorSchema
    typed: TypedFormulaAnalysis

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)


def _proposal_id(spec: ProposalSpec) -> str:
    analysis = analyze_formula(spec.formula)
    payload = {
        "canonical_ast": analysis.canonical_ast,
        "direction": spec.direction,
        "horizon": spec.horizon,
        "research_form": spec.research_form,
    }
    return hashlib.sha256(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()).hexdigest()


def _field_sources(fields: tuple[str, ...]) -> tuple[str, ...]:
    sources = tuple(
        sorted(source for source, available in SOURCE_FIELDS.items() if set(fields) & available)
    )
    unresolved = sorted(set(fields) - set().union(*(SOURCE_FIELDS[source] for source in sources)))
    if unresolved:
        raise ValueError(f"proposal fields have no source: {unresolved}")
    return sources


def compile_proposal(spec: ProposalSpec) -> GeneratedProposal:
    if not spec.hypothesis.strip() or not spec.provider_id.strip():
        raise ValueError("proposal hypothesis and provider_id are required")
    if spec.origin == "llm" and not spec.provider_id.startswith("llm:"):
        raise ValueError("LLM proposals require a provider_id prefixed with llm:")
    analysis = analyze_formula(spec.formula.strip())
    proposal_id = _proposal_id(spec)
    schema = FactorSchema(
        schema_id=f"auto_{proposal_id[:20]}",
        version="5.7.0",
        name=f"Automatic proposal {proposal_id[:12]}",
        event=f"automatic_{spec.research_form}",
        context="label_free_proposal_generation",
        quality=f"origin={spec.origin};provider={spec.provider_id}",
        direction=spec.direction,
        output="typed_factor_score",
        horizon=spec.horizon,
        formula=spec.formula.strip(),
        data_sources=_field_sources(analysis.required_fields),
        required_fields=analysis.required_fields,
        availability_lag_days=0 if "qd_auction" in _field_sources(analysis.required_fields) else 1,
        economic_rationale=spec.hypothesis.strip(),
    )
    route = route_factor_schema(schema, requested_form=spec.research_form)
    typed = type_check_schema(schema, route=route)
    return GeneratedProposal(proposal_id, spec, schema, typed)


def _symbolic_specs(
    catalog: tuple[FieldSemantic, ...],
    *,
    lookbacks: tuple[int, ...],
    include_inverse: bool,
) -> tuple[ProposalSpec, ...]:
    specs: list[ProposalSpec] = []

    def add(
        formula: str,
        hypothesis: str,
        research_form: ResearchForm,
        provider_id: str,
    ) -> None:
        for direction in ((1, -1) if include_inverse else (1,)):
            specs.append(
                ProposalSpec(
                    formula,
                    hypothesis,
                    research_form,
                    "5d",
                    direction,
                    "symbolic",
                    provider_id,
                )
            )

    for item in catalog:
        if "continuous_ranking" in item.allowed_forms and item.value_type == "continuous":
            for lookback in lookbacks:
                add(
                    f"mean({item.field}, {lookback})",
                    f"The trailing level of {item.field} may rank subsequent returns.",
                    "continuous_ranking",
                    "symbolic:field-level",
                )
                add(
                    f"sma_ratio({item.field}, {max(1, lookback // 4)}, {lookback})",
                    f"The trend state of {item.field} may persist or mean-revert.",
                    "continuous_ranking",
                    "symbolic:field-trend",
                )
                if item.source == "qd_daily" and item.field == "close":
                    add(
                        f"period_return(close, {lookback})",
                        "Trailing price return may continue or reverse over the next horizon.",
                        "continuous_ranking",
                        "symbolic:price-return",
                    )
                    add(
                        f"volatility(close, {lookback})",
                        "Realized volatility may proxy risk appetite or a volatility premium.",
                        "continuous_ranking",
                        "symbolic:price-risk",
                    )
        if "event_study" in item.allowed_forms:
            add(
                f"mean({item.field}, {lookbacks[0]})",
                f"The {item.field} state may condition a sparse event response.",
                "event_study",
                "symbolic:event-level",
            )
    same_unit: dict[str, list[FieldSemantic]] = {}
    for item in catalog:
        if "continuous_ranking" in item.allowed_forms:
            same_unit.setdefault(item.unit, []).append(item)
    for unit, items in sorted(same_unit.items()):
        if unit == "binary":
            continue
        for left, right in pairwise(items):
            add(
                f"mean({left.field}, {lookbacks[0]}) / (mean({right.field}, {lookbacks[0]}) + 1)",
                f"The normalized imbalance between {left.field} and {right.field} may proxy pressure.",
                "continuous_ranking",
                "symbolic:same-unit-ratio",
            )
    return tuple(specs)


def generate_symbolic_proposals(
    *,
    budget: int = 256,
    lookbacks: tuple[int, ...] = (5, 20, 60),
    include_inverse: bool = False,
) -> tuple[GeneratedProposal, ...]:
    if budget < 1:
        raise ValueError("proposal budget must be positive")
    if not lookbacks or any(value < 2 or value > 252 for value in lookbacks):
        raise ValueError("symbolic lookbacks must be between 2 and 252")
    unique: dict[str, GeneratedProposal] = {}
    for spec in _symbolic_specs(
        build_semantic_catalog(), lookbacks=lookbacks, include_inverse=include_inverse
    ):
        try:
            item = compile_proposal(spec)
        except (ValueError, TypeError):
            continue
        unique.setdefault(item.proposal_id, item)
    return tuple(unique[key] for key in sorted(unique)[:budget])


def generate_structural_proposals(
    *,
    budget: int = 512,
    lookbacks: tuple[int, ...] = (3, 5, 10, 20, 60),
    horizons: tuple[PredictionHorizon, ...] = ("1d", "5d", "20d"),
    include_inverse: bool = True,
) -> tuple[GeneratedProposal, ...]:
    """Generate a label-free, mechanism-diverse V9 proposal packet.

    Unlike the legacy field enumerator, this grammar predeclares economic interactions.  It never
    reads labels and varies only bounded lookback, horizon and direction policy dimensions.
    Invalid source/form/unit combinations are rejected by the existing typed compiler.
    """

    if budget < 1:
        raise ValueError("proposal budget must be positive")
    if not lookbacks or any(value < 2 or value > 252 for value in lookbacks):
        raise ValueError("structural lookbacks must be between 2 and 252")
    if not horizons or len(set(horizons)) != len(horizons):
        raise ValueError("structural horizons must be non-empty and unique")
    specs: list[ProposalSpec] = []

    def add(
        formula: str,
        hypothesis: str,
        research_form: ResearchForm,
        provider_id: str,
    ) -> None:
        for horizon in horizons:
            for direction in ((1, -1) if include_inverse else (1,)):
                specs.append(
                    ProposalSpec(
                        formula,
                        hypothesis,
                        research_form,
                        horizon,
                        direction,
                        "symbolic",
                        provider_id,
                    )
                )

    for lookback in lookbacks:
        short = max(2, lookback // 4)
        if short >= lookback:
            short = lookback - 1
        add(
            f"relative_strength(close, benchmark_close, {lookback})",
            "Stock return relative to the contemporaneously observable market path may persist or reverse.",
            "continuous_ranking",
            "symbolic:relative-strength",
        )
        add(
            f"max_drawdown(close, {lookback})",
            "Recent path damage may proxy forced selling, recovery optionality or persistent risk.",
            "continuous_ranking",
            "symbolic:path-damage",
        )
        add(
            f"amihud(close, amount, {lookback})",
            "Return impact per traded amount may expose a priced liquidity state.",
            "continuous_ranking",
            "symbolic:liquidity-impact",
        )
        add(
            f"sma_ratio(turnover, {short}, {lookback}) - period_return(close, {lookback})",
            "Turnover acceleration without matching price response may precede repricing.",
            "continuous_ranking",
            "symbolic:turnover-price-divergence",
        )
        add(
            f"mean(net_inflow_amount, {lookback}) / (mean(amount, {lookback}) + 1) "
            f"- period_return(close, {lookback})",
            "Normalized buying pressure may arrive before price fully incorporates demand.",
            "continuous_ranking",
            "symbolic:flow-price-divergence",
        )
        add(
            f"(mean(large_buy_amount, {lookback}) - mean(large_sell_amount, {lookback})) "
            f"/ (mean(amount, {lookback}) + 1)",
            "Large-order composition may reveal persistent informed demand or crowded flow.",
            "continuous_ranking",
            "symbolic:flow-composition",
        )
        add(
            f"(mean(margin_financing_buy, {lookback}) - mean(margin_financing_repay, {lookback})) "
            f"/ (mean(margin_financing_balance, {lookback}) + 1) "
            f"- period_return(close, {lookback})",
            "Leveraged demand growth that is not yet reflected in price may precede adjustment.",
            "continuous_ranking",
            "symbolic:margin-price-divergence",
        )
        add(
            f"(mean(close, {lookback}) - mean(chip_weighted_cost, {lookback})) "
            f"/ (mean(close, {lookback}) + 1)",
            "Distance from observed holder cost may proxy supply overhang or trend confirmation.",
            "continuous_ranking",
            "symbolic:chip-price-location",
        )
        add(
            f"mean(auction_return, {short}) - period_return(close, {short})",
            "Opening-auction repricing relative to the recent close path may identify overnight information.",
            "event_study",
            "symbolic:auction-price-interaction",
        )
    unique: dict[str, GeneratedProposal] = {}
    for spec in specs:
        try:
            item = compile_proposal(spec)
        except (ValueError, TypeError):
            continue
        unique.setdefault(item.proposal_id, item)
    return tuple(unique[key] for key in sorted(unique)[:budget])


def load_llm_proposals(path: str | Path, *, provider_id: str) -> tuple[GeneratedProposal, ...]:
    if not provider_id.startswith("llm:"):
        raise ValueError("provider_id must begin with llm:")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise TypeError("LLM proposal packet must be a JSON list")
    expected = {"formula", "hypothesis", "research_form", "horizon", "direction"}
    unique: dict[str, GeneratedProposal] = {}
    for index, row in enumerate(payload):
        if not isinstance(row, dict) or set(row) != expected:
            raise ValueError(f"LLM proposal {index} must contain exactly {sorted(expected)}")
        spec = ProposalSpec(
            formula=str(row["formula"]),
            hypothesis=str(row["hypothesis"]),
            research_form=row["research_form"],
            horizon=row["horizon"],
            direction=row["direction"],
            origin="llm",
            provider_id=provider_id,
        )
        item = compile_proposal(spec)
        unique.setdefault(item.proposal_id, item)
    return tuple(unique[key] for key in sorted(unique))


def load_cached_llm_proposals(
    path: str | Path,
    *,
    provider_id: str,
    expected_sha256: str,
) -> tuple[GeneratedProposal, ...]:
    """Replay a frozen LLM proposal packet without a network or label-dependent call."""

    source = Path(path)
    actual = hashlib.sha256(source.read_bytes()).hexdigest()
    if actual != expected_sha256:
        raise ValueError("cached LLM proposal packet hash mismatch")
    return load_llm_proposals(source, provider_id=provider_id)


def merge_proposals(*groups: tuple[GeneratedProposal, ...], budget: int) -> tuple[GeneratedProposal, ...]:
    if budget < 1:
        raise ValueError("proposal budget must be positive")
    unique: dict[str, GeneratedProposal] = {}
    for item in (proposal for group in groups for proposal in group):
        unique.setdefault(item.proposal_id, item)
    return tuple(unique[key] for key in sorted(unique)[:budget])
