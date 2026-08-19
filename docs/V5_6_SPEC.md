# V5.6 — Typed Factor-expression DSL

## Objective

Prevent syntactically valid but semantically invalid formulas from reaching a backtest. V5.6
compiles V5.5-routed schemas into a typed, deterministic intermediate contract.

## Static checks

- every referenced field is bound to exactly one semantic-catalog entry;
- arithmetic observes units, with explicit dimensionless compatibility;
- time-series functions declare output units and preserve field availability provenance;
- mixed-frequency inputs fail closed;
- the automatic-search lookback is capped at 252 sessions;
- a route must be cryptographically bound to the exact schema fingerprint;
- canonical typed identity is independent of display name.

The existing AST whitelist continues to reject attributes, imports, arbitrary calls, keyword
arguments and non-finite or unbounded constants. V5.6 does not evaluate return labels and adds no
inferential trial.

## Acceptance

- all V5.5 semantic candidates receive an explicit accepted/rejected outcome;
- incompatible-unit and over-limit adversarial fixtures are rejected;
- output is deterministic and bilingual;
- the full repository regression and Ruff checks pass.
