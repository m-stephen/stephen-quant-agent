# V2.1: Real-QD Alpha Discovery and Reliability Calibration

## Objective

V2.1 connects the auditable V2.0 loop to real QD data through a reproducible
`readiness → mechanism hypothesis → training screen → CPCV → cost backtest → Alpha Court → replay`
pipeline. A candidate remains a research signal until it survives statistical falsification.

## Frozen boundaries

- Data warm-up begins on 2021-07-01; evaluation is restricted to 2022-01-04–2024-12-31.
- The 2025 validation window and 2026 final-test window remain sealed.
- Reference NAV is CNY 3 million with explicit commission, tax, slippage, and impact.
- Thirteen distinct mechanisms allow only a 5/20-session window mutation: 26 preregistered candidates.
- Every screening, CPCV, and execution attempt enters the trial ledger; DSR and PBO account for multiplicity.

## Readiness gate

Research requires exact daily/fundamental matching, session and dynamic-universe coverage,
fund-flow/auction/margin/industry coverage, frozen snapshot hashes, and path-redacted artifacts.
Any failure stops the pipeline before empirical research.

## Modes

- `dry-run`: validate configuration and source presence without data or registry mutation.
- `readiness`: emit bilingual readiness reports and the dynamic universe.
- `research`: run the full cascade and emit a replay manifest.
- `replay`: verify artifact hashes offline without machine-local data paths.
- `kill`: stop before data or registry access.

Machine paths live only in Git-ignored `configs/qd-paths.local.json`; raw data, `reports/`, and
`artifacts/` are also ignored.

## Acceptance

Unit fixtures and the full suite pass; the real-data gate is READY; at least twelve mechanisms are
generated and fully counted; CPCV/placebo/DSR/PBO/cost/capacity gates run at frozen thresholds;
2025/2026 remain unopened; offline replay and registry audit pass.
