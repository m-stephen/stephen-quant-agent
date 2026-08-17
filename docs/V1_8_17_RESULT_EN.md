# V1.8.17 Frozen Result: Engineering Pass, Alpha Rejected

## Decision

Issue #27's engineering objective is complete. The system automatically generates and backtests normalized multi-source factors, applies family budgets plus yearly-stability and rank-turnover screening, and produces auditable results for three horizons. All horizons passed the CPCV signal gate, but none passed the complete Alpha Court. No portfolio or live-trading authorization is granted.

- Engineering decision: **PASS**
- Alpha decision: **REJECT_ALPHA_COURT**
- Data snapshot: `eb6b8b61030a338f417f79f969d7ebecd60bb3b3ff1103a57b718aabf25e3ccd`
- Successful suite consumption: 125 / 132 frozen Trials
- Final global Trial count: 242
- Validation window opened: no
- Final-test window opened: no

The global ledger started with the 78 V1.8.16 Trials. The first engineering run failed because the leading warm-up period had no eligible cross-section. The rerun followed a tested fix, while the failed attempts remained in the ledger. Official DSR therefore includes the multiplicity cost of this development iteration.

## Three-horizon results

| Horizon | Candidates | CPCV shortlist | Formal selection | Net return | Walk-forward return | DSR | PBO | Decision |
|---|---:|---:|---|---:|---:|---:|---:|---|
| next-open | 33 | 5 | `price_reversal_60` | -16.20% | -28.59% | 0.087964 | 0.000000 | Reject |
| 5-day | 33 | 6 | `price_reversal_60` | +20.09% | +17.47% | 0.614181 | 0.000000 | Reject |
| 20-day | 33 | 6 | `price_reversal_20` | +8.59% | +41.51% | 0.287329 | 0.000000 | Reject |

Signal-shuffle and return-permutation placebo p-values are 0.005 for all horizons. This supports a non-random in-sample relation but does not supersede DSR, cost, or stability gates. The frozen DSR requirement remains 0.95.

## Evidence from the new factors

- `large_flow_intensity_60` entered real cost backtests at next-open and 5-day horizons, demonstrating that flow/ADV hypotheses traverse the complete generation, screening, and CPCV pipeline.
- The final 5-day walk-forward deployment block switched from price reversal to `large_flow_intensity_60`.
- All five 20-day deployment blocks selected `flow_price_divergence_60`. Its training RankIC declined from 0.247656 to 0.129490 but remained positive.
- At 20 days, `flow_price_divergence_60` achieved training RankIC 0.130074, 100% positive-year stability, rank turnover 0.0384, and +3.32% in its standalone cost backtest.

The new sources improved research usefulness and walk-forward selection, but do not yet establish deployable Alpha.

## Comparison with V1.8.16

- Next-open walk-forward improved from about -40.32% to -28.59%, still unusable.
- 5-day walk-forward improved from about +8.38% to +17.47%.
- 20-day walk-forward improved from about -18.43% to +41.51%, driven by flow-price divergence.
- 5-day DSR rose from about 0.370 to 0.614. The 20-day DSR fell from about 0.419 to 0.287 because the global Trial penalty is stricter and the formal selection remains price reversal.

## Acceptance and limitations

- Ruff: passed.
- pytest: 173 tests passed at the final commit.
- Future-available or stale multi-source inputs: fail closed.
- Cross-fold winsorization and standardization: fitted on training IDs only.
- Machine paths, raw data, SQLite databases, and report directories: Git-ignored.
- Existing industry-index files do not provide historical stock-industry membership. The real run therefore uses market centering and does not fabricate industry-neutral results.

## Next step

Do not lower DSR. Treat the 20-day `flow_price_divergence_60` as a parent for a newly preregistered family: point-in-time industry-neutral variants, flow surprise, capacity buckets, and market-regime stability. Keep 2025/2026 sealed until that independent protocol is frozen.
