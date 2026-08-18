from __future__ import annotations

from dataclasses import dataclass, replace
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
                    "period_return(close, {window}) / (volatility(close, {window}) + 0.000001)"
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


def normalized_generation_plan() -> GenerationPlan:
    """V1.8.17 hypotheses normalized by liquidity and combined across sources."""

    return GenerationPlan(
        templates=(
            *seed_generation_plan().templates[:3],
            FactorTemplate(
                template_id="fund_flow_intensity",
                name="ADV-normalized fund-flow intensity",
                event="fund_flow_liquidity",
                context="market_neutral_cross_section",
                quality="point_in_time_fund_flow_and_daily_bars",
                output="cross_sectional_score",
                formula_template=(
                    "mean(net_inflow_amount, {window}) / (mean(amount, {window}) + 1.0)"
                ),
                required_fields=("amount", "net_inflow_amount"),
                data_sources=("qd_daily", "qd_fund_flow"),
                direction=1,
                economic_rationale="Net demand is comparable only after scaling by traded value.",
            ),
            FactorTemplate(
                template_id="large_flow_intensity",
                name="ADV-normalized large-order imbalance",
                event="large_order_flow",
                context="market_neutral_cross_section",
                quality="point_in_time_fund_flow_and_daily_bars",
                output="cross_sectional_score",
                formula_template=(
                    "(mean(large_buy_amount, {window}) - "
                    "mean(large_sell_amount, {window})) / "
                    "(mean(amount, {window}) + 1.0)"
                ),
                required_fields=("amount", "large_buy_amount", "large_sell_amount"),
                data_sources=("qd_daily", "qd_fund_flow"),
                direction=1,
                economic_rationale="Large-order imbalance may proxy informed demand.",
            ),
            FactorTemplate(
                template_id="extra_large_flow_intensity",
                name="ADV-normalized extra-large-order imbalance",
                event="extra_large_order_flow",
                context="market_neutral_cross_section",
                quality="point_in_time_fund_flow_and_daily_bars",
                output="cross_sectional_score",
                formula_template=(
                    "(mean(extra_large_buy_amount, {window}) - "
                    "mean(extra_large_sell_amount, {window})) / "
                    "(mean(amount, {window}) + 1.0)"
                ),
                required_fields=(
                    "amount",
                    "extra_large_buy_amount",
                    "extra_large_sell_amount",
                ),
                data_sources=("qd_daily", "qd_fund_flow"),
                direction=1,
                economic_rationale="The largest orders may contain stronger information.",
            ),
            FactorTemplate(
                template_id="flow_price_divergence",
                name="Fund-flow versus price divergence",
                event="flow_price_divergence",
                context="market_neutral_cross_section",
                quality="point_in_time_fund_flow_and_daily_bars",
                output="cross_sectional_score",
                formula_template=(
                    "mean(net_inflow_amount, {window}) / "
                    "(mean(amount, {window}) + 1.0) - period_return(close, {window})"
                ),
                required_fields=("amount", "close", "net_inflow_amount"),
                data_sources=("qd_daily", "qd_fund_flow"),
                direction=1,
                economic_rationale="Buying pressure without price response may reveal underreaction.",
            ),
            FactorTemplate(
                template_id="margin_buy_intensity",
                name="ADV-normalized financing demand",
                event="margin_financing",
                context="market_neutral_cross_section",
                quality="point_in_time_margin_and_daily_bars",
                output="cross_sectional_score",
                formula_template=(
                    "mean(margin_financing_buy, {window}) / (mean(amount, {window}) + 1.0)"
                ),
                required_fields=("amount", "margin_financing_buy"),
                data_sources=("qd_daily", "qd_margin"),
                direction=1,
                economic_rationale="Financing demand is scaled by normal market liquidity.",
            ),
            FactorTemplate(
                template_id="margin_balance_surprise",
                name="Net financing-flow intensity",
                event="margin_balance_change",
                context="market_neutral_cross_section",
                quality="point_in_time_margin_and_daily_bars",
                output="cross_sectional_score",
                formula_template=(
                    "(mean(margin_financing_buy, {window}) - "
                    "mean(margin_financing_repay, {window})) / "
                    "(mean(amount, {window}) + 1.0)"
                ),
                required_fields=(
                    "amount",
                    "margin_financing_buy",
                    "margin_financing_repay",
                ),
                data_sources=("qd_daily", "qd_margin"),
                direction=1,
                economic_rationale="Net leveraged buying may lead price adjustment.",
            ),
            FactorTemplate(
                template_id="auction_liquidity_strength",
                name="Auction return and liquidity interaction",
                event="opening_auction",
                context="pre_open_market_neutral_cross_section",
                quality="same_day_point_in_time_auction",
                output="cross_sectional_score",
                formula_template=(
                    "mean(auction_return, {window}) * mean(auction_volume_ratio_1, {window})"
                ),
                required_fields=("auction_return", "auction_volume_ratio_1"),
                data_sources=("qd_auction",),
                direction=1,
                economic_rationale="Price moves backed by auction liquidity should be more credible.",
            ),
            FactorTemplate(
                template_id="auction_amount_intensity",
                name="ADV-normalized opening-auction amount",
                event="opening_auction_liquidity",
                context="pre_open_market_neutral_cross_section",
                quality="same_day_auction_and_prior_daily_bars",
                output="cross_sectional_score",
                formula_template=(
                    "mean(auction_amount, {window}) / (mean(amount, {window}) + 1.0)"
                ),
                required_fields=("amount", "auction_amount"),
                data_sources=("qd_daily", "qd_auction"),
                direction=1,
                economic_rationale="Auction demand is scaled by the stock's normal traded value.",
            ),
        ),
        windows=(5, 20, 60),
        horizons=("next_open", "5d", "20d"),
    )


