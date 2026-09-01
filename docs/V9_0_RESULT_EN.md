# V9.0 automatic alpha discovery test report

## Decision

The engineering release passes, but the alpha validation does not. The final decision is
**`NO_RELIABLE_ALPHA`** and the candidate must not be deployed.

Synthetic search-power calibration passed. The planted signal ranked first, with discovery RankIC
0.1057 and holdout RankIC 0.1210. The best null candidate fell from 0.0408 in discovery to 0.0026
in holdout. A deliberately leaked positive control reached RankIC 1.0 and was detected. Planning
froze 50 candidates across nine mechanism families without reading real labels or consuming a Trial.

The empirical replay used manifest-bound daily-bar and fund-flow snapshots and restored the frozen
V8.1 flow-price-divergence candidate. The portfolio used CNY 3m NAV, Top40, a ten-name buffer,
41 bps round-trip cost, doubled-cost stress, capacity checks, and 199 signal-shuffle placebos.

| Segment | Rebalances | Net excess | Annualized excess Sharpe | Double-cost return | Max drawdown | Placebo p | Gate |
|---|---:|---:|---:|---:|---:|---:|---|
| 2015–2017 discovery | 37 | 18.15% | 0.703 | 4.73% | -12.14% | 0.010 | PASS |
| 2018 validation | 13 | 18.58% | 1.772 | 13.89% | -1.97% | 0.005 | PASS |
| 2019 frozen test | 13 | -4.53% | -0.183 | -8.14% | -13.67% | 0.510 | FAIL |
| 2020–2021 confirmation | 25 | 1.42% | 0.122 | -6.24% | -11.88% | 0.180 | FAIL |
| 2022–2024 stress | 36 | -3.83% | -0.024 | -14.17% | -22.18% | 0.185 | FAIL |

Estimated capacity remained above CNY 300m, so the failure is not caused by the CNY 3m capital
constraint. It is a loss of out-of-sample efficacy. The historical Trial baseline is 533 and every
local replay attempt remains in the registry. The complete historical Trial-Sharpe matrix is not
recoverable from current artifacts, so DSR/PBO were not fabricated and the Court fails closed.
No 2025–2026 labels were queried.
The stable analysis hash is `1f004f3e54a1c12948ec4434b21929b5b29b87b7c8f790d0ea89403aa62d5443`.

## Interpretation

The attractive early result does not survive later regimes. The V8.1 candidate is therefore more
consistent with a period-specific liquidity effect than durable alpha. V9.0's value is that it can
detect and document this failure. The next campaign should consume the frozen multi-candidate packet
and preserve complete path-return matrices rather than tuning this rejected candidate.
