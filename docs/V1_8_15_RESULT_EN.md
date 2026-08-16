# V1.8.15 Dynamic-Universe Fundamental CPCV Result

## Decision

**The signal gate rejected the family. Do not run execution falsification and keep 2025 and 2026 sealed.**

The strongest predeclared candidate was the fold-local positive-RankIC value/quality composite. Its
mean path RankIC was 0.012552 with 10/10 positive paths, below the frozen 0.02 threshold. Book-to-price
and earnings yield were consistently positive but also too weak. Profitability and net margin did not
provide positive standalone information.

## Frozen lineage

- Research implementation commit: `e6b4535a3455f8cdbdf81b1d3eb4fd9dd866d9ff`.
- Experiment: `exp_e3ffbc5af5eb4029`.
- Snapshot: `snap_c1c3651f8ea05595`.
- Combined daily/fundamental source snapshot:
  `c1c3651f8ea05595256648725d44e29e673143b0a542ba1a5dd5cfd0d21bd112`.
- Daily source snapshot: `376223e719076e8b6c706c227cec3e82b1ead9e30b7267ceaa0966ced318e819`.
- Fundamental source snapshot: `48478d9540b6f22231c58c96cbe702fdc07b05585572620b1a0a87a049d335aa`.
- Membership SHA-256: `29dd231b8bc6a56bb9e3fd140f331fa1676a96384416d740c3c8f2d7d65c4061`.
- Candidate manifest SHA-256: `567a08fd5db44d4e4b563a20e5b6c71cd55002e79e571e304724a15a30ab5b17`.
- CPCV semantic manifest SHA-256: `081e30aa56a459544c8efbf0fd65ad1100680149eb5e7c0e75b199cf3b38fb1f`.
- Six Trials were registered and completed.

## Coverage and hygiene

- Research window: 2022-01-04 through 2024-12-31; 2025/2026 partitions were not loaded or hashed.
- 726 membership sessions, 724 evaluable next-open labels, and 217,110 common observations.
- Valid factor rows: 217,776 for book-to-price/profitability and 217,800 for earnings yield/net margin.
- Common-sample failures: 90 for book-to-price/profitability and 66 for earnings yield/net margin.
- CPCV used 6 groups, 3 test groups per fold, 20 folds, 10 reconstructed paths, and a 5-day embargo.
- All 80 split-hygiene findings passed.

## Candidate results

| Trial | Candidate | Mean path RankIC | Positive paths | Decision |
|---:|---|---:|---:|---|
| 1 | `book_to_price_single` | 0.012548 | 10/10 | Below threshold |
| 2 | `earnings_yield_single` | 0.011477 | 10/10 | Below threshold |
| 3 | `profitability_single` | -0.000086 | 0/10 | Rejected |
| 4 | `net_margin_single` | -0.002331 | 0/10 | Rejected |
| 5 | `value_quality_equal` | 0.007856 | 10/10 | Below threshold |
| 6 | `value_quality_train_ic` | 0.012552 | 10/10 | Below threshold |

The learned candidate assigned most fold-local weight to book-to-price and earnings yield. Its tiny
improvement over book-to-price is insufficient to cross the predeclared gate.

## Gate evaluation

| Gate | Frozen threshold | Actual | Decision |
|---|---:|---:|---|
| CPCV hygiene | All pass | 80/80 | Pass |
| Mean path RankIC | At least 0.02 | 0.012552 | Fail |
| Positive paths | At least 8/10 | 10/10 | Pass |
| PBO | At most 0.20 | 0.00 | Pass but non-rescuing |

PBO measures relative selection stability; it cannot turn a sub-threshold absolute signal into an
accepted alpha. Under the sequential gate, cost-aware execution, placebo, DSR, 2025 validation, and
2026 final testing were not run.

## Frozen artifact hashes

| Artifact | SHA-256 |
|---|---|
| Result JSON | `1171054c47cd6b9250a01c633f2d5b354e3e6162f6530adf04cb704fdfce82be` |
| Generated English report | `a384a70905b6ad5871a33056f00f649e9be790c0690a34b31b2a8af0b52cdc13` |
| Generated Chinese report | `907282f3e04aa75fafd544f1588bc6fe01cf2865b2aecf4e01f6ee405ad1b66d` |
| CPCV manifest file | `4838a23efbb8b0c91c2ddc79959dbd5dd05dc9e1ee37e431128ee2ff7a45fdf5` |
| CPCV audit | `d20118a75bca660569bf27ed7d2d730438ef1d8d85f1f0e58100bffedbc601ed` |

## Constraint on follow-up research

The positive but weak value result may justify a new economic hypothesis, such as slower holding
periods or more precise filing-availability metadata. Changing the horizon, threshold, neutralizer,
or candidate direction after seeing this result is a new Experiment and must increment the Trial
ledger. It may not use 2025 or 2026 while being redesigned.
