# V5.0 Market-wide Balanced-universe Alpha Search Result

## Decision

V5.0 removes the narrow, large-cap-biased liquidity Top50 universe and finds the strongest lead
for append-only forward validation so far. The frozen decision is nevertheless
`NO_DEVELOPMENT_ALPHA`: the only failed gate is multiplicity-adjusted DSR after 1,206 recorded
inferential attempts.

The selected cross-domain ensemble contains:

- `chip_cost_gap_reversal_5_20_20d`: a 20-session reversal signal when price is elevated relative
  to the recent five-day holder-weighted cost basis, consistent with profit-taking pressure.
- `flow_price_divergence_20_20d`: 20-day normalized net inflow minus contemporaneous price return,
  intended to capture buying pressure that has not yet been reflected in price.

Their daily-IC correlation is 0.1337. Four of 36 predeclared candidates passed cross-year
stability; only these two orthogonal domains were promoted to the full validation panel.

## Universe expansion

| Metric | Result |
|---|---:|
| Mean full eligible mother pool | 4,081.51 names/day |
| Minimum / maximum | 3,033 / 5,066 |
| Unique historical names | 5,121 |
| Former Top50 mean share | 1.253% |
| Balanced screening panel | about 300 names/day |
| Balanced validation panel | about 1,200 names/day |
| Mean one-way membership turnover | 0.1300% |

The eligible pool has no liquidity-rank truncation. Each day is split 30%/40%/30% into
large/mid/small capitalization buckets, followed by stable SHA-256 sampling within each bucket.
Membership becomes usable only on the next trading session.

## Portfolio and stress evidence

The reused historical window is 2022–2024 with a BUY Top50 portfolio and a 20-session horizon.
2022 is development, 2023 confirmation and 2024 a reused shadow period. No 2025/2026 data was
used for candidate generation or tuning.

| NAV and cost | Matched-control excess | Increment | Incremental daily Sharpe | Positive paths | Drawdown | Capacity clipped |
|---|---:|---:|---:|---:|---:|---:|
| CNY 3m, standard | +31.27% | +32.72% | 3.8360 | 19/20 | -5.88% | 0 |
| CNY 3m, doubled | +16.63% | +19.22% | 2.3877 | 16/20 | -6.83% | 0 |
| CNY 20m, standard | +31.27% | +32.72% | 3.8360 | 19/20 | -5.88% | 0 |
| CNY 20m, doubled | +16.63% | +19.22% | 2.3877 | 16/20 | -6.83% | 0 |

These are historical excess returns against a matched no-signal control, not account-level
absolute returns or a forecast. Neither NAV triggered the frozen 5% participation cap.

## Size and liquidity slices

| Slice | RankIC | Increment | Matched-control excess | Positive paths |
|---|---:|---:|---:|---:|
| Large | 0.0860 | +27.51% | +25.87% | 20/20 |
| Mid | 0.1305 | +34.08% | +31.65% | 20/20 |
| Small | 0.0953 | +22.62% | +20.18% | 20/20 |
| High liquidity | 0.1186 | +32.46% | +27.86% | 20/20 |
| Mid liquidity | 0.0991 | +36.18% | +28.09% | 20/20 |
| Low liquidity | 0.0769 | +22.27% | +17.26% | 20/20 |

Every slice is positive. The evidence is therefore not confined to large, highly liquid stocks;
mid caps are strongest while small and low-liquidity names retain positive contributions.

## Alpha Court

| Gate | Frozen threshold | Result | Status |
|---|---:|---:|---|
| Positive stress fraction | >=75% | 100% | PASS |
| PBO | <=0.05 | 0 | PASS |
| Signal placebo p | <=0.05 | 0.005 | PASS |
| Return placebo p | <=0.05 | 0.005 | PASS |
| DSR | >=0.95 | 0 | **FAIL** |

DSR uses the empirical incremental-return skewness of 1.1900 and excess kurtosis of 5.9708. It
also includes prior research, the 46 revealed attempts from the interrupted audit run, and the
46 final rerun attempts, for 1,206 recorded Trials. Positive skew and fat tails do not overcome
the multiplicity penalty.

## Next steps

1. Freeze the two formulas, equal-rank ensemble, Top50 breadth, 20-session horizon, universe,
   and cost model. Do not tune them on 2022–2026 again.
2. Register an append-only forward candidate and rerun without tuning after at least 25 genuinely
   new common trading sessions arrive.
3. Give any new search an independent trial budget and a different economic mechanism, preferably
   corporate actions, margin financing or auction microstructure. Do not scan neighboring windows
   around this ensemble.
4. Improve caching and chunking to reduce the roughly 13 GB full-panel peak without changing the
   sample or metric definitions.

## Evidence boundary

- Dataset and membership hashes are frozen; raw data and local paths remain outside Git.
- All 2022–2024 observations are reused development evidence, not fresh out-of-sample proof.
- `NO_DEVELOPMENT_ALPHA` does not mean the ensemble is useless; it means the evidence cannot yet
  overcome the accumulated search bias.
