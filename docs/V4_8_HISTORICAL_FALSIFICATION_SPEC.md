# V4.8 Frozen Candidate Historical Falsification Protocol

This protocol tests the already-frozen V4.8 candidate on 2020–2021 without changing its identity.

## Frozen inputs

- candidate fingerprint `49bbaa53abab3f00a43011565235529629d807e8712eafc163e020f10ab9fec7`;
- equal percentile rank of `flow_price_divergence_5_20d` and `auction_strength_5_20d`;
- `AVOID` bottom 10, 10-rank holding buffer and 20-session horizon;
- CNY 3 million NAV, 5% participation and the existing standard/2x cost models;
- DSR 0.95, placebo 0.05, 15/20 positive paths and positive median path Sharpe.

## Historical universe

Rebuild 2020–2021 membership under the V1.8.11 contract: same-day fundamental metadata, trailing
20-session liquidity, minimum 120-session history, CNY 20 million liquidity floor, top 300 ranked
members and first 50 names used for execution. A predeclared list of 14 empty or schema-incomplete
fundamental partitions produces no new decision on those dates. Missing fields are never imputed.

## Evidence status

This is post-discovery backward temporal falsification. It may reject the candidate or strengthen a
mechanism hypothesis, but it can never be relabelled as forward out-of-sample evidence. The test
records exactly two inferential Trials, standard and doubled cost, and prohibits all parameter search.

