from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .generator import FactorTemplate, GenerationPlan
from .proposal_generator import ProposalSpec, compile_proposal

MECHANISM_GRAMMAR_VERSION = "7.4.0"


@dataclass(frozen=True)
class MechanismRecipe:
    family: str
    name: str
    formula: str
    rationale: str


def _recipes() -> tuple[MechanismRecipe, ...]:
    """Frozen, label-free mechanism grammar for the first V7.4 epoch."""

    return (
        MechanismRecipe(
            "price_risk",
            "Twenty-day risk-adjusted momentum",
            "period_return(close, 20) / (volatility(close, 20) + 0.000001)",
            "Return scaled by its own realized risk may separate efficient trends from noise.",
        ),
        MechanismRecipe(
            "price_risk",
            "Sixty-day risk-adjusted momentum",
            "period_return(close, 60) / (volatility(close, 60) + 0.000001)",
            "A slower return-to-risk state may capture persistent cross-sectional repricing.",
        ),
        MechanismRecipe(
            "price_path",
            "Twenty-day return-to-drawdown",
            "period_return(close, 20) / (-max_drawdown(close, 20) + 0.000001)",
            "Returns achieved with shallow path drawdown may be more persistent.",
        ),
        MechanismRecipe(
            "price_path",
            "Sixty-day return-to-drawdown",
            "period_return(close, 60) / (-max_drawdown(close, 60) + 0.000001)",
            "Medium-term trend quality may be revealed by return per unit of path damage.",
        ),
        MechanismRecipe(
            "liquidity",
            "Twenty-day Amihud pressure",
            "amihud(close, amount, 20)",
            "Price movement per traded yuan may proxy illiquidity risk and crowding.",
        ),
        MechanismRecipe(
            "liquidity",
            "Sixty-day Amihud pressure",
            "amihud(close, amount, 60)",
            "Persistent price impact may distinguish durable liquidity states.",
        ),
        MechanismRecipe(
            "fund_flow_surprise",
            "Net-flow five-versus-sixty surprise",
            "mean(net_inflow_amount, 5) / (mean(amount, 5) + 1.0) - "
            "mean(net_inflow_amount, 60) / (mean(amount, 60) + 1.0)",
            "Recent net demand relative to its own baseline may reveal a flow impulse.",
        ),
        MechanismRecipe(
            "fund_flow_surprise",
            "Large-order five-versus-sixty surprise",
            "(mean(large_buy_amount, 5) - mean(large_sell_amount, 5)) / "
            "(mean(large_buy_amount, 60) + mean(large_sell_amount, 60) + 1.0)",
            "A change in large-order imbalance may precede a delayed price response.",
        ),
        MechanismRecipe(
            "fund_flow_surprise",
            "Extra-large-order five-versus-sixty surprise",
            "(mean(extra_large_buy_amount, 5) - mean(extra_large_sell_amount, 5)) / "
            "(mean(extra_large_buy_amount, 60) + mean(extra_large_sell_amount, 60) + 1.0)",
            "The largest-ticket demand impulse may isolate informed-flow persistence.",
        ),
        MechanismRecipe(
            "fund_flow_composition",
            "Large-versus-extra-large flow composition",
            "((mean(large_buy_amount, 20) - mean(large_sell_amount, 20)) - "
            "(mean(extra_large_buy_amount, 20) - mean(extra_large_sell_amount, 20))) / "
            "(mean(large_buy_amount, 20) + mean(large_sell_amount, 20) + 1.0)",
            "Order-size composition may distinguish broad demand from concentrated demand.",
        ),
        MechanismRecipe(
            "margin_demand",
            "Margin-balance momentum",
            "period_return(margin_financing_balance, 20)",
            "Growth in financing balance may proxy persistent leveraged demand.",
        ),
        MechanismRecipe(
            "margin_demand",
            "Margin-balance trend",
            "sma_ratio(margin_financing_balance, 5, 20)",
            "The short-versus-medium financing balance trend may identify leverage acceleration.",
        ),
        MechanismRecipe(
            "margin_demand",
            "Margin buy-to-repay pressure",
            "mean(margin_financing_buy, 5) / (mean(margin_financing_repay, 5) + 1.0)",
            "Financing purchases relative to repayments may measure net leveraged demand.",
        ),
        MechanismRecipe(
            "chip_structure",
            "Chip win-rate acceleration",
            "mean(chip_win_rate, 5) - mean(chip_win_rate, 20)",
            "A rising profitable-holder share may change subsequent supply pressure.",
        ),
        MechanismRecipe(
            "chip_structure",
            "Chip central dispersion",
            "(mean(chip_cost_85, 20) - mean(chip_cost_15, 20)) / "
            "(mean(chip_weighted_cost, 20) + 1.0)",
            "Holder-cost dispersion may proxy disagreement and latent selling pressure.",
        ),
        MechanismRecipe(
            "chip_structure",
            "Chip tail asymmetry",
            "((mean(chip_cost_95, 20) - mean(chip_cost_50, 20)) - "
            "(mean(chip_cost_50, 20) - mean(chip_cost_5, 20))) / "
            "(mean(chip_weighted_cost, 20) + 1.0)",
            "Asymmetry of holder costs may distinguish overhead supply from support.",
        ),
        MechanismRecipe(
            "chip_structure",
            "Weighted holder-cost momentum",
            "period_return(chip_weighted_cost, 20)",
            "Migration of the holder cost center may reveal position transfer and trend quality.",
        ),
        MechanismRecipe(
            "flow_price_interaction",
            "Normalized flow during price weakness",
            "mean(net_inflow_amount, 20) / (mean(amount, 20) + 1.0) * "
            "(-period_return(close, 20))",
            "Buying pressure during weakness may reveal absorption before delayed repricing.",
        ),
        MechanismRecipe(
            "flow_price_interaction",
            "Flow per unit volatility",
            "mean(net_inflow_amount, 20) / (mean(amount, 20) + 1.0) / "
            "(volatility(close, 20) + 0.000001)",
            "Demand normalized by both liquidity and risk may isolate efficient accumulation.",
        ),
        MechanismRecipe(
            "margin_price_interaction",
            "Leverage-price divergence",
            "period_return(margin_financing_balance, 20) - period_return(close, 20)",
            "Leverage growth not yet reflected in price may indicate delayed response or crowding.",
        ),
        MechanismRecipe(
            "margin_price_interaction",
            "Net financing pressure by turnover",
            "(mean(margin_financing_buy, 20) - mean(margin_financing_repay, 20)) / "
            "(mean(amount, 20) + 1.0)",
            "Net leveraged demand scaled by trading value may be comparable across stocks.",
        ),
        MechanismRecipe(
            "chip_price_interaction",
            "Price-to-holder-cost gap",
            "mean(close, 5) / (mean(chip_weighted_cost, 5) + 1.0) - 1.0",
            "Distance from the holder cost center may proxy unrealized profit and supply pressure.",
        ),
        MechanismRecipe(
            "chip_price_interaction",
            "Price-versus-holder-cost momentum",
            "period_return(close, 20) - period_return(chip_weighted_cost, 20)",
            "Price moving ahead of the cost center may reveal trend strength or crowding.",
        ),
        MechanismRecipe(
            "chip_price_interaction",
            "Momentum conditioned by chip concentration",
            "period_return(close, 20) * (1.0 - "
            "(mean(chip_cost_85, 20) - mean(chip_cost_15, 20)) / "
            "(mean(chip_weighted_cost, 20) + 1.0))",
            "Momentum supported by a concentrated holder-cost distribution may be more durable.",
        ),
    )


