# V1.8.15 Point-in-Time Value and Quality Research

## Objective

Test whether simple value and quality signals add stable cross-sectional information after the
V1.8.14 microstructure family was rejected. This milestone starts with data readiness; it does not
authorize the 2025 validation window or the 2026 final test.

## Frozen data semantics

- Returns use back-ratio-adjusted open prices.
- Valuation ratios use raw close reconstructed as `adjusted_close / adjustment_factor`.
- Fundamental fields become available at 15:01 China time and may trade only at the next open.
- A changed field is promoted only after two consecutive identical daily snapshots. The prior
  confirmed value remains active during the transition.
- Twenty earlier sessions warm up the confirmation state.
- No vendor PE or PB field is used.
- Daily transforms are cross-sectional only; no full-window scaler or neutralizer may be fitted.

## Predeclared component family

1. Book-to-price: confirmed book value per share divided by raw close; require positive book value.
2. Earnings yield: confirmed EPS divided by raw close.
3. Profitability: confirmed EPS divided by confirmed book value; require positive book value.
4. Net margin: confirmed net profit margin.

Revenue and profit growth remain diagnostic fields only in this version because their observed
ranges are extreme. Every component will be winsorized cross-sectionally, industry-demeaned, and
residualized against log market capitalization using only that decision day's members.

## Candidate and evaluation constraints

- Singles: book-to-price, earnings yield, profitability, and net margin.
- Composite: one equal-rank value/quality candidate.
- Learned composite: one fold-local positive-RankIC weighting candidate with equal-weight fallback.
- Each candidate is a separate Trial in the multiplicity ledger.
- Research window: 2022-01-04 through 2024-12-31.
- CPCV: closed next-open labels, purge, embargo, and fold-local fitting.
- A signal gate pass only authorizes in-window execution falsification, costs, placebo, and DSR.
- 2025 and 2026 remain sealed until every earlier gate passes.

## Data-readiness result

- 746 source snapshots were frozen, including 20 warm-up sessions.
- Fundamental snapshot SHA-256:
  `48478d9540b6f22231c58c96cbe702fdc07b05585572620b1a0a87a049d335aa`.
- 726 research sessions and 217,800 requested dynamic-universe rows.
- 217,800 rows emitted; zero missing member rows and zero invalid numeric cells.
- All seven retained fields reached 100% confirmed coverage.
- The two-snapshot rule withheld 19,300 changing member-field observations, including 4,114 EPS
  and 3,733 book-value observations.
- Economic validity is not implied by completeness: EPS is nonpositive in 24,833 observations,
  book value in 24, and growth/margin fields contain extreme values. Explicit eligibility filters
  and cross-sectional robustification are therefore mandatory.

## Test targets

- Reject missing same-day partitions, duplicate instruments, date mismatches, invalid numbers, and
  nonpositive adjustment factors.
- Prove a one-session provisional value cannot replace the last confirmed value.
- Prove adjusted returns and raw valuation prices use distinct, reproducible price semantics.
- Prove neutralization uses the same decision date only.
- Verify frozen hashes, Trial counts, CPCV hygiene, bilingual artifacts, and sealed windows.

## Current checkpoint

**Data readiness passed. Signal testing has not run, so no alpha conclusion exists yet.**