def v21_mechanism_generation_plan() -> GenerationPlan:
    """V2.1 bounded mechanism search over complementary QD sources.

    Each template is a distinct economic hypothesis. Window changes are the only
    permitted mutation inside a family, which keeps multiplicity explicit.
    """

    daily = seed_generation_plan().templates[:3]
    normalized = normalized_generation_plan().templates[3:]
    return GenerationPlan(
        templates=(
            *daily,
            *normalized,
            FactorTemplate(
                template_id="flow_confirmation",
                name="Flow-confirmed momentum",
                event="flow_price_confirmation",
                context="market_neutral_cross_section",
                quality="point_in_time_fund_flow_and_daily_bars",
                output="cross_sectional_score",
                formula_template=(
                    "mean(net_inflow_amount, {window}) / "
                    "(mean(amount, {window}) + 1.0) * "
                    "period_return(close, {window})"
                ),
                required_fields=("amount", "close", "net_inflow_amount"),
                data_sources=("qd_daily", "qd_fund_flow"),
                direction=1,
                economic_rationale="Demand backed by price continuation may be more persistent.",
            ),
            FactorTemplate(
                template_id="margin_flow_confirmation",
                name="Financing and cash-flow confirmation",
                event="leveraged_cash_demand",
                context="market_neutral_cross_section",
                quality="point_in_time_margin_fund_flow_and_daily_bars",
                output="cross_sectional_score",
                formula_template=(
                    "mean(margin_financing_buy, {window}) / "
                    "(mean(amount, {window}) + 1.0) + "
                    "mean(net_inflow_amount, {window}) / "
                    "(mean(amount, {window}) + 1.0)"
                ),
                required_fields=("amount", "margin_financing_buy", "net_inflow_amount"),
                data_sources=("qd_daily", "qd_fund_flow", "qd_margin"),
                direction=1,
                economic_rationale="Independent leveraged and cash demand may jointly signal informed buying.",
            ),
        ),
        windows=(5, 20),
        horizons=("20d",),
    )


