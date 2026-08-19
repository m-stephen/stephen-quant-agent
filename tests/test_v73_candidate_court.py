from stephen_quant.workflows import (
    V73_FROZEN_TEMPLATE_IDS,
    V73_PRIOR_INFERENTIAL_TRIALS,
    frozen_v73_generation_plan,
)


def test_v73_frozen_plan_is_the_deduplicated_v71_v72_survivor_union() -> None:
    plan = frozen_v73_generation_plan()

    assert len(plan.templates) == 16
    assert {template.template_id for template in plan.templates} == V73_FROZEN_TEMPLATE_IDS
    assert plan.windows == (5,)
    assert plan.horizons == ("5d",)
    assert V73_PRIOR_INFERENTIAL_TRIALS == 39 + 42

    sources = ["+".join(template.data_sources) for template in plan.templates]
    assert sources.count("qd_daily") == 8
    assert sources.count("qd_chip") == 4
    assert sources.count("qd_margin") == 3
    assert sources.count("qd_fund_flow+qd_margin") == 1
    assert sources.count("qd_fund_flow") == 0


def test_v73_plan_preserves_revealed_formula_directions_without_mutation() -> None:
    plan = frozen_v73_generation_plan()
    formulas = {(template.formula_template, template.direction) for template in plan.templates}

    assert ("volatility(close, 60)", -1) in formulas
    assert ("period_return(close, 20)", -1) in formulas
    assert ("sma_ratio(chip_cost_5, 1, 5)", -1) in formulas
    assert (
        "mean(net_inflow_amount, 5) / (mean(margin_financing_balance, 5) + 1)",
        1,
    ) in formulas
