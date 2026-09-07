# V11.9 Continuous Capital and Calendar Challenge

Question: do the frozen leads survive continuous capital and predeclared rebalance timing?
Issue184 preregistration comment5559351596 controls this bounded epoch. Formulas remain frozen.

## Protocol

Use the same immutable snapshot and exposed2023–2024 development data. Never read2025/2026.
Two leads plus four coverage-matched low-vol/hash controls, CNY3m once,20-session cycle,
Top40 and10-rank buffer. Test phases0/5/10/15, a fixed equal four-cohort target mixture,
and annually restarted target-selection calendars in an otherwise continuous account.
These are four selected-in-advance phases, not exhaustive20-phase coverage.

The mixture is ONE netted account, not average realized NAV: each cohort owns25% desired
weights, unstarted cohorts stay cash, and each cohort refresh rebalances the entire aggregate
target (including other cohorts' realized drift). It is not four segregated funds.
Test41/82bps costs through the actual existing execution model. Register72 policies before
market reads, even conservatively charging exact baseline replays. Debt3184→3256; failed
reservations remain charged and an exclusive predecessor claim prevents duplicate research.

## Interpretation

The prespecified staggered policy must meet doubled-cost positive returns in both years,
continuous Sharpe>=0.7, full-account drawdown>=-25%, total incremental return over matched
low-vol>=3pp, annual increments>=-5pp, and beat hash. At least3/4 single phases must have
positive increment and the worst must be>=-5pp. Never promote the best observed phase.

Decompose the annual-reset linked return minus continuous phase0 return into an account-reset
difference and a calendar difference, using the continuous annual-calendar run as intermediary.
This is an order-dependent descriptive difference, not an identified causal decomposition.
Aggregate annual returns from continuous daily returns; never reset actual capital for this cut.

Report the complete12-candidate/calendar family at doubled costs with20-session purge,
5-day embargo CPCV, PBO, family placebo and raw-count DSR sensitivity. Historical exposure,
local-family dispersion and missing full historical selection evidence prevent certification.
All existing Court thresholds stay unchanged. Adjusted fractional shares, linear fees and
ADV capacity remain research approximations, not raw-share/lots/min-fee/opening-fill evidence.

## Acceptance and reproduction

Copy the relative-path example into gitignored local config and run
`PYTHONPATH=src python -m stephen_quant.workflows.v119_calendar_epoch --config configs/calendar-challenge.local.json`.
Synthetic leakage/calendar/netting/ledger tests precede source-code freezing and the real run.
Independent72-account reconciliation, complete bilingual results and an isolated reviewable PR
are required. Failed epochs remain recorded. No automatic main merge or live trading.