def v30_continuous_generation_plan() -> GenerationPlan:
    """Issue #100 epoch-one mechanisms with no post-result mutation surface."""

    common = {
        "context": "market_neutral_cross_section",
        "quality": "point_in_time_multisource_and_daily_bars",
        "output": "cross_sectional_score",
        "direction": 1,
    }
    return GenerationPlan(
        templates=(
            FactorTemplate(
                template_id="margin_demand_acceleration_5_20",
                name="Financing-demand acceleration",
                event="margin_demand_acceleration",
                formula_template=(
                    "mean(margin_financing_buy, 5) / (mean(amount, 5) + 1.0) - "
                    "mean(margin_financing_buy, 20) / (mean(amount, 20) + 1.0)"
                ),
                required_fields=("amount", "margin_financing_buy"),
                data_sources=("qd_daily", "qd_margin"),
                economic_rationale=(
                    "A recent acceleration in leveraged demand may precede delayed price pressure."
                ),
                **common,
            ),
            FactorTemplate(
                template_id="leveraged_informed_acceleration_5_20",
                name="Leveraged and extra-large demand acceleration",
                event="cross_source_demand_acceleration",
                formula_template=(
                    "mean(margin_financing_buy, 5) / (mean(amount, 5) + 1.0) - "
                    "mean(margin_financing_buy, 20) / (mean(amount, 20) + 1.0) + "
                    "(mean(extra_large_buy_amount, 5) - mean(extra_large_sell_amount, 5)) / "
                    "(mean(amount, 5) + 1.0) - "
                    "(mean(extra_large_buy_amount, 20) - mean(extra_large_sell_amount, 20)) / "
                    "(mean(amount, 20) + 1.0)"
                ),
                required_fields=(
                    "amount",
                    "margin_financing_buy",
                    "extra_large_buy_amount",
                    "extra_large_sell_amount",
                ),
                data_sources=("qd_daily", "qd_fund_flow", "qd_margin"),
                economic_rationale=(
                    "Independent acceleration in leveraged and very-large cash demand may identify informed buying."
                ),
                **common,
            ),
            FactorTemplate(
                template_id="auction_price_absorption_5",
                name="Auction pressure versus prior price movement",
                event="auction_price_absorption",
                formula_template="mean(auction_return, 5) - period_return(close, 5)",
                required_fields=("auction_return", "close"),
                data_sources=("qd_daily", "qd_auction"),
                economic_rationale=(
                    "Auction demand that exceeds the recent close-to-close move may reveal delayed price incorporation."
                ),
                **common,
            ),
        ),
        windows=(20,),
        horizons=("20d",),
    )


def v30_epoch_two_generation_plan() -> GenerationPlan:
    """Issue #100 epoch-two mechanisms, frozen after epoch one was tombstoned."""

    common = {
        "context": "market_neutral_cross_section",
        "quality": "point_in_time_multisource_and_daily_bars",
        "output": "cross_sectional_score",
    }
    return GenerationPlan(
        templates=(
            FactorTemplate(
                template_id="liquidity_stress_reversal_20",
                name="Temporary liquidity-stress premium",
                event="liquidity_stress_reversal",
                formula_template="amihud(close, amount, 20)",
                required_fields=("amount", "close"),
                data_sources=("qd_daily",),
                direction=1,
                economic_rationale=(
                    "Temporary price impact may command subsequent reversal compensation."
                ),
                **common,
            ),
            FactorTemplate(
                template_id="margin_crowding_reversal_20",
                name="Leveraged price-crowding reversal",
                event="margin_crowding_reversal",
                formula_template=(
                    "period_return(margin_financing_balance, 20) * period_return(close, 20)"
                ),
                required_fields=("close", "margin_financing_balance"),
                data_sources=("qd_daily", "qd_margin"),
                direction=-1,
                economic_rationale=(
                    "Price continuation accompanied by rapidly rising financing may become crowded and unwind."
                ),
                **common,
            ),
            FactorTemplate(
                template_id="cash_absorbs_deleveraging_5_20",
                name="Cash demand absorbing leveraged retrenchment",
                event="cash_absorbs_deleveraging",
                formula_template=(
                    "(mean(extra_large_buy_amount, 5) - mean(extra_large_sell_amount, 5)) / "
                    "(mean(amount, 5) + 1.0) - "
                    "(mean(extra_large_buy_amount, 20) - mean(extra_large_sell_amount, 20)) / "
                    "(mean(amount, 20) + 1.0) - "
                    "(mean(margin_financing_buy, 5) / (mean(amount, 5) + 1.0) - "
                    "mean(margin_financing_buy, 20) / (mean(amount, 20) + 1.0))"
                ),
                required_fields=(
                    "amount",
                    "extra_large_buy_amount",
                    "extra_large_sell_amount",
                    "margin_financing_buy",
                ),
                data_sources=("qd_daily", "qd_fund_flow", "qd_margin"),
                direction=1,
                economic_rationale=(
                    "Accelerating very-large cash demand may absorb a relative slowdown in leveraged demand."
                ),
                **common,
            ),
        ),
        windows=(20,),
        horizons=("20d",),
    )


