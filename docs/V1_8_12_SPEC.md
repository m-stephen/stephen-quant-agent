# V1.8.12 — Stateful Sparse-Panel Execution

## Objective

Value and execute a dynamic-universe portfolio without deleting holdings when a daily row is
missing and without inventing tradable returns during suspensions.

## Frozen accounting rules

- Targets must be timestamped before the execution open.
- Long-only target weights cannot exceed the configured position limit or 100% in aggregate.
- Sells execute before buys; buys are scaled proportionally when cash is insufficient.
- Commission, sell tax, and slippage are explicit. Order capacity must be supplied from information
  available before the open, never from same-day closing volume.
- An upper-limit open blocks buys; a lower-limit open blocks sells.
- ST or delisting status removes the asset from targets and creates a forced-exit intent, but the
  position remains when the open is not sellable.

## Missing-bar policy

When an existing holding is absent from a daily partition:

1. Trading is blocked and recorded as `missing_bar_suspension`.
2. For the first 19 missing exchange sessions, NAV uses the last observed close with an explicit
   `stale_sessions` count and `explicit_stale_last_close` source.
3. On the 20th consecutive missing session, the mark is conservatively reduced to zero and the
   write-off is recorded. This is a risk control, not an assertion that the legal claim vanished.
4. If a quote later reappears, the current open restores the observable value, records a recovery,
   and any pending exit may execute.

An unchanged stale mark is an explicit valuation state; it is never presented as an observed zero
return. Overnight gaps, write-offs, and recoveries flow through continuous NAV from the previous
session close.

## Scope

V1.8.12 provides the reusable execution/accounting engine and adversarial tests for suspension,
price-limit exit blocking, permanent disappearance, recovery, funding, timing, and costs. It does
not spend the reserved 2025 validation window or run a new alpha experiment.
