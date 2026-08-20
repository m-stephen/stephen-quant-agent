from stephen_quant.cli import build_parser
from stephen_quant.discovery import (
    DiscoveryCpcvConfig,
    generate_v74_epoch_two_plan,
    generate_v74_mechanism_plan,
    v74_mechanism_family_counts,
)
from stephen_quant.discovery.screening import _budget_family
from stephen_quant.workflows import (
    V74_EPOCH_TWO_PRIOR_INFERENTIAL_TRIALS,
    V74_FAMILY_BUDGETS,
    V74_PRIOR_INFERENTIAL_TRIALS,
    frozen_v73_generation_plan,
)
from stephen_quant.workflows.v74_novel_mechanisms import frozen_v74_epoch_two_config


def test_v74_mechanism_grammar_is_direction_complete_and_bounded() -> None:
    plan = generate_v74_mechanism_plan()

    assert len(plan.templates) == 48
    assert plan.windows == (5,)
    assert plan.horizons == ("5d",)
    by_formula: dict[str, set[int]] = {}
    for template in plan.templates:
        by_formula.setdefault(template.formula_template, set()).add(template.direction)
    assert len(by_formula) == 24
    assert all(directions == {-1, 1} for directions in by_formula.values())
    assert sum(value for _, value in v74_mechanism_family_counts()) == 48
    assert sum(value for _, value in V74_FAMILY_BUDGETS) == 24
    assert V74_PRIOR_INFERENTIAL_TRIALS == 145


def test_v74_uses_new_mechanisms_and_multiple_source_combinations() -> None:
    plan = generate_v74_mechanism_plan()
    prior = {
        (template.formula_template, template.direction)
        for template in frozen_v73_generation_plan().templates
    }
    current = {
        (template.formula_template, template.direction) for template in plan.templates
    }
    sources = {template.data_sources for template in plan.templates}

    assert not (prior & current)
    assert ("qd_daily", "qd_fund_flow") in sources
    assert ("qd_daily", "qd_margin") in sources
    assert ("qd_chip", "qd_daily") in sources
    assert any("max_drawdown" in formula for formula, _ in current)
    assert any("amihud" in formula for formula, _ in current)


def test_v74_cli_requires_explicit_local_paths() -> None:
    args = build_parser().parse_args(
        [
            "discover-novel-alpha",
            "--paths-config",
            "configs/qd-paths.local.json",
        ]
    )
    assert args.command == "discover-novel-alpha"
    assert args.paths_config.endswith("qd-paths.local.json")


def test_v74_epoch_two_is_cross_source_direction_complete_and_new() -> None:
    first = generate_v74_mechanism_plan()
    second = generate_v74_epoch_two_plan()
    first_identities = {
        (item.formula_template, item.direction, "5d") for item in first.templates
    }
    second_identities = {
        (item.formula_template, item.direction, "20d") for item in second.templates
    }

    assert len(second.templates) == 32
    assert len({item.formula_template for item in second.templates}) == 16
    assert not (first_identities & second_identities)
    assert second.windows == (20,)
    assert second.horizons == ("20d",)
    assert all(len(item.data_sources) >= 2 for item in second.templates)
    assert V74_EPOCH_TWO_PRIOR_INFERENTIAL_TRIALS == 298


def test_v74_epoch_two_cli_is_explicit() -> None:
    args = build_parser().parse_args(
        [
            "discover-cross-source-alpha",
            "--paths-config",
            "configs/qd-paths.local.json",
        ]
    )
    assert args.command == "discover-cross-source-alpha"


def test_v74_epoch_two_cpcv_has_fifteen_available_paths() -> None:
    config = frozen_v74_epoch_two_config()
    assert (config.groups, config.test_groups, config.minimum_positive_paths) == (7, 3, 15)
    DiscoveryCpcvConfig(
        groups=config.groups,
        test_groups=config.test_groups,
        embargo_days=config.embargo_days,
        minimum_positive_paths=config.minimum_positive_paths,
        maximum_pbo=config.maximum_pbo,
    ).validate()


def test_v74_family_budget_uses_explicit_mechanism_event() -> None:
    budgets = {"flow_chip_confirmation": 4}
    assert (
        _budget_family("v74e2_abcdef_20_20d", "flow_chip_confirmation", budgets)
        == "flow_chip_confirmation"
    )
    assert _budget_family("price_momentum_20_20d", "price", budgets) == "price_momentum"