def v30_epoch_three_generation_plan() -> GenerationPlan:
    """Issue #100 epoch-three chip-distribution mechanisms."""

    common = {
        "context": "market_neutral_cross_section",
        "quality": "end_of_day_chip_distribution_and_daily_bars",
        "output": "cross_sectional_score",
        "data_sources": ("qd_daily", "qd_chip"),
    }
    return GenerationPlan(
        templates=(
            FactorTemplate(
                template_id="chip_cost_gap_reversal_5",
                name="Holder cost-gap reversal",
                event="chip_cost_gap_reversal",
                formula_template=(
                    "mean(close, 5) / (mean(chip_weighted_cost, 5) + 1.0) - 1.0"
                ),
                required_fields=("chip_weighted_cost", "close"),
                direction=-1,
                economic_rationale=(
                    "Price far above the observed holder cost basis may face profit-taking."
                ),
                **common,
            ),
            FactorTemplate(
                template_id="chip_profit_crowding_reversal_5",
                name="Profitable-holder crowding reversal",
                event="chip_profit_crowding_reversal",
                formula_template=(
                    "mean(chip_win_rate, 5) * "
                    "(mean(close, 5) / (mean(chip_weighted_cost, 5) + 1.0) - 1.0)"
                ),
                required_fields=("chip_weighted_cost", "chip_win_rate", "close"),
                direction=-1,
                economic_rationale=(
                    "A broadly profitable holder base may amplify profit-taking pressure."
                ),
                **common,
            ),
            FactorTemplate(
                template_id="chip_concentrated_momentum_5",
                name="Cost-concentrated momentum",
                event="chip_concentrated_momentum",
                formula_template=(
                    "period_return(close, 5) * "
                    "(1.0 - (mean(chip_cost_85, 5) - mean(chip_cost_15, 5)) / "
                    "(mean(chip_weighted_cost, 5) + 1.0))"
                ),
                required_fields=(
                    "chip_cost_15",
                    "chip_cost_85",
                    "chip_weighted_cost",
                    "close",
                ),
                direction=1,
                economic_rationale=(
                    "Recent momentum may persist when holder costs are concentrated."
                ),
                **common,
            ),
        ),
        windows=(20,),
        horizons=("20d",),
    )


def v30_epoch_four_generation_plan() -> GenerationPlan:
    """Issue #100 epoch-four chip-dynamics mechanisms."""

    common = {
        "context": "market_neutral_cross_section",
        "quality": "end_of_day_chip_distribution_dynamics_and_daily_bars",
        "output": "cross_sectional_score",
        "data_sources": ("qd_daily", "qd_chip"),
    }
    return GenerationPlan(
        templates=(
            FactorTemplate(
                template_id="chip_win_rate_acceleration_5_20",
                name="Profitable-holder acceleration reversal",
                event="chip_win_rate_acceleration",
                formula_template=(
                    "mean(chip_win_rate, 5) - mean(chip_win_rate, 20)"
                ),
                required_fields=("chip_win_rate",),
                direction=-1,
                economic_rationale=(
                    "A rapid increase in profitable holders may create near-term realization pressure."
                ),
                **common,
            ),
            FactorTemplate(
                template_id="chip_cost_band_compression_5_20",
                name="Holder cost-band compression",
                event="chip_cost_band_compression",
                formula_template=(
                    "(mean(chip_cost_85, 5) - mean(chip_cost_15, 5)) / "
                    "(mean(chip_weighted_cost, 5) + 1.0) - "
                    "(mean(chip_cost_85, 20) - mean(chip_cost_15, 20)) / "
                    "(mean(chip_weighted_cost, 20) + 1.0)"
                ),
                required_fields=("chip_cost_15", "chip_cost_85", "chip_weighted_cost"),
                direction=-1,
                economic_rationale=(
                    "A tightening holder cost band may reduce overhead supply and support adjustment."
                ),
                **common,
            ),
            FactorTemplate(
                template_id="chip_cost_basis_momentum_confirmation_5",
                name="Cost-basis and price momentum confirmation",
                event="chip_cost_basis_momentum_confirmation",
                formula_template=(
                    "period_return(chip_weighted_cost, 5) * period_return(close, 5)"
                ),
                required_fields=("chip_weighted_cost", "close"),
                direction=1,
                economic_rationale=(
                    "Price continuation accompanied by a rising holder cost basis may be less fragile."
                ),
                **common,
            ),
        ),
        windows=(20,),
        horizons=("20d",),
    )


