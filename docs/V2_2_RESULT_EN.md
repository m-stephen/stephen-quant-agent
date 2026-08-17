# V2.2 Portfolio Breadth Result

Status: **REJECT_NO_IMPROVEMENT**. This is a valid negative research result, not an engineering
failure. Only the previously consumed 2022–2024 research window was used; it is not evidence
from the sealed 2025/2026 windows and is not investment advice.

## Integrity evidence

- The Top-5 control exactly reproduced V2.1: 34.7435% net return, 0.426572 annualized net
  Sharpe, and -28.4219% maximum drawdown.
- The frozen source snapshot, signal schema, and signal fingerprint matched.
- Five new trials were registered, bringing the cumulative ledger from 37 to 42.
- The reverse-rank control had -0.493319 annualized Sharpe and -68.82% net return.
- Signal-shuffle and return-permutation placebo p-values were both 0.005; inherited PBO was 0.
- Offline replay verified all three hashed artifacts, and the registry audit passed.
- Neither the 2025 validation window nor the 2026 final-test window was opened.

## Breadth comparison

| Top-K | Net return | Annualized net Sharpe | Maximum drawdown | Turnover | Cost (CNY) |
|---:|---:|---:|---:|---:|---:|
| 5 | 34.74% | 0.4266 | -28.42% | 32.4226 | 205,533.14 |
| 10 | 29.59% | 0.4063 | -23.21% | 30.6986 | 198,067.38 |
| 15 | 17.55% | 0.3214 | -21.48% | 27.8720 | 169,884.96 |
| 20 | -2.31% | 0.0895 | -23.68% | 25.4643 | 139,385.25 |

No portfolio was capacity-clipped. Top-10 and Top-15 improved drawdown, but the frozen
selection rule correctly retained Top-5 because every broader portfolio reduced Sharpe.

## Decision

The breadth-change, Sharpe-improvement, maximum-drawdown, and DSR gates failed. DSR was
0.500759 against the required 0.95. Therefore V2.2 does not replace the V2.1 reference
portfolio. The evidence supports keeping the signal as a research candidate while rejecting
the claim that breadth alone makes it a reliable alpha.

The next epoch should test one pre-registered risk-control mechanism—such as industry/style
residualization or volatility-aware sizing—without reopening factor search or the sealed
windows.
