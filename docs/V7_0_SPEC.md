# V7.0 — Automatic Alpha Discovery

## Objective

Turn the V5.5–V6.3 components into one reproducible command that generates typed factors, records
every empirical attempt, tests a bounded research batch and reports truthfully whether a deployable
Alpha exists.

## Frozen reference protocol

- Research labels: 2022-01-01 through 2024-12-31 only.
- Validation: 2025, sealed.
- Final test: 2026, sealed.
- Universe: point-in-time dynamic membership, up to 300 stocks per decision date.
- Horizon: five sessions.
- Grammar batch: eight automatically selected formula identities, both directions for each, for 16
  registered schema trials.
- Training gate: coverage at least 0.80, mean RankIC at least 0.005, positive years at least 2/3,
  turnover at most 0.80 and peer correlation at most 0.70.
- CPCV: six groups, three test groups, five-day embargo, eight-candidate maximum.

The generator derives safe symbolic formulas from the field semantic catalog. It adds return,
volatility, trend, level and compatible-unit ratio operators, compiles through the typed DSL and
enforces direction completeness. LLM packets remain optional, untrusted JSON and are not used by
the reference run.

## Integrity boundary

The command enumerates local-source coverage without writing absolute paths into reports. Research
files and dynamic membership are frozen by SHA-256 before trials start. Validation and final-test
labels are not loaded. `PASS_SIGNAL_GATE` is only an intermediate research status; deployment also
requires execution, transaction costs, capacity, placebo, DSR, Alpha Court and forward evidence.

For fixed formulas, combinatorial paths may traverse the same complete group set and therefore have
identical averages. V7.0 detects this degenerate path matrix and fails closed because its PBO and
positive-path counts do not contain independent falsification evidence.
