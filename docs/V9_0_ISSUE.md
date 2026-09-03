# V9.0 — Close the gap from statistical factors to reliable alpha discovery

## Goal

Turn the current collection of search, validation and warehouse components into one reproducible,
portfolio-native discovery loop. The release may report `NO_RELIABLE_ALPHA`; it must never weaken
Alpha Court thresholds to manufacture a pass.

## Scope

1. Recover the V8.1 flow-price-divergence candidate as a versioned, replayable hypothesis.
2. Add search-power calibration: planted-alpha recovery, null false-positive control,
   deliberate-overfit curve, leakage positive control and temporal-CV sanity checks.
3. Make candidate promotion portfolio-native: fixed CNY 3m NAV, Top40, 10-name buffer,
   explicit standard/double costs, capacity and market-relative excess return.
4. Expand the label-free mechanism grammar by structure rather than parameter sweeps:
   cross-sectional transforms, change/surprise, interactions, decay, event/regime context and
   multiple predeclared horizons.
5. Add stable lineage levels (`SemanticPlan -> MechanismFamily -> ExpressionVariant ->
   ParameterVariant -> PolicyVariant`), semantic deduplication, failure tombstones and a frozen
   empirical budget. LLM packets remain optional, cached and offline-replayable.
6. Report conversion attribution for signal, long leg, benchmark, turnover, costs, capacity,
   drawdown and time/regime concentration.
7. Execute one controlled historical campaign: 2015–2017 discovery, 2018 validation, 2019 frozen
   test, 2020–2021 confirmation, 2022–2024 stress. Keep 2025–2026 sealed for tuning.
8. Produce deterministic JSON plus bilingual Markdown reports and carry all prior Trials into DSR.

## Acceptance criteria

- Calibration fails closed unless planted signals are recovered and null/leakage controls behave as
  expected.
- No candidate reaches Court through RankIC alone; portfolio evidence is mandatory.
- Every empirical candidate/policy increments the Trial ledger exactly once.
- Re-running the same frozen config and snapshot reproduces candidate identities and report hashes.
- Standard and doubled-cost, placebo, purged CPCV/PBO, DSR and path gates remain unchanged.
- Unit tests and Ruff pass; real-data outcome is reported honestly as `PASS` or
  `NO_RELIABLE_ALPHA`.
- Changes land through a `codex/` branch and reviewed PR, then become the latest `main` only after
  CI succeeds.

## Explicit non-goals

- Do not wait for full minute materialization to continue daily-factor research.
- Do not claim that missing historical industry membership or corporate actions prevents all factor
  discovery; disclose the neutralization/deployment limitation instead.
- Do not search, tune or replace candidates using 2025–2026 labels.
