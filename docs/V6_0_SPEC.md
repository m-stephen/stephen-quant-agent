# V6.0 — Portfolio-aware Factor Objective

## Objective

Select factors by their incremental contribution to a realistic portfolio, not by standalone
RankIC or Sharpe. A weaker but orthogonal factor may be more valuable than another strong duplicate.

## Joint objective and gates

The research-only objective combines marginal information ratio, net Sharpe, doubled-cost Sharpe and
positive CPCV path fraction, then subtracts turnover, drawdown and correlation penalties. Frozen
hard gates require:

- capacity of at least CNY 3 million;
- annual turnover no greater than 24 portfolio-equivalents;
- doubled-cost Sharpe at least -0.25;
- non-negative marginal IR;
- absolute pairwise rank correlation no greater than 0.70;
- at most five selected factors.

The dependence matrix must be complete and unique. Evidence from validation or final-test windows is
rejected. Greedy selection is deterministic, and selected positive objectives are normalized to
weights summing to one.

## Trial boundary

V6.0 does not run new estimates by itself; it consumes already registered research evidence and adds
zero inferential Trials. V5.8 remains responsible for evidence-trial accounting.
