# V5.0 Market-wide Balanced-universe Alpha Search

Tracking issue: #116

## Objective

Replace the liquidity-ranked Top50 research universe with a market-wide,
point-in-time investable mother pool. Preserve small- and mid-cap exposure while
keeping research cost bounded and every empirical attempt in the trial ledger.

V5.0 is a search-system validation release. It does not authorize live trading,
and it does not turn reused historical evidence into a new untouched test.

## Frozen universe

- A-share instrument with a known listing date and at least 120 prior sessions.
- Exclude ST, delisting-marked, suspended, and otherwise non-trading rows.
- Require valid vendor market capitalization and 20-session mean traded amount
  of at least CNY 10 million.
- Do not apply a liquidity-rank top-N truncation to the eligible mother pool.
- Form daily size buckets at 30% large, 40% mid, and 30% small; form liquidity
  terciles independently.
- Make each decision-date membership effective on the next trading session.
- Select up to 400 instruments per size bucket for the validation panel using a
  stable SHA-256 instrument ordering. Select the first 100 of each bucket for
  candidate screening. This yields approximately 1,200 validation names and
  300 screening names per day without selecting only the largest stocks.
- Treat explicitly listed historical fundamental-source omissions as missing;
  never impute them silently.

## Frozen search and validation

- Screen 36 direction-complete, predeclared candidates from auction, fund-flow,
  and chip domains on the balanced screening panel.
- Promote only directionally stable candidates, then select an orthogonal set
  using daily-IC correlation no greater than 0.75.
- Recompute only the promoted candidates on the balanced validation panel.
- Use a BUY Top50 portfolio with a 20-session horizon.
- Treat 2022 as development, 2023 as confirmation, and 2024 as a reused shadow
  period. Prohibit 2025 and 2026 from candidate generation or optimization.
- Run purged CPCV with 6 groups, 3 test groups, and a 5-day embargo.
- Carry all prior inferential attempts and the portfolio's empirical return
  skewness and excess kurtosis into DSR; run signal-shuffle and
  return-permutation placebos with 199 repetitions each.

## Execution stresses

- Net asset values: CNY 3 million and CNY 20 million.
- Standard costs: 3 bps commission, 5 bps sell tax, 5 bps slippage, and 10 bps
  impact; repeat at double cost.
- Maximum participation: 5% of traded amount.
- Report large/mid/small and high/mid/low-liquidity slice diagnostics.

## Frozen Alpha Court

- Development incremental daily Sharpe: at least 0.50.
- Positive return and positive excess return in at least 75% of stress cases.
- Deflated Sharpe Ratio probability: at least 0.95.
- Probability of Backtest Overfitting: at most 0.05.
- Signal-shuffle and return-permutation empirical p-values: each at most 0.05.
- At least two orthogonal information domains.

Only a candidate satisfying every frozen gate may be reported as `PASS`.
Regardless of the decision, the result remains historical research evidence and
requires append-only forward validation on genuinely new data before deployment.
