# V2 M5: Budgeted Autonomous Research Loop (Shadow Mode)

## One command

```text
stephen-quant --db artifacts/v2-shadow.sqlite3 v2-shadow-validate --config configs/v2.0-m5-shadow.json --output reports/v2.0-shadow
```

The command uses a frozen synthetic engineering fixture. By default it requests no model, reads no external data and connects to no trading execution. `--dry-run` proposes and compiles without empirical feedback; `--kill-switch` stops before research-state mutation; `--replay-manifest` verifies a prior run package offline.

## Orchestration

Candidates pass through constrained proposal, typed compiler/PIT audit, novelty gate, cheap diagnostics, marginal value and future-validation decision. Failures enter the structured failure store and produce revision or STOP_FAMILY only through a closed epoch. Every proposal/decision enters Search Ledger; any numerical feedback first creates an Inferential Trial.

## Decision boundary

M5 permits only `REJECT`, `REVISE`, `STOP_FAMILY` and `PROMOTE_FOR_FUTURE_VALIDATION`. The last means worthy of future independent validation, not Alpha Court approval or live-trading authorization. Access to 2025 validation and 2026 final test must remain zero.

## Outputs

The command writes JSON, Chinese and English Markdown, a Replay Manifest and complete registry provenance. Generated outputs remain under git-ignored reports/artifacts paths.