def v30_epoch_five_generation_plan() -> GenerationPlan:
    """Issue #100 epoch-five limit-event mechanisms from a dense absence-aware panel."""

    common = {
        "context": "market_neutral_cross_section",
        "quality": "end_of_day_limit_event_panel_and_daily_bars",
        "output": "cross_sectional_score",
        "data_sources": ("qd_daily", "qd_limit_event"),
        "direction": 1,
    }
    return GenerationPlan(
        templates=(
            FactorTemplate(
                template_id="limit_up_persistence_20",
                name="Limit-up event persistence",
                event="limit_up_persistence",
                formula_template="mean(kpl_limit_up_flag, 20)",
                required_fields=("kpl_limit_up_flag",),
                economic_rationale=(
                    "Repeated limit-up participation may proxy sustained attention and demand."
                ),
                **common,
            ),
            FactorTemplate(
                template_id="limit_up_main_net_intensity_5",
                name="Limit-event main-flow intensity",
                event="limit_up_main_flow",
                formula_template=(
                    "mean(kpl_main_net_amount, 5) / (mean(amount, 5) + 1.0)"
                ),
                required_fields=("amount", "kpl_main_net_amount"),
                economic_rationale=(
                    "Net main-flow demand during limit-up events may persist beyond the event day."
                ),
                **common,
            ),
            FactorTemplate(
                template_id="limit_up_seal_strength_5",
                name="Closing limit-seal strength",
                event="limit_up_seal_strength",
                formula_template=(
                    "mean(kpl_close_seal_amount, 5) / "
                    "(mean(kpl_turnover_amount, 5) + 1.0)"
                ),
                required_fields=("kpl_close_seal_amount", "kpl_turnover_amount"),
                economic_rationale=(
                    "A large closing seal relative to event turnover may reveal unfilled demand."
                ),
                **common,
            ),
        ),
        windows=(20,),
        horizons=("20d",),
    )


def v43_sparse_domain_inverse_plan() -> GenerationPlan:
    """Direction-complete follow-up for the underexplored chip and limit-event domains.

    V3.0 preregistered only one economic direction per formula. V4.3 records the opposite
    direction as a new hypothesis instead of silently taking an absolute IC.
    """

    source_plans = (
        v30_epoch_three_generation_plan(),
        v30_epoch_four_generation_plan(),
        v30_epoch_five_generation_plan(),
    )
    templates = tuple(
        replace(
            template,
            template_id=f"{template.template_id}_inverse",
            name=f"{template.name} (inverse hypothesis)",
            direction=-template.direction,
            economic_rationale=(
                f"Counter-direction falsification of the prior hypothesis: "
                f"{template.economic_rationale}"
            ),
        )
        for plan in source_plans
        for template in plan.templates
    )
    return GenerationPlan(templates=templates, windows=(20,), horizons=("20d",))


