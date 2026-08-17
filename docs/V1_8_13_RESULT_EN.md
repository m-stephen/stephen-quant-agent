# V1.8.13 Dynamic-Universe Stateful Backtest Result

## Decision

**PASS_ENGINEERING / REJECT_ALPHA**

The frozen V1.8.11 dynamic membership, QD daily adapter, factor registry, V1.8.12
stateful execution, explicit costs, and CSI 300 comparison completed end to end. The
fixture `mom_120_skip_20@1.0.0` had already been rejected, and this run provides no new
alpha claim.

## Frozen scope and lineage

- Data history: 2021-07-01 through 2024-12-31.
- Research execution: 2022-01-05 through 2024-12-31, 725 sessions.
- Reserved validation: 2025; reserved final test: 2026. Neither window was loaded or hashed.
- Dynamic universe: 726 decision sessions, daily Top 300, 1,738 unique instruments.
- Experiment: `exp_494ec15dfd304a37`.
- Trial: `trial_29a1d15320a74e2d`, Trial 1.
- Snapshot: `snap_376223e719076e8b`.
- Membership SHA-256: `29dd231b8bc6a56bb9e3fd140f331fa1676a96384416d740c3c8f2d7d65c4061`.
- Selected QD source snapshot SHA-256:
  `376223e719076e8b6c706c227cec3e82b1ead9e30b7267ceaa0966ced318e819`.
- CSI 300 source SHA-256:
  `105c12d2deafa93642b3227e868f701628b89c3c55da8e08de8f5e8593398e96`.

The first registered attempt, `trial_4ba2399c8a7a44d8`, failed safely on a blank
point-in-time name field and recorded `failed_engineering`. Adapter version
`qd-daily-directory-1.3.1` retains such rows for history but blocks trading rather than
guessing missing metadata. The completed run is a separate registered trial.

## Backtest outcome

| Metric | Strategy | CSI 300 |
|---|---:|---:|
| Total return | -77.0047% | -19.8255% |
| Maximum drawdown | -80.2035% | -35.6298% |
| Final NAV from CNY 1,000,000 | CNY 229,953.09 | n/a |

Strategy excess total return was **-57.1792 percentage points**. Explicit commission,
sell tax, and slippage totaled CNY 40,830.58. This is a negative research result from an
already rejected fixture, not evidence that the pipeline or data should be optimized to
make this factor pass.

## Data and execution quality

- The adapter read 1,454,127 rows from 851 immutable daily files for 1,738 instruments.
- Schema drift, filename/date disagreement, duplicate instrument-date keys, invalid OHLC,
  non-positive adjustment factors, and missing required price fields are hard failures.
- 841 bars (0.0578%) lacked point-in-time name or previous-close metadata. They remained
  available to historical factor calculations but were prohibited from trading.
- 43,497 of 43,500 expected rebalance signals were available (99.9931%); three were
  explicitly counted as failures.
- Across 12,985 consecutive held-session mark comparisons, none moved more than 50%.
  The single move above 21% was a Beijing Stock Exchange instrument, consistent with its
  wider daily price band rather than an adjustment discontinuity.
- 51 of 4,111 actionable order intents were partly or fully blocked: 17 for missing
  point-in-time metadata, 10 for missing bars or suspension, 7 at the upper limit, 4 at
  the lower limit, and 13 by cash funding scale.
- Sparse accounting recorded 10 stale position-days, zero forced write-offs, and zero
  recoveries. A missing quote never silently deleted a holding.

## Frozen artifact hashes

| Artifact | SHA-256 |
|---|---|
| Dynamic backtest JSON | `0e57c431f28ecc84ed5a7da73809cf27657b784e5069ea5e350e82d6121a2b8e` |
| Dynamic targets JSONL | `17f33408b789a68cfb1fd382c4723dc4910bd765fcc046f54f759804d1f88a52` |
| Stateful execution JSON | `1c40ff7a59c69ed190a6f99c66afbc2ae138d179be714ee96d6ed5cc8bdc44eb` |
| QD data audit JSON | `1b834bd86a705477ce53946d93a757aca6e209d6e110c83167eeaaea406bf9fe` |

Generated reports and market data remain outside Git. The hashes and registered trial
ledger provide reproducibility without publishing private data or machine-local paths.

## Next gate

Keep 2025 and 2026 sealed. Predeclare a small candidate set, run CPCV and falsification inside
2022-2024, and advance only candidates that pass those tests to the untouched 2025 validation.
