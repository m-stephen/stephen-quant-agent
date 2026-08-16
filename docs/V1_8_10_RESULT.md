# V1.8.10 — Frozen Composite CPCV Result

## Decision

**REJECT. Do not open the 2025 validation window. Keep 2026 sealed.**

The selected fold-local composite was stable across the ten reconstructed CPCV paths, but its
mean path RankIC did not reach the predeclared minimum effect size of 0.02.

## Lineage

- Research implementation: `ce757f18bd2cce6f12758b3277f192557425c8a3`.
- Indexed CPCV audit implementation: `55d24cf5f9650c3dd7a3a5dd86d0374e39cfb46a`.
- Completed Experiment: `exp_6d9099fbd7d14944`.
- Snapshot: `snap_e5d5045cf1ded749`.
- Source manifest SHA-256:
  `e5d5045cf1ded7494764da678ebd6027ac6e79defb90e4bfb5f481fe36502480`.
- CPCV manifest SHA-256:
  `b8c1741177d7a791654f576da9225013c6d6d393d6479afb9f12e14e33b7c308`.
- Adapter: `qd-daily-directory-1.3.0`, back-ratio adjustment.
- Panel: 20 instruments, 852 daily files, 17,040 rows.
- Loaded range: 2021-07-01 through 2025-01-02.

The 2025-01-02 bar is only the endpoint of the final 2024 next-open research label. The reserved
validation begins on 2025-01-03, so no validation observation was evaluated. No 2026 file was
loaded or hashed.

## Engineering attempt ledger

The first execution registered four Trials under `exp_6c0435f4a5d64cc7` and exposed quadratic
runtime in the original interval audit. It was interrupted before any metric was observed. All
four attempts remain recorded as `failed_engineering`; none was deleted or reused.

After replacing pairwise checks with equivalent indexed closed-interval queries and passing the
full test suite, the completed Experiment registered four new Trials. The local V1.8.10 ledger
therefore contains eight attempts: four transparent engineering failures and four completed
configuration evaluations. PBO compares the four distinct completed configurations, not repeated
copies of the same hypotheses.

## Completed configuration results

| Trial | Configuration | Mean path RankIC | Positive paths | Result |
|---:|---|---:|---:|---|
| 1 | `volume_control` | -0.002442 | 0/10 | Reject |
| 2 | `volume_trend_lowvol_equal` | 0.009200 | 10/10 | Below effect threshold |
| 3 | `volume_trend_lowvol_train_ic` | 0.010754 | 10/10 | Selected, below effect threshold |
| 4 | `all_five_train_ic` | 0.003633 | 6/10 | Reject |

The selected configuration learned non-negative weights inside each fold over volume surprise,
trend efficiency, and low Parkinson volatility.

## Gate evaluation

- CPCV hygiene: **PASS**.
- Positive paths: **PASS**, 10/10 versus minimum 8/10.
- PBO: **PASS**, 0.00 versus maximum 0.20.
- Mean path RankIC: **FAIL**, 0.010754 versus minimum 0.02.

PBO of zero means the selected configuration was not ranked in the lower half of the complementary
paths in the declared selection test. It does not rescue a signal whose absolute effect is below
the minimum threshold.

## Interpretation

Low-volatility and trend information improved the negative standalone volume signal and did so
consistently, but the economic effect remains weak. Adding all five factors reduced stability and
strength. The project should not spend the untouched 2025 validation window on this family.

Any next iteration must introduce a genuinely new, economically motivated feature family or a
materially different target using research data only. It must create a new Experiment and count
all variants. Lowering the 0.02 gate after observing this result is prohibited.
