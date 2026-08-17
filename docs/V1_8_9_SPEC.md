# V1.8.9 — Predeclared Factor Family Validation

## Objective

Validate the five factors frozen by the V1.8.8 training-only redundancy screen without expanding
the search space after seeing 2024 results. Each factor is one independent Trial in a single
shared Experiment and snapshot.

## Frozen factor family

1. `mom_120_skip_20@1.0.0`
2. `trend_efficiency_20@1.0.0`
3. `range_position_20@1.0.0`
4. `volume_surprise_5_20@1.0.0`
5. `parkinson_vol_20@1.0.0`

No parameter variants or replacements are allowed in this validation family.

## Frozen evaluation design

- Training reservation: 2022-01-01 through 2023-12-31.
- Validation: 2024-01-02 through 2024-12-31.
- Sealed test reservation: 2026-01-05 through 2026-08-14.
- Universe and frozen snapshot are identical across all five Trials.
- Portfolio: top 5, rebalance every 5 trading days, 2% cash reserve, 20% maximum position.
- Costs: 3 bps commission, 5 bps sell tax, 5 bps slippage, 10 bps market impact.
- Maximum participation: 5% of observed daily volume.
- Benchmark: CSI 300.
- Falsification: 199 placebo repetitions per Trial.

The 2026 files must not be loaded or hashed during validation.

## Family-level decision

Select the accepted Trial with the highest net validation Sharpe. The factor family passes only
when that winner satisfies every condition:

1. Net Sharpe is positive.
2. Net return exceeds CSI 300 over the matched validation dates.
3. The placebo audit passes.
4. Deflated Sharpe Ratio is at least 0.95 using the complete recorded Trial count.

Failure of any condition rejects the family and keeps the 2026 test sealed. The report must still
include all Trials, including rejected or failed attempts, so retrying cannot erase multiplicity.

PBO is not reported here because this stage does not fit an audited CPCV performance matrix.
Claiming PBO from a single validation path would give false precision.
