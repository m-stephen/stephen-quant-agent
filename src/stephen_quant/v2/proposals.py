from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Literal

from .compiler import ExpressionBlueprint
from .contracts import V2Hypothesis
from .replay import FrozenInteraction

ProposalMode = Literal["EXPLORE", "MUTATE"]


@dataclass(frozen=True)
class ConstrainedProposal:
    proposal_id: str
    mode: ProposalMode
    hypothesis: V2Hypothesis
    blueprint: ExpressionBlueprint
    parent_proposal_id: str | None = None
    mutated_dimension: str | None = None


class ConstrainedProposalQueue:
    """Deterministic queue: selection is allowlisted and mutation changes one dimension."""

    def __init__(self, blueprints: tuple[ExpressionBlueprint, ...], budget: int) -> None:
        if budget < 1:
            raise ValueError("proposal queue budget must be positive")
        ids = [item.blueprint_id for item in blueprints]
        if not blueprints or len(ids) != len(set(ids)):
            raise ValueError("proposal blueprints must be non-empty and unique")
        self._blueprints = tuple(sorted(blueprints, key=lambda item: item.blueprint_id))
        self._budget = budget
        self._items: list[ConstrainedProposal] = []

    @property
    def items(self) -> tuple[ConstrainedProposal, ...]:
        return tuple(self._items)

    def _append(
        self,
        mode: ProposalMode,
        hypothesis: V2Hypothesis,
        blueprint: ExpressionBlueprint,
        parent: str | None = None,
        dimension: str | None = None,
    ) -> ConstrainedProposal:
        if len(self._items) >= self._budget:
            raise ValueError("proposal queue budget exhausted")
        payload = {
            "mode": mode,
            "hypothesis_id": hypothesis.hypothesis_id,
            "blueprint_id": blueprint.blueprint_id,
            "parameters": blueprint.parameters,
            "parent": parent,
            "dimension": dimension,
            "sequence": len(self._items) + 1,
        }
        digest = hashlib.sha256(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()[:24]
        proposal = ConstrainedProposal(
            f"proposal_{digest}", mode, hypothesis, blueprint, parent, dimension
        )
        self._items.append(proposal)
        return proposal

    def explore(self, hypothesis: V2Hypothesis) -> ConstrainedProposal:
        matches = [item for item in self._blueprints if item.event == hypothesis.event]
        if len(matches) != 1:
            raise ValueError("explore requires exactly one allowlisted blueprint for event")
        return self._append("EXPLORE", hypothesis, matches[0])

    def mutate_lookback(
        self, parent: ConstrainedProposal, *, parameter: str, value: int
    ) -> ConstrainedProposal:
        parameters = dict(parent.blueprint.parameters)
        if parameter not in parameters or value < 1 or parameters[parameter] == value:
            raise ValueError("mutation must change exactly one existing positive lookback")
        parameters[parameter] = value
        mutated = replace(parent.blueprint, parameters=tuple(sorted(parameters.items())))
        return self._append(
            "MUTATE", parent.hypothesis, mutated, parent.proposal_id, f"parameter:{parameter}"
        )


@dataclass(frozen=True)
class FrozenProposalSelection:
    event: str
    blueprint_id: str
    parameters: tuple[tuple[str, int], ...]
    response_sha256: str


def replay_frozen_selection(interaction: FrozenInteraction) -> FrozenProposalSelection:
    """Parse recorded bytes only; this function has no model or network callback."""

    interaction.validate()
    try:
        payload = json.loads(interaction.raw_output)
        event = str(payload["event"])
        blueprint_id = str(payload["blueprint_id"])
        parameters = tuple(
            sorted((str(key), int(value)) for key, value in payload["parameters"].items())
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError("frozen proposal selection is invalid") from exc
    return FrozenProposalSelection(event, blueprint_id, parameters, interaction.output_sha256)
