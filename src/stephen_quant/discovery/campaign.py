from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from stephen_quant.integrity.registry import ExperimentRegistry

from .models import CampaignBudget, FactorSchema


@dataclass(frozen=True)
class CampaignSpec:
    name: str
    experiment_id: str
    budget: CampaignBudget
    horizons: tuple[str, ...]
    ranking_metric: str
    stopping_rule: str
    sealed_windows: tuple[str, ...]

    def to_json(self) -> str:
        self.budget.validate()
        if not self.name.strip() or not self.ranking_metric.strip() or not self.stopping_rule.strip():
            raise ValueError("campaign specification contains empty required text")
        if not self.horizons or not self.sealed_windows:
            raise ValueError("campaign horizons and sealed windows cannot be empty")
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)


class SearchCampaign:
    """Bounded proposal ledger that records duplicates before empirical evaluation."""

    def __init__(
        self,
        registry: ExperimentRegistry,
        spec: CampaignSpec,
        *,
        campaign_id: str | None = None,
    ) -> None:
        self.registry = registry
        self.spec = spec
        self.campaign_id = campaign_id or registry.create_research_campaign(
            experiment_id=spec.experiment_id,
            name=spec.name,
            schema_budget=spec.budget.schema,
            cpcv_budget=spec.budget.cpcv,
            execution_budget=spec.budget.execution,
            specification_json=spec.to_json(),
        )
        self._seen = registry.campaign_fingerprints(self.campaign_id)

    def propose(self, schema: FactorSchema) -> tuple[bool, str, int]:
        fingerprint = schema.fingerprint
        duplicate_of = self._seen.get(fingerprint)
        decision = "duplicate" if duplicate_of is not None else "generated"
        reason = None if duplicate_of is None else f"duplicate of {duplicate_of}"
        proposal_id, number = self.registry.record_campaign_proposal(
            campaign_id=self.campaign_id,
            fingerprint=fingerprint,
            schema_json=schema.to_json(),
            decision=decision,
            reason=reason,
        )
        if duplicate_of is None:
            self._seen[fingerprint] = proposal_id
        return duplicate_of is None, proposal_id, number

    def summary(self) -> dict[str, object]:
        return self.registry.campaign_summary(self.campaign_id)
