# V12.0 test report: mechanisms recovered, economic detection power insufficient

## Conclusion

The bounded **M0–M2 implementation agreed in Issue #200 is complete and its one
reserved synthetic audit has finished**. Calibration is **FAIL**: recovery plus
economic promotion was 40% for the linear case and 54% for interaction, below the
predeclared 80% power target. Both null distributions passed the path-FWER criterion.

These are generated-market tests, not a market Alpha backtest or expected investment
return. `validated_alpha=false`, new empirical trials = 0, historical raw-attempt
lower bound = 3,733. Automated search stays paused. Delivery does not authorize M4
or complete the later research milestones of #200.

[Chinese report](V12_0_RESULT.zh.md) · [Machine-readable summary](V12_0_RESULT.summary.json) ·
[Specification](V12_0_SPEC.md) · [Discussion](https://github.com/m-stephen/stephen-quant-agent/issues/200)

## Reserved audit

Exactly one suite was opened. **600 complete independent source/search paths**
finished in 530.36 seconds. Each path included training selection, offspring,
native continuous accounts and evaluation; candidates within one path were not
counted as independent replicates. No failed paths, replacement seeds or manual
substitutions were discarded.

| Scenario | Event | Events / paths | Adjusted interval | Frozen requirement | Result |
|---|---|---:|---:|---|---|
| Linear planted | Recovery AND economic promotion | 40 / 100 | 26.39%–54.79% | Lower bound >=80% | FAIL |
| Interaction planted | Recovery AND economic promotion | 54 / 100 | 39.33%–68.19% | Lower bound >=80% | FAIL |
| Correlated null | Any promotion | 0 / 200 | 0%–3.04% | Upper bound <=5% | PASS |
| Regime-volatility null | Any promotion | 0 / 200 | 0%–3.04% | Upper bound <=5% | PASS |

Exact binomial bounds allocate total coverage error 0.05 across four scenarios,
three fixed looks (100/200/500) and both tails. Zero events at 100 still gives a
5.99% upper bound, so the nulls continued to 200. Both planted upper bounds were
already below 80% at 100 and stopped as declared. This is all-null path FWER under
the named distributions, not mixed-population FDR or a market false-positive rate.

## Recovery is not the principal loss in these benchmark cases

| Diagnostic | Linear / 100 | Interaction / 100 |
|---|---:|---:|
| Exact expression and direction | 95 | 100 |
| Predeclared semantic recovery | 100 | 100 |
| True expression in top three | 100 | 100 |
| Final economic promotion | 40 | 54 |
| Known expression: positive mean increment at both costs | 96 | 98 |
| Known expression: same economic gate passed | 41 | 54 |
| Reference passed but discovered candidate failed | 1 | 0 |

Most attrition occurs **after expression recovery** in these two known generated
families. Providing the correct expression at the same selected horizon and under
the same ranks/execution only raises promotion to 41%/54%. This does not support
blaming every failure on the generator or concluding that purchasing data is necessary.
The reference is not an optimal portfolio/horizon oracle, so construction is not exonerated.

At double cost, 60 linear and 46 interaction paths fail HAC t>=2.5; only 6 and 3,
respectively, have paired daily means below 1bp. Failure reasons overlap and must
not be added as exclusive causal attributions. With 120 evaluation sessions,
positive net increment often lacks the required statistical evidence. This benchmark
effect-size/length/cost/gate combination is underpowered; it does not establish
that all validation standards should be weakened. No threshold changed after opening.

## Paired increments and costs

Values below are **mean paired daily return differences across independent paths,
in bps/day**. They are not one real portfolio's returns, must not be annualized as
market forecasts, and do not predict profits on CNY3m.

| Scenario | Zero cost | 82bps round trip | 164bps round trip |
|---|---:|---:|---:|
| Linear planted | 16.34 | 13.11 | 9.81 |
| Interaction planted | 25.02 | 19.87 | 14.62 |
| Correlated null | -0.44 | -4.05 | -7.65 |
| Regime null | -0.50 | -4.16 | -7.85 |

Matched accounts share ex-ante constraints, not realized fees or turnover. Local
evidence retains all four roles, daily returns, fees, traded notionals and group
exposures. NAV differences, cumulative-return percentage points, relative wealth
and CNY increments have separate definitions and calculations.

## Engineering verification

New targeted regressions: **47 passed**. Ruff passed for src/tests and the new
summary script. Clean-subprocess full regression: **1,674 passed, 2 skipped,
0 failed**, pytest wall time818.09s; JUnit suite time816.184s. The two skips concern
platform-specific resource measurement and symlink support. All three frozen-
implementation CI groups passed: Python3.10 trace120, Python3.10 trace0 and
Python3.12 trace120 ([run34154910807](https://github.com/m-stephen/stephen-quant-agent/actions/runs/34154910807)).
The latest documentation/summary-script commit has its own PR checks; an earlier
commit's green checks must not be presented as that later check result.

The initial full run was1,672passed,2failed,2skipped. It triggered the existing QD isolation guard in two CLI tests
because host maintenance configuration was inherited. Production guards were not
changed or disabled. That complete test file passes **10 tests** in a clean child
environment; persistent host configuration is unchanged. Initial engineering failures
and run evidence remain local. Error logs containing sensitive environment values
are excluded from Git and publication.

The read-only summarizer verifies hashes of all 600 results, plans, source bindings
and event ledgers, recomputes NAVs from daily returns for every four-account run,
and reconciles individual SQLite Trial identities: `PASS_HASH_COUNTS_SQLITE_DAILY_NAV`.
Native accounts also check scalar cash/marks/fees/returns. This is not full independent
order-fill reconstruction or broker certification.

- Independent sources, snapshots and experiments: 600 each.
- Training structure-label evaluations: 28,800; native four-account runs: 7,200;
  known-expression references: 400.
- Native synthetic Trial stage records: 36,400; fits: 0; empirical trials: 0.
- Global policy identities: 831; policy-by-source evaluations: 35,405. Neither count
  is the number of independent inferential trials.
- Two development suites of 16 paths each: 32 total, known development seeds,
  excluded from the 600-path readiness audit.

## Frozen provenance

- Implementation commit: `deee7ae6825f169ab02a77980abaa448850f6ce8`.
- Suite: `v12.0-reserved-audit-1`, consumed; cannot certify modified code by reopening it.
- Plan SHA-256: `3b0030507d309a0852afdfce1bddebfda8ca2304de08b4b1cf59919024f7d36d`.
- Pipeline SHA-256: `1b4c4b3a455b033853f0765a31d9fb4485fbe77aba6d0878d566879641ae3123`.
- Canonical RESULT SHA-256: `42cd33e56f3cc0dab389d1f363e12e770d7fd10c1254c4a1c96460defbe9028d`.
- Runtime: Windows, Python3.10.9, NumPy2.2.6, bound to executable bytes in the plan.
- Read-only aggregation: `python scripts/summarize_v12_reset.py --run artifacts/v12-reserved-audit --output <new-summary-file>`.

Full local artifacts are in this worktree's `artifacts/v12-reserved-audit/`: PLAN,
RESULT, TERMINAL, per-path source hashes/results/event ledgers and registry.sqlite3.
Large machine artifacts, real source paths and credentials are not committed.

## Recommended next step and limits

1. Retain this failure and do not expand real-label search. The finite search recovers
   mechanisms, but economic detection power is not certified at the chosen benchmark.
2. Design a bounded **effect-size x observation-length x cost power study**, preserving
   false-positive and evidence standards. Separate tradability from detectability.
   Development cases may inform design; a new reserved audit needs separate approval,
   identity and inherited failures, not unlimited revisions until PASS.
3. Diagnose gross-proxy versus net-account ranking and the effects of maintenance/
   holding rules using finite predeclared development comparisons, not unlimited
   parameter changes against revealed historical market windows.
4. Only then separately approve one finite M4 epoch on admitted existing data. Full
   data-domain completion is not required. Missing historical comparable matrices
   keep formal Court statistics NOT_IDENTIFIABLE/null, never invented values.

This run is stopped. No new market search, V11.2 clock reset or certified Alpha.
