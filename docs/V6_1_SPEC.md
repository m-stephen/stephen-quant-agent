# V6.1 — Tamper-evident Research Memory

## Objective

Make past attempts, failures and Trial costs reusable by the automatic controller. A failed idea must
not become “new” merely because its display name changed.

## Ledger contract

Each append-only JSONL event binds semantic identity, stage, outcome, failure code, Trial delta,
cumulative Trial count, evidence-snapshot SHA-256, UTC availability and parent identities. Its stable
event identity excludes the proposal display name. Every row hashes the previous row, producing a
deterministically replayable chain.

Replay fails on content tampering, sequence gaps, broken previous hashes, duplicate semantic evidence,
non-UTC timestamps or validation/final-test feedback. The ledger stores evidence hashes and outcomes,
not credentials, raw market data or local paths.

## Recommendations

- empty memory: `EXPLORE`;
- fewer than three repeated failures: `MUTATE_OR_EXPLORE`;
- three or more identical family failures: `REPAIR`;
- eight or more: `STOP_FAMILY`.

Writing or replaying memory adds no inferential Trial; the recorded deltas must already originate from
V5.8 evidence stages.
