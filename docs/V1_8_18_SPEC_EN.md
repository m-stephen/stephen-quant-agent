# V1.8.18: 20-day Flow-divergence Stability and Capacity Stress

Tracking issue: [#29](https://github.com/m-stephen/stephen-quant-agent/issues/29)

## Frozen hypothesis

V1.8.17's 20-day walk-forward selector repeatedly favored `flow_price_divergence_60`. V1.8.18 tests incremental information, state stability, and capacity sensitivity within that family without weakening any Alpha Court gate.

## Search space

- Horizon: 20 days only.
- Candidates: eight preregistered parent, 5/60 and 20/60 flow surprises, large and extra-large order surprises, a flow-persistence × price-reversal interaction, and two controls.
- CPCV limit: six; cost-execution limit: three; participation stress Trials: 1%, 5%, and 10%.
- Research ends on 2024-12-31. The 2025 validation and 2026 final-test windows remain sealed.

## State and capacity diagnostics

- Market regimes use equal-weight market return and volatility over the 20 sessions before execution.
- High/low volatility thresholds use only rolling volatility visible at that decision time.
- Capacity slices use decision-time ADV and split each daily cross-section into low, middle, and high terciles.
- Participation stress keeps commission, tax, slippage, and impact assumptions unchanged.
- Every stress configuration is registered before DSR is computed, preventing post-hoc stress tests from escaping the multiplicity ledger.

## Industry-neutral constraint

The available Shenwan files are industry indices rather than historical stock membership. The Tonghuashun concept archive starts mainly in 2025. The system accepts only PIT stock-industry mappings carrying `effective_at` and `available_at`, and requires exactly one visible industry per stock at decision time. Otherwise it fails closed. No fabricated industry-neutral backtest is run.

## One-command run

```powershell
stephen-quant --db artifacts/qd-v1.8.18.sqlite3 qd-auto-discover `
  --paths-config configs/qd-paths.local.json `
  --manifest configs/v1.8.18-flow-stress.json `
  --ingested-at 2026-08-17T00:00:00+08:00 `
  --output reports/qd-v1.8.18-flow-stress
```

Engineering acceptance is not Alpha acceptance. CPCV, costs, placebo tests, PBO, global-Trial DSR, and walk-forward jointly determine the final decision.
