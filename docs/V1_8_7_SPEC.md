# V1.8.7 — Validation diagnostics and tradability

V1.8.7 lives on the long-running `data-test` branch. It diagnoses the frozen V1.8.6 candidate on
the validation window without reading the reserved 2026 final-test data, and makes open execution
more conservative for A-share price limits.

## Validation-only contract

With `--evaluation-window validation`, the workflow:

- registers the Trial before evaluation;
- freezes QD partitions only from training start through the first session after validation end;
- computes signals, returns, benchmark comparison, and placebos only on validation dates; and
- retains the declared final-test dates in the ledger without loading or hashing their files.

This mode is accepted only for date-partitioned directories. A monolithic CSV could expose future
rows in the frozen source and is therefore rejected.

## Conservative open-limit execution

QD daily rows contain the security name, previous close, and open. At the 09:30 execution point,
the adapter infers the daily limit using information available by then:

- Shanghai/Shenzhen main-board prefixes: 10%;
- historical main-board ST names: 5% before 2026-07-06, then 10%;
- ChiNext and STAR prefixes, including ST names: 20%;
- Beijing exchange or 4/8 prefixes: 30%;
- names beginning with `N` or `C`, or opens outside the ordinary calculated band: no-limit session
  or conservative no-limit inference.

Prices are rounded to a CNY 0.01 tick with half-up rounding. A buy at the upper limit or a sell at
the lower limit receives zero execution. The desired but blocked notional and blocked-order count
are reported separately from liquidity-capacity and cash-funding clipping.

This is a conservative open-auction assumption, not a queue-fill simulator. It is intended for the
training-selected, seasoned-stock universe; IPO no-limit periods are outside the supported rule.
When name or previous close is absent, the audit marks tradability as unavailable rather than
claiming that the check ran.

See `docs/QD_PRICE_LIMIT_RULES.md` for the board prefixes, historical exceptions, formulas, and
official exchange sources.

## Suspension rule

QD omits suspended rows. Missing held assets remain a hard error and are never forward-filled or
silently treated as executable. A later milestone may add an explicit stale mark-to-market state,
but V1.8.7 does not invent prices for absent bars.

## Decision rule

The validation run is diagnostic evidence. It cannot change the already frozen factor, lookback,
portfolio, or cost assumptions using the observed 2025 final-test result. The reserved 2026 window
may be opened only after the next candidate specification is frozen and all validation checks pass.
