# V5.4 Alpha Conversion Diagnostics and Constrained Generation Test Report

## Final decision

V5.4 found no candidate eligible for formal validation. The decision is `NO_CONVERTIBLE_ALPHA`.

The test resolves the main ambiguity from prior versions: candidates are not failing only because Alpha Court is strict. They fail earlier, when statistical ranking information must become costed portfolio return. Across the 36-cell fixed-formula grid, the best cell produced **+1.72% gross excess** and **-1.69% net excess**. The 12 constrained new candidates produced zero stable survivors and spent no downstream stress Trials.

## Evidence scope and Trial ledger

- 2021 supplies lookback; 2022–2024 are reused development evidence;
- CNY 3m NAV;
- fixed diagnostics: 3 formulas × 4 horizons × 3 breadths = 36 Trials;
- constrained generation: 6 new mechanism templates × two directions = 12 Trials;
- stress validation: 0 Trials;
- the first runtime exposed an unreachable fixed 12-path gate for five-session signals; all 48 Trials remain recorded;
- a corrected 60%-of-offsets gate was replayed through another 48 Trials;
- cumulative Trial count: **1,328**;
- input snapshot SHA-256: `e7302bb0abeba41e5c55e30e1e0a49fa8a15375f945bd423caa8e14b796f0fb5`;
- all economic metrics were identical across both runs, with economic-result SHA-256 `c247ca2995a6214993f1f0e43680a6809436956868ed31deaa37c18afeda169c`.

## Fixed-formula diagnostics: every grid cell had negative net excess

| Horizon | Best net excess at horizon | Corresponding best gross excess | Interpretation |
|---:|---:|---:|---|
| 1 session | -11.90% | -5.56% | high turnover and tail loss dominate |
| 5 sessions | -4.26% | -0.14% | a shorter horizon does not fix conversion |
| 10 sessions | **-1.69%** | +1.72% | best net cell remains negative |
| 20 sessions | -1.82% | **+7.98%** | broader selection improves gross return but not net return |

The best overall cell is negative-direction limit-up seal strength, a 10-session horizon and Top20 breadth. Three-year gross excess is +1.72%, net excess is -1.69%, and cost tolerance is only 0.50 times standard cost. Annual net excess is -11.36%, +5.48% and +5.15%, with 0/10, 5/10 and 7/10 positive paths. This is a regime-dependent signal that failed badly in 2022, not a stable Alpha.

The runner-up is auction price absorption at 20 sessions and Top100: +7.98% gross, -1.82% net and 0.81 times standard-cost tolerance. Annual net excess is -1.37%, -1.04% and +0.58%. Greater breadth reduced concentration but did not produce cross-year positive performance.

## Why positive RankIC did not become return

The limit-seal signal has annual RankIC around 0.055–0.063, yet Top20 quantile monotonicity is -0.297, +0.224 and -0.164, while Top-Bottom return is negative in 2022 and 2024. Its positive RankIC comes mainly from weak ordering through the middle of the cross-section, not persistent outperformance in the extreme top tail. A fixed Top20 or Top50 portfolio concentrates capital exactly where the relationship is unstable.

The failures separate into two mechanisms:

1. **Event signals have a shape problem.** Limit-event and auction candidates often lose money even before costs; lower fees cannot repair non-monotonic, sparse or regime-dependent signals.
2. **Margin signals have a cost-and-decay problem.** Some gross edge exists, but it does not reliably cover turnover and weakens in later years.

## Constrained generation: the only near lead still decays

| Candidate | 2022/2023/2024 RankIC | Annual net excess | Paths | Decision |
|---|---|---|---|---|
| Negative margin net demand, 20 sessions | 0.0461 / 0.0079 / 0.0205 | +5.05% / -1.47% / -1.33% | 16/20, 9/20, 8/20 | unstable |
| Negative limit-seal retention, 5 sessions | 0.0605 / 0.0449 / 0.0624 | -12.61% / -3.86% / -7.09% | 0/5, 0/5, 0/5 | reject |
| Negative limit main-flow/float-cap, 5 sessions | 0.0500 / 0.0400 / 0.0512 | -15.06% / -4.07% / -8.85% | 0/5, 0/5, 0/5 | reject |
| Positive auction amount absorption, 5 sessions | 0.0360 / 0.0195 / 0.0380 | -15.17% / -19.10% / -10.88% | 0/5, 0/5, 0/5 | reject |

Negative margin net demand is the only mechanism worth further explanation: three-year compounded gross excess is +12.72%, net excess is +2.12%, and it tolerates about 1.20 times standard cost. But 2022 supplies the gain; 2023 and 2024 net returns and paths both fail. A positive three-year total cannot override that decay.

## Updated diagnosis of the system

1. **Universe breadth is no longer the primary bottleneck.** Top20, Top50 and Top100 all fail net.
2. **A single holding horizon is not the sole cause.** One-, five-, ten- and twenty-session variants all remain negative net.
3. **RankIC alone is insufficient.** Extreme-quantile monotonicity, Top-Bottom direction, gross return and net return must agree.
4. **Event candidates are poorly represented as continuous daily Top-N factors.** They are better candidates for event-triggered conditions, filters or avoidance rules.
5. **The constrained generator correctly limits search and stops early**, but its expression structure—not the number of nearby windows—now needs improvement.

## Recommended next step

V5.5 should focus on conditional events and low-turnover conversion:

1. Use negative margin net demand as a filter on an existing low-turnover portfolio, testing whether it can reduce trading while retaining gross edge.
2. Reframe limit and auction inputs as event-triggered studies on observed events only, rather than mixing many zero-valued non-events into a continuous daily ranking.
3. Add three hard screening gates: quantile monotonicity, RankIC-aligned Top-Bottom return, and break-even cost of at least 1.5 times the standard model.
4. Do not tune around the observed Top20/10-session best cell; it is consumed development evidence.

This version does not authorize live trading or deployment of CNY 3m into any tested candidate.
