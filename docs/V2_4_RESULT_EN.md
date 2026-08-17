# V2.4 Temporal Stability Result

Engineering status: **RESEARCH_PREVIEW_READY**. Alpha status:
**RESEARCH_PREVIEW_ONLY**.

The frozen execution exactly reproduced V2.3: 63.71% net return, 0.6028 annualized net
Sharpe, -21.12% maximum drawdown, CNY 226,029.47 cost, and no capacity clipping.

## Calendar-year evidence

| Year | Periods | Net return | Annualized net Sharpe | Maximum drawdown |
|---|---:|---:|---:|---:|
| 2022 | 12 | 7.29% | 0.3520 | -21.12% |
| 2023 | 12 | -8.77% | -0.4145 | -19.27% |
| 2024 | 11 | 67.26% | 1.2553 | -8.91% |

Two of three years were positive, and the worst-year return remained above the frozen -10%
floor. However, 2023 Sharpe failed the -0.25 floor. The weakest rolling 12-period Sharpe was
-0.5095 and also failed; rolling drawdown passed at -21.12%.

The top-decile absolute-return contribution was 45.16%, below the 50% ceiling. Both inherited
placebos remained 0.005 and signal-selection PBO remained 0. Moment-corrected DSR was 0.602876
after 45 recorded trials, below the required 0.95.

## Decision

The system is reproducible, fail-closed, capacity-aware, replayable, and safe to publish as a
disabled-by-default research preview. The strategy is temporally uneven and does not pass
Alpha Court. Neither 2025 nor 2026 was opened.
