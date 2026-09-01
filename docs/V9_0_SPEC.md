# V9.0 calibrated, portfolio-native alpha discovery

## Objective

V9.0 closes the engineering gap between producing statistical factor scores and deciding whether a
factor can support a tradable portfolio. It is a discovery-system release, not an alpha claim.

## Frozen research protocol

- Time roles: 2015–2017 discovery, 2018 validation, 2019 frozen test, 2020–2021 confirmation,
  2022–2024 stress, and 2025 onward sealed.
- Search budget: 50 label-free frozen proposals. The historical multiplicity baseline is 533 Trials.
- Portfolio: CNY 3m initial NAV, prior-ADV Top300 universe, Top40 holdings, 10-name rank buffer,
  41 bps round-trip cost, doubled-cost stress and 5% participation capacity.
- Alpha Court: DSR >= 0.95, PBO <= 0.05, placebo p <= 0.05, plus economic, path, cost and capacity
  gates. Missing DSR/PBO evidence fails closed.

## Components

1. Search calibration uses synthetic planted alpha, null searches, an overfit curve, a deliberate
   leakage control, and purge/embargo overlap checks.
2. Structural proposal generation varies economic mechanisms, horizons and directions rather than
   relying on dense parameter sweeps.
3. Five-level lineage identifies semantic plans, mechanism families, expressions, parameters and
   portfolio policies; semantic duplicates and tombstoned failures remain visible.
4. Optional LLM proposals are accepted only as byte-hashed offline packets. They never bypass the
   grammar, Trial ledger or Alpha Court.
5. Portfolio-native evaluation attributes benchmark, gross signal return, turnover, costs, capacity,
   drawdown and calendar-year concentration.

## Reproduction

```powershell
stephen-quant --db artifacts/v9.0/registry.sqlite3 v9-alpha-plan `
  --output reports/v9.0-alpha-discovery

stephen-quant --db artifacts/v9.0/registry.sqlite3 v9-alpha-replay `
  --warehouse-root E:\QD\quant-warehouse-v84 `
  --daily-snapshot 9ba3320edf76036e5431c0360eed5bf54ca641936a3fa2f1ab12064019cfebd5 `
  --multisource-snapshot cc4d6ccb871887aa9d1561827e430e52fcd6c0e2fbc63ba617369580e5f07bcd `
  --output reports/v9.0-alpha-discovery
```

The first command reads no real labels and consumes no Trial. The second requires exact frozen
snapshot identities, reads only their manifest-bound Parquet partitions, records one frozen
candidate/policy Trial, and never queries 2025–2026 labels. The stable `analysis_sha256` excludes
registry-generated experiment and Trial IDs so an identical snapshot/config replay is comparable.
Machine-local paths, reports, registries and raw data remain ignored by Git.
