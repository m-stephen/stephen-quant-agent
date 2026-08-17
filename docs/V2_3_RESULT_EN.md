# V2.3 Style Residualization Result

Status: **PROMOTE_RESEARCH_ONLY**. The single registered candidate materially improves the
consumed research sample, but it does not pass multiplicity-adjusted Alpha Court. This is not
evidence from 2025/2026 and is not investment advice.

## Result

| Variant | Net return | Annualized net Sharpe | Maximum drawdown | Turnover | Cost (CNY) |
|---|---:|---:|---:|---:|---:|
| Raw Top-5 | 34.74% | 0.4266 | -28.42% | 32.4226 | 205,533.14 |
| Style-residualized Top-5 | 63.71% | 0.6028 | -21.12% | 32.8054 | 226,029.47 |

Residualization improved net return by 28.97 percentage points, annualized net Sharpe by
0.1762, and maximum drawdown by 7.30 percentage points. No capacity clipping occurred.

## Integrity and falsification

- The raw control reproduced V2.1 exactly.
- 34,143 observations across 685 decision dates were residualized.
- Mean absolute residual correlation was `7.27e-16` to price momentum and `1.30e-13` to
  `log(ADV20)`; forward returns were not used in fitting.
- Reversed residual ranking produced -0.2575 annualized Sharpe and -52.56% net return.
- Signal-shuffle and return-permutation placebo p-values were both 0.005; inherited PBO was 0.
- The two new trials brought the cumulative ledger to 44.
- Offline replay verified all three artifacts and registry audit confirmed exactly two trials.
- 2025 and 2026 remained sealed.

## Decision

All execution and falsification gates passed except DSR. Trial-aware DSR rose to 0.581752 but
remained below the frozen 0.95 threshold. The residualized signal is therefore the preferred
research candidate, but it does not replace the production/reference claim as a proven Alpha.

The next independent epoch should test temporal stability of this exact frozen residualized
mapping through pre-registered rolling/walk-forward subperiod gates, without changing its
formula or opening the sealed windows.
