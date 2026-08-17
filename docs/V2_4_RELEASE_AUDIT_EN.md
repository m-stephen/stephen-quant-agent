# V2.4 Research-Preview Release Audit

## Release classification

- Package version: 2.4.0
- Intended branch: `main`
- Classification: `research-preview`
- Live autonomous trading: disabled and unsupported
- Alpha claim: rejected
- Sealed data: 2025 validation and 2026 final test unopened

## Required evidence

- `data-test` has no divergence from `main` and is fast-forward compatible.
- Exact V2.3 execution replay passes.
- Point-in-time controls pass and forward returns are excluded from fitting.
- Trial ledger is 45 with exactly one V2.4 validation trial.
- Capacity clipping is zero.
- Generated JSON plus Chinese/English Markdown pass offline hash replay.
- Registry snapshot, experiment, and trial-counter audits pass.
- Full pytest, Ruff, compile, and GitHub Actions must pass before merge.
- Tracked content must contain no machine-local QD paths, raw data, credentials, registries, or
  generated reports.

## Interpretation

Passing this audit authorizes publication of research infrastructure and its negative/positive
evidence. It does not authorize live trading, threshold relaxation, opening sealed windows, or
describing the V2.3 signal as proven Alpha.