def generate_v74_mechanism_plan() -> GenerationPlan:
    """Compile the frozen mechanism recipes in both economic directions."""

    templates: list[FactorTemplate] = []
    formula_identities: set[tuple[str, int]] = set()
    for recipe in _recipes():
        for direction in (-1, 1):
            proposal = compile_proposal(
                ProposalSpec(
                    formula=recipe.formula,
                    hypothesis=recipe.rationale,
                    research_form="continuous_ranking",
                    horizon="5d",
                    direction=direction,
                    origin="symbolic",
                    provider_id=f"symbolic:v7.4:{recipe.family}",
                )
            )
            identity = (proposal.schema.formula, direction)
            if identity in formula_identities:
                raise ValueError(f"duplicate V7.4 mechanism identity: {identity}")
            formula_identities.add(identity)
            digest = hashlib.sha256(
                f"{recipe.family}|{proposal.proposal_id}".encode()
            ).hexdigest()[:16]
            templates.append(
                FactorTemplate(
                    template_id=f"v74_{digest}",
                    name=f"{recipe.name} ({'inverse' if direction == -1 else 'direct'})",
                    event=recipe.family,
                    context="market_neutral_cross_section",
                    quality="label_free_frozen_mechanism_grammar",
                    output="cross_sectional_score",
                    formula_template=proposal.schema.formula,
                    required_fields=proposal.schema.required_fields,
                    data_sources=proposal.schema.data_sources,
                    direction=direction,
                    economic_rationale=recipe.rationale,
                )
            )
    plan = GenerationPlan(tuple(templates), (5,), ("5d",))
    plan.validate()
    return plan


