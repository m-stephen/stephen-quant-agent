# V5.5 — Field Semantics and Research-form Routing

## Objective

Create the semantic control plane required by automatic factor discovery. Candidate expressions
must understand what a field means before they are allowed to consume statistical trial budget.

## Contract

Every declared source field records its value type, unit, frequency, point-in-time availability,
sparsity, missing-value meaning, economic role and allowed research forms. The router supports:

- continuous cross-sectional ranking;
- sparse event studies;
- portfolio eligibility filters;
- market-regime switches.

Schema identity is based on computation and research use, not its display name. Renaming a failed
hypothesis therefore cannot evade the research-memory ledger. Missing observations are never
silently converted to zero unless the field contract explicitly declares a structural zero.

## Integrity boundary

V5.5 reads schema metadata only. It does not read future returns, tune a factor, alter the frozen
V4.7 candidate, or increment the inferential trial ledger. V5.6 may consume only candidates that
pass this semantic router.

## Acceptance gates

- exact coverage of every field in `SOURCE_FIELDS`;
- deterministic output and semantic deduplication;
- auction and limit-up inputs route to event studies;
- margin inputs support both ranking and filtering;
- explicit missing-versus-zero semantics;
- invalid research-form overrides fail closed;
- Chinese and English machine-readable reports.
