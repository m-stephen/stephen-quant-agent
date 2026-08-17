# V1.8.14 Dynamic-Universe CPCV Signal-Gate Result

## Decision

**REJECT_SIGNAL_GATE. Do not run execution falsification. Keep 2025 and 2026 sealed.**

All four predeclared microstructure candidates produced negative mean OOS-path RankIC and zero
positive reconstructed paths. The strongest candidate, `gap_reversal_single`, scored -0.017115
against the frozen +0.02 minimum. The family therefore stops at the signal gate.

## Frozen lineage

- Research implementation commit: `5a8de9b6beb127e56a551ee2267974888cedcb89`.
- Experiment: `exp_02043f147da34a20`.
- Snapshot: `snap_376223e719076e8b`.
- Source snapshot SHA-256:
  `376223e719076e8b6c706c227cec3e82b1ead9e30b7267ceaa0966ced318e819`.
- Membership SHA-256:
  `29dd231b8bc6a56bb9e3fd140f331fa1676a96384416d740c3c8f2d7d65c4061`.
- Candidate manifest SHA-256:
  `b11a97334b3eee5500b83c9a6178990c198287c5fc7f49d3e586c833ba115b3c`.
- CPCV semantic manifest SHA-256:
  `94b7a6b420c3a34c10bcf07a2fc6bb3fe593255027dc927534ad5699da7df8ce`.
- Registered Trials: four; completed research measurements: four.

## Data and split coverage

- Loaded history: 2021-07-01 through 2024-12-31 only.
- Research memberships: 726 sessions; evaluated next-open labels: 724 dates.
- Common cross-sectional observations: 217,134 of 217,200 expected (99.9696%).
- Explicit component failures: 66 for each factor, caused by unavailable sparse labels or bars.
- Source data: 1,454,127 rows, 851 daily files, 1,738 dynamic instruments.
- CPCV: six groups, three test groups, 20 folds, ten reconstructed paths, five-day embargo.
- Audit: 80 of 80 findings passed across disjointness, closed-label purge, embargo, and recorded
  temporal boundaries.
- No 2025 or 2026 market partition was loaded or hashed.

## Candidate results

| Trial | Candidate | Mean path RankIC | Positive paths | Decision |
|---:|---|---:|---:|---|
| 1 | `gap_reversal_single` | -0.017115 | 0/10 | Reject |
| 2 | `close_location_single` | -0.023265 | 0/10 | Reject |
| 3 | `gap_close_equal` | -0.026700 | 0/10 | Reject |
| 4 | `gap_close_train_ic` | -0.026700 | 0/10 | Reject |

Both training component RankICs were non-positive in every fold, so the predeclared fold-local
rule fell back to equal weights. This is why the trained and equal-weight combinations match.

Fixed configurations have identical scores across the ten reconstructed paths because every path
covers the same full OOS date set and their formulas do not vary by fold. This is expected CPCV
path reconstruction behavior. The fold-learned candidate would differ only if its training
weights differed across folds.

## Gate evaluation

| Gate | Frozen threshold | Observed | Result |
|---|---:|---:|---|
| CPCV hygiene | all checks pass | 80/80 | Pass |
| Mean path RankIC | at least 0.02 | -0.017115 | Fail |
| Positive paths | at least 8/10 | 0/10 | Fail |
| PBO | at most 0.20 | 0.00 | Pass, non-rescuing |

PBO is zero because the relative ordering is stable; it does not imply useful alpha when every
candidate has negative absolute RankIC. Under the predeclared sequential gate, DSR, cost-aware
execution, and placebo tests were not run after the signal failure.

## Artifact hashes

| Artifact | SHA-256 |
|---|---|
| Result JSON | `16183d0aa141ecb6ab4d249aea2b835c0108f32dd14bd1ea840a883f4508d71a` |
| English report | `8658e38793bc9173966397672842aeecb4503556582ed978ee3b5b0013a30927` |
| Chinese report | `e75c5888b9679b65361798ea494e90cda56885016ce422696c377cab81d9b7b5` |
| CPCV manifest file | `2f8bcf5fa140d4ab6a736242e29ed9d87a92e72e3e84b006ea19ff775a0bfdc7` |
| CPCV audit | `d20118a75bca660569bf27ed7d2d730438ef1d8d85f1f0e58100bffedbc601ed` |
| QD data audit | `1b834bd86a705477ce53946d93a757aca6e209d6e110c83167eeaaea406bf9fe` |

## Interpretation and constraint

The declared contrarian gap direction and positive close-location direction are unsupported in
this research interval. Simply flipping either sign after seeing this result is prohibited. A
reversed or redesigned hypothesis requires a new version, new economic rationale, new Experiment,
and additional counted Trials; it still may not use 2025 or 2026 during research.
