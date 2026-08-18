# V5.2/V5.3 Dual-track Research Protocol

## Track A — frozen prospective validation

Freeze date: `2026-08-16`. No observation on or before that date may change a formula, direction,
weight, universe rule, breadth, horizon, cost model or gate.

Three observation lines are preregistered:

1. the V5.1 equal-rank chip-cost-gap and flow-price-divergence ensemble;
2. the same ensemble residualized against prior-known size, liquidity, 20-session momentum and
   20-session volatility;
3. `flow_price_divergence_20_20d` alone.

Coverage is the intersection of daily, fund-flow and chip partitions after the freeze date. The
system reports:

- fewer than 25 sessions: `WAITING_FOR_DATA`, no performance Trial;
- 25–59 sessions: early-warning test only;
- 60–119 sessions: preliminary forward assessment;
- at least 120 sessions: decision-eligible assessment.

Forward performance additionally requires a point-in-time market-wide membership/tier artifact
covering every execution date. Missing membership is a blocker, never backfilled from future
constituents. Standard and conservative execution, 20 offset paths, placebo, empirical-moment DSR
and append-only Trial lineage remain mandatory.

## Track B — independent-mechanism discovery

Track B reuses 2022–2024 only as development evidence and receives a separate fixed budget of 14
candidate Trials. It excludes chip-cost and fund-flow-divergence formulas.

Predeclared direction-complete candidates:

- margin buy intensity (20 sessions): both directions;
- margin demand acceleration (5 versus 20): both directions;
- margin-price crowding interaction (20 sessions): both directions;
- auction-price absorption (5 sessions): both directions;
- limit-up persistence (20 sessions): both directions;
- limit-event main-net intensity (5 sessions): both directions;
- closing seal strength (5 sessions): both directions.

Screening uses the frozen size-balanced panel of roughly 300 names per day. Candidates must have
positive 2023 and 2024 RankIC, at least two positive-return years, no year RankIC below -0.02 and
no severe decay. At most one candidate per economic domain proceeds to the roughly 1,200-name
validation panel. Validation uses standard, doubled and conservative execution at CNY 3m, BUY50,
20 sessions and 20 offset paths. The selected ensemble is tested both raw and residualized against
prior-known size, liquidity, 20-session momentum and 20-session volatility, under standard,
doubled and conservative execution. The residualized ensemble must remain positive under standard
and conservative execution with at least 15/20 positive conservative paths. Purged CPCV/PBO, both
placebo tests and DSR >= 0.95 are mandatory. The budget is 14 candidate Trials plus at most six
fixed validation Trials. Trial accounting starts from the V5.1 cumulative total of 1,218.

No candidate or direction may be added after results are observed. Track B can produce a new
development lead, never a final or deployable Alpha from the reused historical window.
