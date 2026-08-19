# V5.8 — Staged Candidate Screening Funnel

## Objective

Prevent automatic proposal generation from turning directly into an expensive multiple-testing
campaign. Each downstream stage has a smaller frozen budget and stronger evidence requirements.

## Frozen stages

| Stage | Default budget | Label use | Trial treatment |
|---|---:|---|---|
| typed proposal | 256 | none | zero |
| data quality | 192 | none | zero |
| training screen | 96 | research labels | one per evaluated candidate |
| purged CPCV/PBO | 16 | research labels | cumulative second trial |
| execution/cost | 4 | research labels | cumulative third trial |

The label-free gate checks coverage, missingness, signal variance and rank-turnover proxy. Later gates
check training RankIC and year stability, CPCV path stability and PBO, then standard and doubled-cost
Sharpe. Evidence identities must match the frozen V5.7 proposal set exactly.

Missing downstream evidence produces an explicit waiting state, never an implicit pass. Budgeted-out
candidates retain the trials already consumed. No validation or final test window is opened here.

## Acceptance

- non-increasing budgets fail closed if misconfigured;
- label-free failures consume zero trials;
- every label-dependent stage accounts for cumulative multiplicity;
- duplicate semantic identities and forged evidence bindings are rejected;
- deterministic plan/result output and full regression pass.
