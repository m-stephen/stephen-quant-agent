# V1.8.3 - Reproducible QMT DAT Backtest Validation

V1.8.3 lives on the long-running `data-test` branch. It demonstrates that local Guojin QMT daily
DAT files can pass through the complete integrity and backtest stack without placing experimental
data code on `main`.

## One-command contract

`qmt-dat-validate` performs:

```text
explicit DAT universe and data window
  -> read-only 64-byte record parsing
  -> canonical unadjusted CSV and raw-source hash manifest
  -> exact CSV snapshot registration
  -> Experiment and Trial registration
  -> point-in-time factor observations
  -> next-open, net-of-cost Momentum Top-K backtest
  -> JSON/Markdown validation summaries
  -> summary artifact registration
```

The operator must predeclare the data, training, validation, and test windows. Repeated attempts
should reuse `--experiment-id` so the Trial ledger records multiplicity. Existing validation output
is refused unless `--overwrite` is explicit.

## Dual verdict

The summary separates two questions:

1. **Engineering validation:** did binary parsing, provenance, snapshotting, Trial-first execution,
   timing, cost accounting, and artifact registration all complete?
2. **Research-claim eligibility:** is the result sufficiently free of adjustment and universe bias
   to support an Alpha claim?

For direct DAT input in V1.8.3, a successful run returns:

```text
engineering_validated = true
research_claim_eligible = false
```

The research verdict is forced to false because prices are unadjusted, corporate actions are not
reconstructed, and universe membership is operator-supplied rather than point-in-time. A universe
smaller than 30 instruments is additionally flagged as a pilot-only sample. These limitations do
not invalidate an engineering test, but they prohibit interpreting its Sharpe or return as verified
Alpha.

## Outputs

The chosen output directory contains:

```text
data/qmt-daily-none.csv
data/qmt-daily-none.csv.manifest.json
trials/<trial-id>/qmt-data-audit.json
trials/<trial-id>/baseline-report.json
trials/<trial-id>/baseline-report.md
validation-summary.json
validation-summary.md
```

Raw data, manifests, registries, and reports remain ignored by Git. The durable summary omits the
local QMT installation path while retaining source, schema, CSV, report, and artifact hashes.

## Acceptance target

- Synthetic DAT input completes the full CLI workflow.
- The provenance manifest is verified and attached to the Trial.
- Validation summaries are deterministic and attached to the Trial.
- Reusing a populated output directory without `--overwrite` fails closed.
- Full tests and lint pass.
- A local Guojin pilot completes without committing raw data or private paths.
