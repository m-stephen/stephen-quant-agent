# V2 M0: Compatible Contracts, Hierarchical IDs, Dual Ledgers and Replay

## Objective

M0 does not build a parallel research stack. It extends the existing V1 FactorSchema, safe DSL, fingerprints, Experiment Registry and Trial Ledger into replayable V2 contracts.

## Design

- A V2 contract embeds the complete V1 schema JSON and legacy fingerprint, enabling reversible migration with semantic verification.
- Hypothesis, expression structure, parameter variant and test stage receive separate deterministic IDs.
- A new append-only Search Ledger is added; the existing Trial table remains the Inferential Trial Ledger.
- A text-only proposal with no empirical feedback may be search-only. Any use of returns, labels, IC, backtests or validation feedback must link an inferential Trial.
- Replay manifests freeze code, dataset snapshots, V2 contracts, the reference library, configuration, seed, both ledger ID sets, and complete LLM/tool interactions.
- The V1.8.21 reference is explicitly `research_only=true` and `validated_alpha=false`.

## Safety boundary

The Search Ledger rejects UPDATE and DELETE. The Trial Ledger rejects DELETE while preserving the existing write-once result transition. Replay audits verify Experiment-to-Snapshot linkage, the snapshot SHA-256, Search entries and Inferential Trials. M0 does not access sealed windows or generate a new alpha claim.
