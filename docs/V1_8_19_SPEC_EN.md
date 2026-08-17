# V1.8.19: CNY 3m Reference and CNY 20m Capacity Ceiling

Tracking issue: [#31](https://github.com/m-stephen/stephen-quant-agent/issues/31)

## Objective

Answer the question left open by V1.8.18: with approximately CNY 3 million currently deployed and a hard ceiling of CNY 20 million, how do execution capacity and costs affect the existing 20-day flow-divergence research pipeline?

## Frozen design

- Use only 2022–2024 research data; keep the 2025 validation and 2026 final-test windows sealed.
- Fix NAV levels at CNY 1m, 3m, 5m, 10m, and 20m.
- Test 1%, 5%, and 10% maximum ADV participation at each NAV, for 15 combinations.
- Use CNY 3m as the same-participation degradation reference. CNY 20m is a hard ceiling; do not extrapolate beyond it.
- Reuse the V1.8.18 candidate family and Alpha Court gates. Add no candidates and do not tune against sealed windows.
- Register all 15 capacity Trials before execution and DSR computation.

## Outputs

For every combination, report net return, Sharpe, maximum drawdown, cost/NAV, capacity-clipped trade ratio, eligible observations, executed orders, and return/Sharpe changes relative to the CNY 3m result at the same participation rate.

Engineering acceptance means the capacity frontier is reproducible and auditable. It does not mean the factor passed the Alpha Court or is approved for live trading.