def v74_mechanism_family_counts() -> tuple[tuple[str, int], ...]:
    counts: dict[str, int] = {}
    for recipe in _recipes():
        counts[recipe.family] = counts.get(recipe.family, 0) + 2
    return tuple(sorted(counts.items()))


def _epoch_two_recipes() -> tuple[MechanismRecipe, ...]:
    """Frozen cross-source confirmation grammar for V7.4 epoch two."""

    flow = "mean(net_inflow_amount, 20) / (mean(amount, 20) + 1.0)"
    margin = (
        "(mean(margin_financing_buy, 20) - mean(margin_financing_repay, 20)) / "
        "(mean(amount, 20) + 1.0)"
    )
    large = (
        "(mean(large_buy_amount, 20) - mean(large_sell_amount, 20)) / "
        "(mean(amount, 20) + 1.0)"
    )
    extra = (
        "(mean(extra_large_buy_amount, 20) - mean(extra_large_sell_amount, 20)) / "
        "(mean(amount, 20) + 1.0)"
    )
    gap = "(mean(close, 5) / (mean(chip_weighted_cost, 5) + 1.0) - 1.0)"
    dispersion = (
        "(mean(chip_cost_85, 20) - mean(chip_cost_15, 20)) / "
        "(mean(chip_weighted_cost, 20) + 1.0)"
    )
    return (
        MechanismRecipe(
            "flow_margin_confirmation",
            "Net-flow and financing confirmation",
            f"({flow}) * ({margin})",
            "Independent cash-flow and leveraged-flow pressure may confirm durable demand.",
        ),
        MechanismRecipe(
            "flow_margin_confirmation",
            "Large-flow and financing-balance confirmation",
            f"({large}) * period_return(margin_financing_balance, 20)",
            "Large-order pressure confirmed by balance growth may reduce false flow signals.",
        ),
        MechanismRecipe(
            "flow_margin_confirmation",
            "Extra-large flow and financing activity",
            f"({extra}) * (mean(margin_financing_buy, 20) / "
            "(mean(margin_financing_repay, 20) + 1.0))",
            "Largest-ticket activity and financing intensity may identify coordinated demand.",
        ),
        MechanismRecipe(
            "flow_margin_confirmation",
            "Flow impulse and margin trend",
            "(mean(net_inflow_amount, 5) / (mean(amount, 5) + 1.0) - "
            f"{flow}) * sma_ratio(margin_financing_balance, 5, 20)",
            "A new flow impulse confirmed by leverage acceleration may persist.",
        ),
        MechanismRecipe(
            "flow_chip_confirmation",
            "Flow and holder-cost gap",
            f"({flow}) * {gap}",
            "Demand relative to turnover may behave differently above and below holder cost.",
        ),
        MechanismRecipe(
            "flow_chip_confirmation",
            "Large flow and win-rate acceleration",
            f"({large}) * (mean(chip_win_rate, 5) - mean(chip_win_rate, 20))",
            "Large demand confirmed by improving holder profitability may reduce supply pressure.",
        ),
        MechanismRecipe(
            "flow_chip_confirmation",
            "Extra-large flow conditioned by chip concentration",
            f"({extra}) * (1.0 - {dispersion})",
            "Concentrated holder costs may strengthen the information in extra-large flow.",
        ),
        MechanismRecipe(
            "flow_chip_confirmation",
            "Flow impulse and chip-tail asymmetry",
            "(mean(net_inflow_amount, 5) / (mean(amount, 5) + 1.0) - "
            f"{flow}) * (((mean(chip_cost_95, 20) - mean(chip_cost_50, 20)) - "
            "(mean(chip_cost_50, 20) - mean(chip_cost_5, 20))) / "
            "(mean(chip_weighted_cost, 20) + 1.0))",
            "Flow impulses may be more informative when holder-cost tails are asymmetric.",
        ),
        MechanismRecipe(
            "margin_chip_confirmation",
            "Financing pressure and holder-cost gap",
            f"({margin}) * {gap}",
            "Leveraged demand conditioned on unrealized holder profit may reveal crowding.",
        ),
        MechanismRecipe(
            "margin_chip_confirmation",
            "Financing-balance and holder-cost migration",
            "period_return(margin_financing_balance, 20) * "
            "period_return(chip_weighted_cost, 20)",
            "Joint migration of leverage and holder cost may confirm position transfer.",
        ),
        MechanismRecipe(
            "margin_chip_confirmation",
            "Financing activity and win-rate acceleration",
            "(mean(margin_financing_buy, 20) / "
            "(mean(margin_financing_repay, 20) + 1.0)) * "
            "(mean(chip_win_rate, 5) - mean(chip_win_rate, 20))",
            "Financing intensity and holder-profit change may jointly proxy crowded demand.",
        ),
        MechanismRecipe(
            "margin_chip_confirmation",
            "Margin trend conditioned by chip concentration",
            f"sma_ratio(margin_financing_balance, 5, 20) * (1.0 - {dispersion})",
            "Leverage acceleration with concentrated holder costs may be more persistent.",
        ),
        MechanismRecipe(
            "path_confirmation",
            "Risk-adjusted return and net-flow confirmation",
            f"(period_return(close, 20) / (volatility(close, 20) + 0.000001)) * ({flow})",
            "Efficient price trends confirmed by normalized flow may survive costs better.",
        ),
        MechanismRecipe(
            "path_confirmation",
            "Return-to-drawdown and financing confirmation",
            "(period_return(close, 20) / (-max_drawdown(close, 20) + 0.000001)) * "
            f"({margin})",
            "High-quality paths confirmed by leveraged demand may reduce drawdown risk.",
        ),
        MechanismRecipe(
            "path_confirmation",
            "Illiquidity absorption",
            f"amihud(close, amount, 20) * ({flow})",
            "Demand in high-price-impact names may indicate absorption or liquidity risk.",
        ),
        MechanismRecipe(
            "path_confirmation",
            "Risk-adjusted return conditioned by chip concentration",
            "(period_return(close, 20) / (volatility(close, 20) + 0.000001)) * "
            f"(1.0 - {dispersion})",
            "Trend efficiency supported by concentrated holder costs may be more durable.",
        ),
    )


