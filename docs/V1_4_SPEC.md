# V1.4 — Alpha Court

V1.4 does not search for better backtests. It tries to reject candidate alpha before promotion.

## Evidence contract

1. Signal shuffle permutes factor values within each timestamp and preserves the cross-section.
2. Return permutation permutes forward returns within each timestamp.
3. Both placebo tests use declared seeds, repeated null distributions, and finite-sample empirical
   p-values: `(1 + null scores >= observed) / (repetitions + 1)`.
4. Deflated Sharpe Ratio uses the immutable experiment trial count, the dispersion of available
   trial Sharpe estimates, sample length, skewness, and excess kurtosis.
5. PBO accepts only complete score matrices over a CPCV manifest whose hygiene audit fully passes.
6. Every JSON and Markdown report records lineage, seeds, trial count, method versions, thresholds,
   and the CPCV manifest hash.

## Default decision policy

- both placebo p-values must be at most 0.05;
- DSR probability must be at least 0.95;
- PBO must be at most 0.05.

Thresholds are explicit report inputs. Changing a threshold creates new evidence; it must never
erase an earlier rejected trial.

## Deliberate limitations

- The raw ledger count is used conservatively as the trial multiplicity. Estimating an effective
  number of independent trials is deferred until trial-dependence data are recorded.
- DSR Sharpe estimates must be unannualized per-observation ratios that share one frequency and
  convention; the selected Sharpe must be present in the supplied trial estimates.
- PBO operates on synchronized CPCV OOS path scores and requires an even number of at least four
  paths and at least two configurations.
- Passing Alpha Court is research evidence, not permission to trade or tune on the final test set.
