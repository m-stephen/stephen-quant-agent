# V6.3 — Append-only Forward Shadow Validation

## Objective

Accumulate genuinely new evidence after candidate freeze without turning that evidence into another
tuning window.

## Protocol and ledger

The protocol freezes candidate semantic identity, last revealed date, required source names, cost
model, portfolio configuration and a minimum of 25 new common sessions. Each observation binds the
protocol, session, every source snapshot hash, standard and doubled-cost net excess return, and UTC
availability time.

Observations must be strictly later than the freeze date and strictly increasing. Missing sources,
duplicates, out-of-order sessions, non-UTC timing, protocol mismatches and ledger tampering fail
closed. Rows form an append-only SHA-256 previous-entry chain.

Before 25 sessions, the summary is `WAITING_FOR_FORWARD_DATA` and all performance metrics are null.
At 25 or more it exposes cumulative standard/doubled-cost excess and annualized Sharpe as forward
evidence. It never proposes parameter changes and adds no inferential Trial.
