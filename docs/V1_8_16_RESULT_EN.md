# V1.8.16 Frozen Research Result — English

## Conclusion

The automated factor-generation and backtest workflow is operational and reproducible,
but **none of the three horizon winners is authorized for portfolio or PPO use**. All
three were rejected by the pre-registered Alpha Court and their portfolio gate files
contain `authorized: false`.

This is a successful engineering result, not a positive Alpha claim. The system generated
and measured 54 structured candidates across three independent Experiments, consumed the
exact frozen suite budget of 78 Trials, produced research memory and Alpha Cards, and kept
the 2025 validation and 2026 final-test windows closed.

## Frozen lineage

- Research data end: `2024-12-31`
- Composite source snapshot:
  `eb6b8b61030a338f417f79f969d7ebecd60bb3b3ff1103a57b718aabf25e3ccd`
- Suite Trial budget / consumed: `78 / 78`
- Candidates: `18 × 3 horizons = 54`
- CPCV shortlist: `6 per horizon`
- Validation window opened: `false`
- Final-test window opened: `false`
- Local verification: `166 passed`; Ruff passed
- GitHub Actions CI: passed on commit `1e7af92`

## Results

| Horizon | CPCV winner | Mean path RankIC | Positive paths | PBO | Execution winner | Net return | Net Sharpe | DSR | Walk-forward return | WF Sharpe | Gate |
|---|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---|
| next-open | `price_reversal_60_next_open` | 0.038626 | 10/10 | 0.000000 | `price_reversal_60_next_open` | -16.20% | 0.0157 | 0.016410 | -40.32% | -0.4617 | REJECT |
| 5-day | `price_reversal_60_5d` | 0.084285 | 10/10 | 0.000000 | `price_reversal_60_5d` | +20.09% | 0.3461 | 0.370456 | +8.38% | 0.2651 | REJECT |
| 20-day | `price_reversal_60_20d` | 0.120787 | 10/10 | 0.000000 | `price_reversal_20_20d` | +8.59% | 0.2503 | 0.419267 | -18.43% | -0.1165 | REJECT |

Both placebo p-values were `0.005` for every execution winner. That evidence was not
sufficient to override DSR or walk-forward failures. DSR used the cumulative global Trial
count at each horizon: 26, 52, and 78.

## Interpretation

- The 5-day reversal family is the best current research lead: positive CPCV, positive
  cost-adjusted execution, and positive walk-forward performance. It still fails the 0.95
  DSR threshold after multiplicity correction.
- The next-open candidate is economically unusable after costs and walk-forward replay.
- The 20-day CPCV signal is strong in-sample across paths, but execution selects a different
  window and walk-forward is negative. This is exactly the instability the final gate is
  designed to catch.
- No validation/test evidence was used to choose a family, direction, window, or horizon.

## Delivered artifacts

Each horizon produces JSON and bilingual Markdown reports, generated schemas, execution
replays, Alpha Court evidence, research memory, an Alpha Card, and a portfolio authorization
or rejection file. Machine-specific reports, registries, caches, paths, and vendor data stay
outside Git.

The next campaign should use the research-memory recommendations under a newly frozen budget,
with special attention to 5-day reversal variants and genuinely new data families. Thresholds
must not be relaxed and sealed windows must remain closed.
