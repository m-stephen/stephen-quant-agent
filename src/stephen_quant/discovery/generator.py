from __future__ import annotations

from dataclasses import dataclass
from itertools import product

from .campaign import SearchCampaign
from .models import FactorSchema, PredictionHorizon


@dataclass(frozen=True)
class FactorTemplate:
    template_id: str
    name: str
    event: str
    context: str
    quality: str
    output: str
    formula_template: str
    required_fields: tuple[str, ...]
    data_sources: tuple[str, ...]
    direction: int
    economic_rationale: str

    def render(self, *, window: int, horizon: PredictionHorizon) -> FactorSchema:
        if window < 1:
            raise ValueError("template window must be positive")
        formula = self.formula_template.format(window=window)
        return FactorSchema(
            schema_id=f"{self.template_id}_{window}_{horizon}",
            version="1.0.0",
            name=f"{self.name} ({window}, {horizon})",
            event=self.event,
            context=self.context,
            quality=self.quality,
            direction=self.direction,  # type: ignore[arg-type]
            output=self.output,
            horizon=horizon,
            formula=formula,
            data_sources=self.data_sources,
            required_fields=self.required_fields,
            availability_lag_days=0,
            economic_rationale=self.economic_rationale,
        )


@dataclass(frozen=True)
class GenerationPlan:
    templates: tuple[FactorTemplate, ...]
    windows: tuple[int, ...]
    horizons: tuple[PredictionHorizon, ...]

    def validate(self) -> None:
        if not self.templates or not self.windows or not self.horizons:
            raise ValueError("generation plan dimensions cannot be empty")
        if any(window < 1 for window in self.windows):
            raise ValueError("generation windows must be positive")
        template_ids = [template.template_id for template in self.templates]
        if len(set(template_ids)) != len(template_ids):
            raise ValueError("generation template ids must be unique")


@dataclass(frozen=True)
class GeneratedCandidate:
    schema: FactorSchema
    proposal_id: str
    proposal_number: int
    unique: bool


def generate_candidates(
    campaign: SearchCampaign, plan: GenerationPlan
) -> tuple[GeneratedCandidate, ...]:
    """Enumerate a frozen search space deterministically and record every proposal."""

    plan.validate()
    generated: list[GeneratedCandidate] = []
    ordered_templates = sorted(plan.templates, key=lambda item: item.template_id)
    for template, window, horizon in product(
        ordered_templates, sorted(set(plan.windows)), sorted(set(plan.horizons))
    ):
        schema = template.render(window=window, horizon=horizon)
        unique, proposal_id, proposal_number = campaign.propose(schema)
        generated.append(
            GeneratedCandidate(
                schema=schema,
                proposal_id=proposal_id,
                proposal_number=proposal_number,
                unique=unique,
            )
        )
    return tuple(generated)


def seed_generation_plan() -> GenerationPlan:
    """Simple baselines used before LLM- or alternative-data-generated candidates."""

    return GenerationPlan(
        templates=(
            FactorTemplate(
                template_id="price_momentum",
                name="Price momentum",
                event="price",
                context="all_market",
                quality="complete_daily_bars",
                output="cross_sectional_score",
                formula_template="period_return(close, {window})",
                required_fields=("close",),
                data_sources=("qd_daily",),
                direction=1,
                economic_rationale="Underreaction may create medium-horizon continuation.",
            ),
            FactorTemplate(
                template_id="price_reversal",
                name="Price reversal",
                event="price",
                context="all_market",
                quality="complete_daily_bars",
                output="cross_sectional_score",
                formula_template="period_return(close, {window})",
                required_fields=("close",),
                data_sources=("qd_daily",),
                direction=-1,
                economic_rationale="Liquidity pressure may create short-horizon reversal.",
            ),
            FactorTemplate(
                template_id="risk_adjusted_momentum",
                name="Risk-adjusted momentum",
                event="price_risk",
                context="all_market",
                quality="positive_prices",
                output="cross_sectional_score",
                formula_template=(
                    "period_return(close, {window}) / "
                    "(volatility(close, {window}) + 0.000001)"
                ),
                required_fields=("close",),
                data_sources=("qd_daily",),
                direction=1,
                economic_rationale="Continuation should be discounted when realized risk is high.",
            ),
            FactorTemplate(
                template_id="fund_flow_pressure",
                name="Net fund-flow pressure",
                event="fund_flow",
                context="all_market",
                quality="point_in_time_fund_flow",
                output="cross_sectional_score",
                formula_template="mean(net_inflow_amount, {window})",
                required_fields=("net_inflow_amount",),
                data_sources=("qd_fund_flow",),
                direction=1,
                economic_rationale="Persistent net buying may reveal informed demand.",
            ),
            FactorTemplate(
                template_id="auction_strength",
                name="Opening-auction strength",
                event="auction",
                context="pre_open",
                quality="point_in_time_auction",
                output="cross_sectional_score",
                formula_template="mean(auction_return, {window})",
                required_fields=("auction_return",),
                data_sources=("qd_auction",),
                direction=1,
                economic_rationale="Persistent auction strength may reveal overnight demand.",
            ),
            FactorTemplate(
                template_id="margin_financing_demand",
                name="Margin financing demand",
                event="margin",
                context="all_market",
                quality="point_in_time_margin",
                output="cross_sectional_score",
                formula_template=(
                    "mean(margin_financing_buy, {window}) / "
                    "mean(margin_financing_balance, {window})"
                ),
                required_fields=("margin_financing_balance", "margin_financing_buy"),
                data_sources=("qd_margin",),
                direction=1,
                economic_rationale="Financing purchases relative to balance proxy leveraged demand.",
            ),
        ),
        windows=(5, 20, 60),
        horizons=("next_open", "5d", "20d"),
    )
