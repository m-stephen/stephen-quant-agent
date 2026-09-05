# V11.3 Search Power Lab

V11.3 implements Issue #178 and separates search-engine diagnosis from reliable-Alpha
confirmation. It freezes a type-safe expression catalog, a synthetic planted/null audit,
one thousand unique real-label identities, a contaminated 2024 diagnostic holdout, and a
deterministic portfolio-native ranking contract.

The exact machine contract is `docs/V11_3_SPEC_LOCK.json`; its raw-byte SHA-256 is recorded in
every report. The synthetic audit is consumed once. Real 2022–2024 labels may be read only after
that audit passes. The 2024 window is then consumed once and can never be represented as an
independent holdout.

## Boundaries

- 2022–2023: `DEVELOPMENT_ONLY`.
- 2024: `CONTAMINATED_DIAGNOSTIC_HOLDOUT`, then `CONSUMED_FOR_DIAGNOSTIC`.
- 2025–2026 historical labels: sealed and never read.
- V11.2 candidates, clock and Nursery: unchanged.
- CNY 3m, Top40, ten-name buffer, 41/82 bps costs and 5% participation remain fixed.
- One epoch stops after at most 1,000 unique real-label candidate identities.
- No result from V11.3 is a validated Alpha or trading authorization.

## Funnel

```text
>=10,000 label-free canonical expressions
  -> 1,000 balanced complete candidate identities
  -> planted/null one-time audit
  -> 2022-2023 nested diagnostic search
  -> freeze inner ranking
  -> consume contaminated 2024 diagnostic once
  -> Search Power status and candidate clusters
  -> forced stop and manual review
```

DSR and PBO remain reported for configuration selection. A future completely fixed prospective
candidate may report PBO as `NOT_APPLICABLE` and must instead use its separately preregistered
primary statistic and alpha-spending contract. This does not change existing Alpha Court gates.
