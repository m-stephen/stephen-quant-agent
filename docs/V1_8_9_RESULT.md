# V1.8.9 — Frozen Validation Result

## Decision

**REJECT. Keep the 2026 test window sealed.**

The strongest member of the predeclared five-factor family was
`volume_surprise_5_20@1.0.0`, but it failed the placebo requirement and its family-adjusted DSR
probability was below the frozen 0.95 threshold.

## Lineage

- Validation implementation commit: `d570e6cb53b0bd191d2cac0d94202582619e5428`.
- Experiment: `exp_912edcc3f8b642f9`.
- Snapshot: `snap_ee27eef1d50fdcb2`.
- Source manifest SHA-256:
  `ee27eef1d50fdcb2ed207dbcabbe3fad291c614e6d8250096605127a1e1d5ca8`.
- Adapter: `qd-daily-directory-1.3.0`, back-ratio adjustment.
- Recorded Trials: 5; accepted executions: 5.
- Evaluation sessions: 242.
- Data audit range: 2022-01-04 through 2025-01-02. The final date is the next-session
  execution bar after the declared 2024 validation window; no 2026 file was loaded or hashed.

Machine-specific source paths, raw market data, the registry database, and generated reports stay
outside git.

## Trial results

| Trial | Factor | Net return | Net Sharpe | CSI 300 excess | Signal placebo p | Return placebo p | Placebo |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | `mom_120_skip_20@1.0.0` | 0.19% | 0.188 | -14.57% | 0.385 | 0.415 | Fail |
| 2 | `trend_efficiency_20@1.0.0` | 10.28% | 0.445 | -4.47% | 0.500 | 0.470 | Fail |
| 3 | `range_position_20@1.0.0` | -1.13% | 0.143 | -15.88% | 0.175 | 0.125 | Fail |
| 4 | `volume_surprise_5_20@1.0.0` | 26.74% | 0.827 | 11.99% | 0.465 | 0.510 | Fail |
| 5 | `parkinson_vol_20@1.0.0` | -0.74% | 0.205 | -15.49% | 0.040 | 0.020 | Pass |

The selected Trial was `trial_4345ab734cbe421b`. Its maximum drawdown was -26.21%.

## Multiplicity-aware result

- Method: Bailey and Lopez de Prado DSR implementation already present in V1.4.
- Recorded trial count: 5.
- Observations: 242.
- DSR probability: **0.689683**.
- Frozen pass threshold: 0.95.

The selected factor passed the raw return and CSI 300 excess-return conditions, but failed both
placebo tests and DSR. `parkinson_vol_20` passed placebo but lost money and underperformed the
benchmark. No family member therefore satisfies the complete acceptance rule.

## Interpretation and next constraint

The result is useful negative evidence: high 2024 return alone is insufficient. The weak placebo
result indicates that the selected factor's portfolio path is not distinguishable from the
declared randomized alternatives under this test design. The next research iteration may improve
the hypothesis or combine factors using training/CPCV only, but it must create a new Experiment
and count every new variant as another Trial. It must not tune against this validation window or
open the reserved 2026 test window.
