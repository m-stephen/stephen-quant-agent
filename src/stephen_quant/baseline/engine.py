from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime
from itertools import pairwise
from statistics import stdev

from .models import (
    METHOD_VERSION,
    BacktestPeriod,
    BaselineConfig,
    BaselineError,
    BaselineLineage,
    BaselineMetrics,
    BaselineObservation,
    BaselineReport,
    OrderExecution,
)


def _parse_timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BaselineError(f"invalid ISO timestamp: {value}") from exc


def _validate_config(config: BaselineConfig) -> None:
    if config.top_k < 1:
        raise BaselineError("top_k must be positive")
    if config.rebalance_every < 1:
        raise BaselineError("rebalance_every must be positive")
    if config.direction not in {-1, 1}:
        raise BaselineError("direction must be -1 or 1")
    if not 0 <= config.cash_reserve < 1:
        raise BaselineError("cash_reserve must be in [0, 1)")
    if not 0 < config.max_position_weight <= 1:
        raise BaselineError("max_position_weight must be in (0, 1]")
    if config.periods_per_year < 1:
        raise BaselineError("periods_per_year must be positive")
    if not 0 < config.max_participation_rate <= 1:
        raise BaselineError("max_participation_rate must be in (0, 1]")
    costs = (
        config.commission_bps,
        config.sell_tax_bps,
        config.slippage_bps,
        config.impact_coefficient_bps,
    )
    if any(not math.isfinite(value) or value < 0 for value in costs):
        raise BaselineError("cost assumptions must be finite and non-negative")
    if not config.cost_model_version:
        raise BaselineError("cost_model_version cannot be empty")
    if config.missing_holding_policy not in {"error", "stale_zero_return"}:
        raise BaselineError("unsupported missing_holding_policy")
    if config.ranking_policy not in {
        "top_k",
        "all_eligible",
        "top_fraction",
        "exclude_bottom_fraction",
        "bottom_fraction_underweight",
    }:
        raise BaselineError("unsupported ranking_policy")
    if (
        config.ranking_policy not in {"top_k", "all_eligible"}
        and not 0 < config.selection_fraction < 1
    ):
        raise BaselineError("fractional ranking policies require selection_fraction in (0, 1)")
    if not 0 <= config.bottom_underweight <= 1:
        raise BaselineError("bottom_underweight must be in [0, 1]")


def _validate_lineage(lineage: BaselineLineage) -> None:
    if not all(
        (
            lineage.factor_id,
            lineage.factor_version,
            lineage.snapshot_id,
            lineage.experiment_id,
            lineage.trial_id,
            lineage.code_version,
        )
    ):
        raise BaselineError("baseline lineage identifiers cannot be empty")


