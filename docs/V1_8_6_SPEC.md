# V1.8.6 — Research-grade QD validation

V1.8.6 lives on the long-running `data-test` branch. It turns the V1.8.5 engineering backtest into
a stronger research validation by removing the manually chosen test universe, adding a declared
benchmark, and actively trying to falsify the factor signal.

## Training-only universe

`qd-select-universe` reads only daily partitions inside the declared training window and the latest
fundamental partition available on or before the training end date. It selects instruments that:

- have positive amount data in every training session;
- do not contain `ST` in the point-in-time name;
- were listed no later than the training start date; and
- rank in the requested top N by mean training-period daily amount.

Blank or zero listing dates are treated as unknown and excluded, with the exclusion count retained
in the audit. Other malformed non-empty listing dates are rejected as source errors.

The command freezes the exact daily and fundamental source files and writes a JSON audit, Markdown
summary, and plain-text stock list. Test and validation returns never influence membership or rank.

## Benchmark comparison

The backtest can load a declared index CSV and compare strategy and benchmark over identical
open-to-next-open windows. The audit records total and annualized return, Sharpe, maximum drawdown,
tracking error, information ratio, and the benchmark source SHA-256.
Source rows with a blank open are counted and excluded; a missing open on any strategy return
boundary still rejects the comparison.

## Placebo audit

When `--placebo-repetitions` is positive, the workflow runs both signal-shuffle and
return-permutation tests using deterministic seeds. The result passes only when both empirical
p-values are at or below 0.05. A failed placebo decision does not erase the run: it is retained as
evidence that the candidate factor was rejected.

## Integrity boundary

- Every backtest still freezes its market-data snapshot and registers a Trial before evaluation.
- Explicit commission, sell tax, slippage, impact, and capacity limits remain mandatory inputs.
- No missing bars are forward-filled and no future fundamental partition is consulted.
- This milestone does not claim executable suspension or price-limit handling.
- PBO and DSR are not reported from a single fixed strategy. They become meaningful only after the
  ledger contains a legitimate multi-trial research family evaluated with audited folds.

The output is stronger out-of-sample evidence, not a live-trading guarantee.