def generate_v74_epoch_two_plan() -> GenerationPlan:
    templates: list[FactorTemplate] = []
    identities: set[tuple[str, int]] = set()
    for recipe in _epoch_two_recipes():
        for direction in (-1, 1):
            proposal = compile_proposal(
                ProposalSpec(
                    recipe.formula,
                    recipe.rationale,
                    "continuous_ranking",
                    "20d",
                    direction,
                    "symbolic",
                    f"symbolic:v7.4-epoch2:{recipe.family}",
                )
            )
            identity = (proposal.schema.formula, direction)
            if identity in identities:
                raise ValueError(f"duplicate V7.4 epoch-two identity: {identity}")
            identities.add(identity)
            digest = hashlib.sha256(
                f"epoch2|{recipe.family}|{proposal.proposal_id}".encode()
            ).hexdigest()[:16]
            templates.append(
                FactorTemplate(
                    template_id=f"v74e2_{digest}",
                    name=f"{recipe.name} ({'inverse' if direction == -1 else 'direct'})",
                    event=recipe.family,
                    context="market_neutral_cross_section",
                    quality="label_free_frozen_cross_source_confirmation",
                    output="cross_sectional_score",
                    formula_template=proposal.schema.formula,
                    required_fields=proposal.schema.required_fields,
                    data_sources=proposal.schema.data_sources,
                    direction=direction,
                    economic_rationale=recipe.rationale,
                )
            )
    plan = GenerationPlan(tuple(templates), (20,), ("20d",))
    plan.validate()
    return plan
