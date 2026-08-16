# V1.8.12 — Frozen Stateful-Execution Result

## Decision

**PASS_ENGINEERING.**

The sparse-panel execution engine preserves holdings across missing rows, accounts continuously
for overnight gaps, blocks impossible orders, and records conservative write-offs and later
recoveries without fabricating observed returns.

This is an execution-engine result, not an alpha result. No new Experiment or Trial was created,
and no reserved 2025 or 2026 market data was read.

## Lineage

- Implementation commit: `9eab667`.
- Method: `stateful-dynamic-universe-execution-1.0.0`.
- Dedicated stateful tests: 7/7 passed.
- Complete project tests: 113/113 passed.
- Static checks: passed.

## Verified cases

1. **Suspension** — a missing held asset remains in positions, cannot trade, and carries an
   explicit `stale_sessions` counter and `explicit_stale_last_close` mark source.
2. **Trading resumption** — the reappearing open recognizes the complete price gap against the
   prior continuous NAV before a pending exit executes.
3. **Conservative disappearance** — the twentieth consecutive missing session writes the mark to
   zero and records the loss without deleting the legal position.
4. **Recovery after write-off** — a later observable open records recovery value; if previous NAV
   was zero, the period return is `N/A` rather than a fabricated finite or infinite return.
5. **Limit-down forced exit** — ST or delisting intent cannot sell at an untradable lower-limit
   open; the holding persists until an executable session.
6. **Point-in-time capacity** — order capacity carries its own availability timestamp and is
   rejected unless known before the execution open.
7. **Funding and costs** — sells precede buys, buys scale proportionally to available cash,
   capacity clips are explicit, and commission, sell tax, and slippage cannot create hidden
   negative cash.

## Frozen policy

- Missing sessions 1–19: explicit stale last-close valuation; no trading.
- Missing session 20: conservative zero mark.
- Later reappearance: observable-value recovery followed by the pending executable action.
- Existing ST/delisting holding: target weight zero, but no assumed sale while the market blocks
  the order.
- Missing holdings are never removed from positions merely because their K-line row is absent.

## Remaining integration work

The engine currently accepts audited bars and target weights. V1.8.13 must bridge the V1.8.11
daily membership JSONL and QD sparse daily bars into this engine, calculate capacity strictly from
prior-session history, and run a 2022–2024 engineering backtest. That run must use a new research
Experiment and Trial ledger and must not open the 2025 or 2026 windows.
