# V1.5 — Momentum Top-K Baseline

V1.5 establishes a simple, auditable portfolio baseline before any reinforcement-learning layer.

## Point-in-time contract

1. Signal and liquidity data must both be available strictly before execution.
2. Each execution cross-section must contain every currently held asset.
3. The forward return window must begin after execution and cannot be used for ranking.
4. Equal signals are resolved deterministically by instrument ID.
5. Sequential forward-return windows cannot overlap.

## Portfolio contract

- Rank by the declared factor direction and hold the first `K` assets.
- Use equal target weights, capped by `max_position_weight`.
- Keep `cash_reserve` plus any exposure left unused by concentration limits in cash.
- Rebalance only on the configured schedule; intermediate periods keep drifting positions.
- Long-only positions and non-negative cash are enforced after every execution.

## Execution and cost contract

- Maximum order size is `average_daily_value * max_participation_rate`.
- Capacity-limited orders are clipped rather than assumed filled.
- Sells execute before buys; buys are proportionally reduced if cash cannot cover trades and costs.
- Commission and slippage are linear in absolute traded notional.
- Market impact is `notional * impact_coefficient_bps * sqrt(participation) / 10,000`.
- Costs are deducted from cash before the forward return is applied.

The report records desired and executed notional, participation, capacity clipping, funding clipping,
and each cost component for every order.

## Metrics

The default headline result is net of costs. Reports include gross and net total return, final NAV,
annualized net return and volatility, net Sharpe, maximum drawdown, turnover, traded notional, total
cost, and clipping diagnostics.

Period gross return uses the actually executed holdings before that period's costs. Turnover is half
the absolute traded notional divided by start-of-period NAV. It is not inferred from target weights.

## Integrity constraints

Cost, capacity, concentration, cash, and rebalance assumptions are versioned trial inputs. Changing
any assumption creates another trial. The final test window is not used to select these assumptions.
