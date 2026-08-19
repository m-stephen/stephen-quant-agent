# V6.2 — Automatic Alpha Court

## Objective

Provide a generic, one-time adjudication contract for any automatically discovered candidate. The
court decides evidence; it does not search, mutate or tune the candidate.

## Frozen protocol

Before sealed evidence is opened, the protocol hashes the candidate semantic identity, dataset
snapshot, code commit, cost model, cumulative Trial count, sealed dates and thresholds. Evidence must
match that protocol, candidate, snapshot and exact window and declare `sealed_once` scope.

Minimum gates are immutable in the conservative direction:

- DSR at least 0.95;
- PBO, signal placebo and return placebo each at most 0.05;
- at least 15 positive paths from at least 20 total paths;
- non-negative median path and standard-cost Sharpe;
- doubled-cost Sharpe at least -0.25;
- capacity at least CNY 3 million;
- valid path counts and empirical skewness/kurtosis evidence.

Every gate must pass. Thresholds may be stricter but never looser. The adjudicator adds no Trial;
all estimation trials must already be represented by the frozen cumulative count.
