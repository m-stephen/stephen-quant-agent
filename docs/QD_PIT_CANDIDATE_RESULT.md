# QD Phase 0-1 Prototype Result

Status: ready for local prototype review, not ready for data promotion.

## Implemented gates

- explicit 2022-2024 allowlist only and no directory enumeration;
- Research Plane rejects restricted-year manifests before data access;
- 2025/2026 maintenance requires complete explicit authorization;
- maintenance requests reject returns, labels, IC, Sharpe, backtests, factor
  performance, rankings, promotion feedback and distribution summaries;
- restricted-year access produces a Data Operations Ledger record;
- research-visible restricted control metadata contains no content/statistics;
- duplicate primary-key and provenance-break thresholds are zero;
- sealed 2025/2026 read/list/hash/enumeration thresholds are zero;
- absolute path leakage and inferential trial delta are zero;
- deterministic normalized report hash;
- A/B/C evidence by source, field and date interval;
- JSON, bilingual Markdown and Data/Search Ledger outputs.

## Evidence status

Only synthetic 2022-2024 fixtures are used by this prototype package. No real
audit result is asserted because an externally generated, isolated or explicit
2022-2024 snapshot and exclusion proof have not been supplied.

No real restricted-year maintenance is performed by this package. Phase 1B
requires an independent Issue, workspace, authorization and Data Operations
Ledger. This avoids PIT discontinuity without exposing restricted years to
research.

## Deferred work

Financial and industry dual-time models, `corporate_action_pit`, PIT market-cap
construction and AlphaPai retrieval are Phase 2-3 work and intentionally absent.

The requested decision is limited to whether Phase 0 + Phase 1A may proceed to a
separate branch and PR targeting `data-test`. It does not authorize sealed-data
access. Phase 1B authorization is separate and never permits research use.
