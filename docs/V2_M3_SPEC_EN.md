# V2 M3: Marginal Alpha Engine

## Objective

Candidates are no longer ranked by standalone IC alone. They are evaluated for incremental information and tradable value relative to a versioned reference portfolio. V1.8.21 remains a `research_only` reference, not a validated alpha library.

## Method

- Each fold fits `candidate ~ reference` on train rows only and applies the residual model to that fold's test rows.
- Reports standalone IC/RankIC, residual IC/RankIC and redundancy correlation.
- Compares long-only and long-short portfolios built from the reference score versus reference plus residual blend.
- Explicitly measures net return, Sharpe, maximum drawdown, turnover, tail return and capacity.
- Marginal utility penalizes incremental turnover, complexity and data cost.

## Acceptance

A frozen fixture must consistently rank a lower-standalone-IC but orthogonal candidate above a higher-IC redundant candidate. Changing test rows cannot alter fold-local fitted coefficients, and identical frozen inputs must produce identical scorecards.