def _group_observations(
    observations: Sequence[BaselineObservation],
) -> tuple[tuple[str, tuple[BaselineObservation, ...]], ...]:
    if not observations:
        raise BaselineError("baseline requires observations")
    groups: dict[str, list[BaselineObservation]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for row in observations:
        key = (row.execution_at, row.instrument)
        if key in seen:
            raise BaselineError(f"duplicate baseline observation: {key}")
        seen.add(key)
        numeric = (row.signal, row.average_daily_value, row.forward_return)
        if any(not math.isfinite(value) for value in numeric):
            raise BaselineError(f"non-finite baseline observation: {key}")
        if row.average_daily_value <= 0:
            raise BaselineError(f"average_daily_value must be positive: {key}")
        if row.forward_return <= -1:
            raise BaselineError(f"long-only forward return cannot be <= -100%: {key}")
        execution = _parse_timestamp(row.execution_at)
        if _parse_timestamp(row.signal_at) > _parse_timestamp(row.signal_available_at):
            raise BaselineError(f"signal available before observation: {key}")
        if _parse_timestamp(row.signal_available_at) >= execution:
            raise BaselineError(f"signal is not available before execution: {key}")
        if _parse_timestamp(row.liquidity_available_at) >= execution:
            raise BaselineError(f"liquidity is not available before execution: {key}")
        if _parse_timestamp(row.return_end_at) <= execution:
            raise BaselineError(f"return window does not follow execution: {key}")
        groups[row.execution_at].append(row)

    ordered: list[tuple[str, tuple[BaselineObservation, ...]]] = []
    for execution_at in sorted(groups, key=_parse_timestamp):
        rows = tuple(sorted(groups[execution_at], key=lambda item: item.instrument))
        return_ends = {row.return_end_at for row in rows}
        if len(return_ends) != 1:
            raise BaselineError(f"cross-section has inconsistent return windows: {execution_at}")
        ordered.append((execution_at, rows))
    for (_, previous), (execution_at, _) in pairwise(ordered):
        if _parse_timestamp(previous[0].return_end_at) > _parse_timestamp(execution_at):
            raise BaselineError("sequential forward-return windows cannot overlap")
    return tuple(ordered)


def _target_weights(
    rows: Sequence[BaselineObservation], config: BaselineConfig
) -> tuple[tuple[str, ...], dict[str, float]]:
    eligible = [row for row in rows if row.eligible]
    if not eligible and config.allow_empty_selection:
        return (), {}
    if config.ranking_policy == "top_k" and len(eligible) < config.top_k:
        raise BaselineError(
            f"cross-section has {len(eligible)} eligible assets but top_k requires {config.top_k}"
        )
    if not eligible:
        raise BaselineError("cross-section has no eligible assets")
    ranked = sorted(eligible, key=lambda row: (-config.direction * row.signal, row.instrument))
    if config.ranking_policy == "top_k":
        selected_rows = ranked[: config.top_k]
        raw_weights = {row.instrument: 1.0 for row in selected_rows}
    elif config.ranking_policy == "all_eligible":
        selected_rows = ranked
        raw_weights = {row.instrument: 1.0 for row in selected_rows}
    elif config.ranking_policy == "top_fraction":
        count = max(1, math.ceil(len(ranked) * config.selection_fraction))
        selected_rows = ranked[:count]
        raw_weights = {row.instrument: 1.0 for row in selected_rows}
    elif config.ranking_policy == "exclude_bottom_fraction":
        excluded = max(1, math.ceil(len(ranked) * config.selection_fraction))
        selected_rows = ranked[: max(1, len(ranked) - excluded)]
        raw_weights = {row.instrument: 1.0 for row in selected_rows}
    else:
        bottom_count = max(1, math.ceil(len(ranked) * config.selection_fraction))
        bottom = {row.instrument for row in ranked[-bottom_count:]}
        selected_rows = ranked
        raw_weights = {
            row.instrument: config.bottom_underweight if row.instrument in bottom else 1.0
            for row in selected_rows
        }
    selected = tuple(row.instrument for row in selected_rows)
    total_raw = sum(raw_weights.values())
    if total_raw <= 0:
        raise BaselineError("ranking policy produced zero portfolio weight")
    investable = 1 - config.cash_reserve
    return selected, {
        instrument: min(investable * raw / total_raw, config.max_position_weight)
        for instrument, raw in raw_weights.items()
    }


def _costs(
    notional: float, average_daily_value: float, config: BaselineConfig
) -> tuple[float, float, float, float]:
    absolute = abs(notional)
    if absolute == 0:
        return 0.0, 0.0, 0.0, 0.0
    commission = absolute * config.commission_bps / 10_000
    sell_tax = absolute * config.sell_tax_bps / 10_000 if notional < 0 else 0.0
    slippage = absolute * config.slippage_bps / 10_000
    participation = absolute / average_daily_value
    impact_bps = config.impact_coefficient_bps * math.sqrt(participation)
    impact = absolute * impact_bps / 10_000
    return commission, sell_tax, slippage, impact


def _buy_scale(
    buys: dict[str, float],
    rows: dict[str, BaselineObservation],
    available_cash: float,
    config: BaselineConfig,
) -> float:
    def requirement(scale: float) -> float:
        return sum(
            notional * scale + sum(_costs(notional * scale, rows[item].average_daily_value, config))
            for item, notional in buys.items()
        )

    if requirement(1.0) <= available_cash:
        return 1.0
    if available_cash <= 0:
        return 0.0
    low, high = 0.0, 1.0
    for _ in range(80):
        middle = (low + high) / 2
        if requirement(middle) <= available_cash:
            low = middle
        else:
            high = middle
    return low


def _execute_rebalance(
    rows: Sequence[BaselineObservation],
    holdings: dict[str, float],
    cash: float,
    nav: float,
    config: BaselineConfig,
) -> tuple[tuple[str, ...], tuple[OrderExecution, ...], dict[str, float], float]:
    by_instrument = {row.instrument: row for row in rows}
    missing = sorted(set(holdings) - set(by_instrument))
    if missing:
        raise BaselineError(f"held assets missing from execution cross-section: {missing}")
    selected, targets = _target_weights(rows, config)
    universe = sorted(set(holdings) | set(targets))
    desired = {
        instrument: targets.get(instrument, 0.0) * nav - holdings.get(instrument, 0.0)
        for instrument in universe
    }
    tradable_desired = {
        instrument: (
            0.0
            if (notional > 0 and not by_instrument[instrument].can_buy_open)
            or (notional < 0 and not by_instrument[instrument].can_sell_open)
            else notional
        )
        for instrument, notional in desired.items()
    }
    capacity = {
        instrument: by_instrument[instrument].average_daily_value * config.max_participation_rate
        for instrument in universe
    }
    capacity_executions = {
        instrument: math.copysign(min(abs(notional), capacity[instrument]), notional)
        if notional
        else 0.0
        for instrument, notional in tradable_desired.items()
    }
    sells = {item: value for item, value in capacity_executions.items() if value < 0}
    buys = {item: value for item, value in capacity_executions.items() if value > 0}
    sell_cost = sum(
        sum(_costs(value, by_instrument[item].average_daily_value, config))
        for item, value in sells.items()
    )
    available_cash = cash - sum(sells.values()) - sell_cost
    if available_cash < -1e-9:
        raise BaselineError("execution costs exceed cash and sale proceeds")
    scale = _buy_scale(buys, by_instrument, max(available_cash, 0.0), config)
    executed = {**sells, **{item: value * scale for item, value in buys.items()}}

    orders: list[OrderExecution] = []
    total_cost = 0.0
    for instrument in universe:
        row = by_instrument[instrument]
        trade = executed.get(instrument, 0.0)
        commission, sell_tax, slippage, impact = _costs(trade, row.average_daily_value, config)
        cost = commission + sell_tax + slippage + impact
        total_cost += cost
        orders.append(
            OrderExecution(
                instrument=instrument,
                selected=instrument in targets,
                signal=row.signal,
                pretrade_weight=holdings.get(instrument, 0.0) / nav,
                target_weight=targets.get(instrument, 0.0),
                desired_notional=desired[instrument],
                capacity_notional=capacity[instrument],
                executed_notional=trade,
                participation_rate=abs(trade) / row.average_daily_value,
                capacity_clipped_notional=max(
                    abs(tradable_desired[instrument]) - abs(capacity_executions[instrument]),
                    0.0,
                ),
                funding_clipped_notional=max(
                    abs(capacity_executions[instrument]) - abs(trade), 0.0
                ),
                commission_cost=commission,
                sell_tax_cost=sell_tax,
                slippage_cost=slippage,
                market_impact_cost=impact,
                total_cost=cost,
                can_buy_open=row.can_buy_open,
                can_sell_open=row.can_sell_open,
                tradability_reason=row.tradability_reason,
                tradability_clipped_notional=max(
                    abs(desired[instrument]) - abs(tradable_desired[instrument]), 0.0
                ),
            )
        )

    updated = dict(holdings)
    for instrument, trade in executed.items():
        updated[instrument] = updated.get(instrument, 0.0) + trade
        if abs(updated[instrument]) < 1e-10:
            updated.pop(instrument)
        elif updated[instrument] < 0:
            raise BaselineError(f"execution created a short position: {instrument}")
    updated_cash = cash - sum(executed.values()) - total_cost
    if updated_cash < -1e-7:
        raise BaselineError("execution created negative cash")
    return selected, tuple(orders), updated, max(updated_cash, 0.0)


def _metrics(
    periods: Sequence[BacktestPeriod], initial_nav: float, config: BaselineConfig
) -> BaselineMetrics:
    net_returns = [period.net_return for period in periods]
    gross_total = math.prod(1 + period.gross_return for period in periods) - 1
    final_nav = periods[-1].end_nav
    annualized_return = (final_nav / initial_nav) ** (config.periods_per_year / len(periods)) - 1
    volatility = (
        stdev(net_returns) * math.sqrt(config.periods_per_year) if len(net_returns) > 1 else None
    )
    sharpe = None
    if volatility not in (None, 0.0):
        sharpe = (sum(net_returns) / len(net_returns)) / stdev(net_returns)
        sharpe *= math.sqrt(config.periods_per_year)

    peak = initial_nav
    max_drawdown = 0.0
    for period in periods:
        peak = max(peak, period.end_nav)
        max_drawdown = min(max_drawdown, period.end_nav / peak - 1)
    orders = [order for period in periods for order in period.orders]
    return BaselineMetrics(
        periods=len(periods),
        initial_nav=initial_nav,
        final_nav=final_nav,
        gross_total_return=gross_total,
        net_total_return=final_nav / initial_nav - 1,
        annualized_net_return=annualized_return,
        annualized_net_volatility=volatility,
        net_sharpe=sharpe,
        max_drawdown=max_drawdown,
        total_turnover=sum(period.turnover for period in periods),
        total_traded_notional=sum(period.traded_notional for period in periods),
        total_cost=sum(period.total_cost for period in periods),
        capacity_clipped_notional=sum(order.capacity_clipped_notional for order in orders),
        funding_clipped_notional=sum(order.funding_clipped_notional for order in orders),
        tradability_clipped_notional=sum(order.tradability_clipped_notional for order in orders),
        tradability_blocked_orders=sum(
            order.tradability_clipped_notional > 1e-9 for order in orders
        ),
        clipped_orders=sum(
            order.capacity_clipped_notional > 1e-9
            or order.funding_clipped_notional > 1e-9
            or order.tradability_clipped_notional > 1e-9
            for order in orders
        ),
    )


def run_momentum_topk(
    observations: Sequence[BaselineObservation],
    lineage: BaselineLineage,
    config: BaselineConfig,
    *,
    initial_nav: float = 1_000_000.0,
) -> BaselineReport:
    """Run a deterministic, self-financing, long-only Top-K momentum baseline."""

    _validate_config(config)
    _validate_lineage(lineage)
    if not math.isfinite(initial_nav) or initial_nav <= 0:
        raise BaselineError("initial_nav must be finite and positive")
    grouped = _group_observations(observations)
    holdings: dict[str, float] = {}
    last_seen: dict[str, BaselineObservation] = {}
    cash = float(initial_nav)
    periods: list[BacktestPeriod] = []
    for period_index, (execution_at, rows) in enumerate(grouped):
        observed_rows = rows
        missing = sorted(set(holdings) - {row.instrument for row in rows})
        if missing and config.missing_holding_policy == "stale_zero_return":
            template = rows[0]
            stale_rows = tuple(
                replace(
                    last_seen[instrument],
                    signal=0.0,
                    execution_at=execution_at,
                    return_end_at=template.return_end_at,
                    forward_return=0.0,
                    can_buy_open=False,
                    can_sell_open=False,
                    tradability_reason="missing_bar_stale_zero_return",
                    eligible=False,
                )
                for instrument in missing
                if instrument in last_seen
            )
            rows = tuple(sorted((*rows, *stale_rows), key=lambda row: row.instrument))
        for row in observed_rows:
            last_seen[row.instrument] = row
        start_nav = cash + sum(holdings.values())
        rebalanced = period_index % config.rebalance_every == 0
        selected: tuple[str, ...] = ()
        orders: tuple[OrderExecution, ...] = ()
        if rebalanced:
            selected, orders, holdings, cash = _execute_rebalance(
                rows, holdings, cash, start_nav, config
            )
        by_instrument = {row.instrument: row for row in rows}
        missing = sorted(set(holdings) - set(by_instrument))
        if missing:
            raise BaselineError(f"held assets missing from return cross-section: {missing}")
        profit = sum(
            value * by_instrument[instrument].forward_return
            for instrument, value in holdings.items()
        )
        total_cost = sum(order.total_cost for order in orders)
        traded_notional = sum(abs(order.executed_notional) for order in orders)
        holdings = {
            instrument: value * (1 + by_instrument[instrument].forward_return)
            for instrument, value in holdings.items()
        }
        end_nav = cash + sum(holdings.values())
        periods.append(
            BacktestPeriod(
                execution_at=execution_at,
                return_end_at=rows[0].return_end_at,
                rebalanced=rebalanced,
                selected_instruments=selected,
                start_nav=start_nav,
                end_nav=end_nav,
                gross_return=profit / start_nav,
                net_return=end_nav / start_nav - 1,
                turnover=traded_notional / (2 * start_nav),
                traded_notional=traded_notional,
                total_cost=total_cost,
                cash_after_execution=cash,
                orders=orders,
            )
        )
    return BaselineReport(
        method_version=METHOD_VERSION,
        lineage=lineage,
        config=config,
        metrics=_metrics(periods, initial_nav, config),
        periods=tuple(periods),
    )
