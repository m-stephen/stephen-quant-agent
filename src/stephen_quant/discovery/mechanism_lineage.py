from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from .proposal_generator import GeneratedProposal

MECHANISM_LINEAGE_VERSION = "9.0.0"


def _identity(level: str, payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            {"level": level, "payload": payload, "version": MECHANISM_LINEAGE_VERSION},
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()


@dataclass(frozen=True)
class ProposalLineage:
    proposal_id: str
    semantic_plan_id: str
    mechanism_family_id: str
    expression_variant_id: str
    parameter_variant_id: str
    policy_variant_id: str
    mechanism_family: str
    origin: str
    empirical_exposure: bool = False


@dataclass(frozen=True)
class FrozenProposalPacket:
    method_version: str
    proposal_ids: tuple[str, ...]
    lineages: tuple[ProposalLineage, ...]
    rejected_semantic_duplicates: tuple[str, ...]
    rejected_tombstones: tuple[str, ...]
    empirical_budget: int
    packet_sha256: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)


def _mechanism_family(item: GeneratedProposal) -> str:
    fields = set(item.schema.required_fields)
    sources = set(item.schema.data_sources)
    formula = item.schema.formula
    if {"net_inflow_amount", "amount", "close"} <= fields:
        return "flow_price_divergence"
    if "qd_auction" in sources and "qd_daily" in sources:
        return "auction_price_interaction"
    if "qd_margin" in sources and "qd_daily" in sources:
        return "margin_price_interaction"
    if "qd_chip" in sources and "qd_daily" in sources:
        return "chip_price_interaction"
    if len(sources) > 1:
        return "cross_source_" + "_".join(sorted(sources))
    if "relative_strength" in formula:
        return "relative_strength"
    if "max_drawdown" in formula or "volatility" in formula:
        return "price_path_risk"
    if "amihud" in formula:
        return "liquidity_impact"
    if "sma_ratio" in formula or "period_return" in formula:
        return "trend_or_reversal"
    return item.schema.event


def build_proposal_lineage(item: GeneratedProposal) -> ProposalLineage:
    family = _mechanism_family(item)
    semantic_plan = {
        "hypothesis": item.proposal.hypothesis.strip(),
        "research_form": item.proposal.research_form,
        "sources": item.schema.data_sources,
    }
    semantic_plan_id = _identity("semantic_plan", semantic_plan)
    family_id = _identity(
        "mechanism_family",
        {"semantic_plan_id": semantic_plan_id, "family": family},
    )
    expression_id = _identity(
        "expression_variant",
        {"family_id": family_id, "canonical_ast": item.typed.canonical_ast},
    )
    parameter_id = _identity(
        "parameter_variant",
        {
            "expression_id": expression_id,
            "lookback": item.typed.lookback_periods,
            "horizon": item.proposal.horizon,
        },
    )
    policy_id = _identity(
        "policy_variant",
        {"parameter_id": parameter_id, "direction": item.proposal.direction},
    )
    return ProposalLineage(
        item.proposal_id,
        semantic_plan_id,
        family_id,
        expression_id,
        parameter_id,
        policy_id,
        family,
        item.proposal.origin,
    )


def freeze_proposal_packet(
    proposals: tuple[GeneratedProposal, ...],
    *,
    empirical_budget: int,
    tombstoned_mechanism_family_ids: frozenset[str] = frozenset(),
    required_proposal_ids: frozenset[str] = frozenset(),
) -> FrozenProposalPacket:
    if empirical_budget < 1:
        raise ValueError("empirical budget must be positive")
    lineages = [build_proposal_lineage(item) for item in proposals]
    accepted: dict[str, ProposalLineage] = {}
    duplicates: list[str] = []
    tombstones: list[str] = []
    for item in sorted(lineages, key=lambda value: value.policy_variant_id):
        if item.mechanism_family_id in tombstoned_mechanism_family_ids:
            tombstones.append(item.proposal_id)
            continue
        if item.policy_variant_id in accepted:
            duplicates.append(item.proposal_id)
            continue
        accepted[item.policy_variant_id] = item
    available_by_proposal = {item.proposal_id: item for item in accepted.values()}
    missing_required = required_proposal_ids - set(available_by_proposal)
    if missing_required:
        raise ValueError(f"required frozen proposals are unavailable: {sorted(missing_required)}")
    required = [available_by_proposal[key] for key in sorted(required_proposal_ids)]
    selected = tuple(
        (
            required
            + [
                accepted[key]
                for key in sorted(accepted)
                if accepted[key].proposal_id not in required_proposal_ids
            ]
        )[:empirical_budget]
    )
    payload: dict[str, object] = {
        "method_version": MECHANISM_LINEAGE_VERSION,
        "proposal_ids": [item.proposal_id for item in selected],
        "lineages": [asdict(item) for item in selected],
        "rejected_semantic_duplicates": sorted(duplicates),
        "rejected_tombstones": sorted(tombstones),
        "empirical_budget": empirical_budget,
    }
    return FrozenProposalPacket(
        MECHANISM_LINEAGE_VERSION,
        tuple(item.proposal_id for item in selected),
        selected,
        tuple(sorted(duplicates)),
        tuple(sorted(tombstones)),
        empirical_budget,
        _identity("frozen_packet", payload),
    )
