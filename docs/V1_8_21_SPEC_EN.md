# V1.8.21 Preregistered Portfolio Usage Slice

## Objective

V1.8.20 found residual information in flow-price divergence, but most value came from avoiding the bottom decile and the simple Top-K long portfolio failed Alpha Court. V1.8.21 stops formula search and compares a bounded set of signal-to-portfolio mappings on consumed 2022–2024 research data.

## Frozen mappings

- equal-weight all-eligible benchmark;
- top decile;
- top 30 percent;
- exclude the bottom decile;
- hold the bottom decile at 25 percent of the ordinary relative weight;
- residualize against preregistered controls, then exclude the bottom decile.

Every mapping is evaluated at CNY 1m, 3m, 5m, 10m and 20m and registered as an inferential trial. The all-eligible equal-weight portfolio supplies incremental return, Sharpe and drawdown comparisons. The reference is fixed before measurement as exclude-bottom-decile at CNY 3m; it is not selected from the results.

## Integrity boundary

- 2022–2024 is consumed research data and every result is `research_only`;
- 2025/2026 is not read, listed or hashed;
- mappings, thresholds, costs, capacity and NAVs are frozen before measurement;
- every mapping/NAV pair is an Inferential Trial;
- the existing self-financing cost, tax, slippage, square-root impact, capacity and tradability model is reused.

## Acceptance

The same manifest must reproduce identical metrics, every trial must remain traceable, and complete Chinese and English reports must be emitted. A versioned reference portfolio is produced regardless of performance, but it is never described as fresh out-of-sample alpha evidence.