def flow_stress_generation_plan() -> GenerationPlan:
    """V1.8.18 preregistered 20-day flow-divergence family."""

    common = {
        "context": "market_neutral_cross_section",
        "quality": "point_in_time_fund_flow_and_daily_bars",
        "output": "cross_sectional_score",
        "data_sources": ("qd_daily", "qd_fund_flow"),
        "direction": 1,
    }
    return GenerationPlan(
        templates=(
            FactorTemplate(
                template_id="flow_price_divergence_parent",
                name="Flow-price divergence parent",
                event="flow_price_divergence",
                formula_template=(
                    "mean(net_inflow_amount, 60) / (mean(amount, 60) + 1.0) "
                    "- period_return(close, 60)"
                ),
                required_fields=("amount", "close", "net_inflow_amount"),
                economic_rationale="Frozen V1.8.17 parent control.",
                **common,
            ),
            FactorTemplate(
                template_id="fund_flow_surprise_5_60",
                name="Five-versus-sixty-day fund-flow surprise",
                event="fund_flow_surprise",
                formula_template=(
                    "mean(net_inflow_amount, 5) / (mean(amount, 5) + 1.0) "
                    "- mean(net_inflow_amount, 60) / (mean(amount, 60) + 1.0)"
                ),
                required_fields=("amount", "net_inflow_amount"),
                economic_rationale="Recent normalized demand may surprise its long baseline.",
                **common,
            ),
            FactorTemplate(
                template_id="fund_flow_surprise_20_60",
                name="Twenty-versus-sixty-day fund-flow surprise",
                event="fund_flow_surprise",
                formula_template=(
                    "mean(net_inflow_amount, 20) / (mean(amount, 20) + 1.0) "
                    "- mean(net_inflow_amount, 60) / (mean(amount, 60) + 1.0)"
                ),
                required_fields=("amount", "net_inflow_amount"),
                economic_rationale="Medium-horizon normalized demand may lead price response.",
                **common,
            ),
            FactorTemplate(
                template_id="large_flow_surprise_5_60",
                name="Large-order imbalance surprise",
                event="large_flow_surprise",
                formula_template=(
                    "(mean(large_buy_amount, 5) - mean(large_sell_amount, 5)) / "
                    "(mean(amount, 5) + 1.0) - "
                    "(mean(large_buy_amount, 60) - mean(large_sell_amount, 60)) / "
                    "(mean(amount, 60) + 1.0)"
                ),
                required_fields=("amount", "large_buy_amount", "large_sell_amount"),
                economic_rationale="Recent large-order imbalance is compared with its own baseline.",
                **common,
            ),
            FactorTemplate(
                template_id="extra_large_flow_surprise_5_60",
                name="Extra-large-order imbalance surprise",
                event="extra_large_flow_surprise",
                formula_template=(
                    "(mean(extra_large_buy_amount, 5) - "
                    "mean(extra_large_sell_amount, 5)) / (mean(amount, 5) + 1.0) - "
                    "(mean(extra_large_buy_amount, 60) - "
                    "mean(extra_large_sell_amount, 60)) / (mean(amount, 60) + 1.0)"
                ),
                required_fields=(
                    "amount",
                    "extra_large_buy_amount",
                    "extra_large_sell_amount",
                ),
                economic_rationale="The largest-order surprise may isolate informed demand.",
                **common,
            ),
            FactorTemplate(
                template_id="flow_reversal_interaction",
                name="Flow persistence and price-reversal interaction",
                event="flow_price_interaction",
                formula_template=(
                    "mean(net_inflow_amount, 20) / (mean(amount, 20) + 1.0) "
                    "* (-period_return(close, 20))"
                ),
                required_fields=("amount", "close", "net_inflow_amount"),
                economic_rationale="Buying pressure during weakness may identify delayed response.",
                **common,
            ),
            FactorTemplate(
                template_id="price_reversal_control",
                name="Twenty-day price-reversal control",
                event="price_reversal_control",
                context="market_neutral_cross_section",
                quality="complete_daily_bars",
                output="cross_sectional_score",
                formula_template="period_return(close, 20)",
                required_fields=("close",),
                data_sources=("qd_daily",),
                direction=-1,
                economic_rationale="Frozen price-only control for incremental-information tests.",
            ),
            FactorTemplate(
                template_id="large_flow_control",
                name="Sixty-day large-flow control",
                event="large_flow_control",
                formula_template=(
                    "(mean(large_buy_amount, 60) - mean(large_sell_amount, 60)) / "
                    "(mean(amount, 60) + 1.0)"
                ),
                required_fields=("amount", "large_buy_amount", "large_sell_amount"),
                economic_rationale="Frozen large-flow control for surprise comparisons.",
                **common,
            ),
        ),
        windows=(60,),
        horizons=("20d",),
    )
