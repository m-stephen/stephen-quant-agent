# V12.0 — Bounded Research Reset / 有界研究重构

## Frozen scope / 冻结范围

Implements the M0–M2 agreement from Issue #200 and comments 5574190768,
5574559507, 5574601170. The user authorized this version's development and tests.
No M4 real-label epoch, M3 data purchase/ingestion, V11.2 evaluation, trade or
automatic follow-on search is authorized. Original RFC/discussion is preserved.
Package version becomes 12.0.0; base main is 50cbc1951d75bf19d79ed263a9621b181ac8af20.

## Acceptance / 验收

1. M0: Separate allocation vs predictive-increment evidence; capability vs authority;
   retain historical raw-attempt lower bound 3,733 and old consumed-operation guards.
2. M1: Reuse native stateful execution for four roles at 0/82/164 roundtrip bps;
   same initial CNY 3m, dates, eligibility, maintenance and execution policy.
   Compare risk+signal with risk-only; signal-only is an unmatched ablation.
   Six synthetic risk groups, one equal-weight name per group, top-two retention;
   not a claim of exact realized volatility/beta matching or broker certification.
3. Define paired daily net difference, descriptive HAC(10), relative wealth,
   total-return percentage-point difference, CNY wealth difference, active vs
   relative-wealth drawdowns, actual fees/traded notionals and exposure differences.
4. M2: Actual source → finite adaptive search → native cost accounts → selection
   gate → oracle-only evaluation. Public synthetic input excludes oracle/case/seed.
   Four initial dimensionless fields; rank and pair interaction, signs and 5/10-session
   horizons (40 structures); at most eight gate offspring of training-selected parents.
   Static/label-stage identities and rejections are retained: 48 training-proxy reads,
   12 native account runs (four roles x three costs), plus two evaluator-only known-
   expression accounts per planted path. This is 62 native Trial stage records per
   planted path or 60 per null, NOT 62 independent inferential trials. A policy already
   scored in training and evaluated in an account has two stage records; no debt erased.
   Training labels mature by session 95; evaluation starts 100. No fitting on evaluation.
5. Four required scene distributions: linear, interaction, correlated null and regime
   null. New independent synthetic sources and search paths per replicate. Noise
   includes common/group shocks; predictive features available before next-open entry.
   Source/evaluator parameters and all thresholds freeze before reserved audit begins.
   Both planted scenarios have a known-expression reference at the search-selected
   horizon, under the same ranks, eligibility, costs and execution. It is diagnostic,
   not a clairvoyant optimum. Its failures never remove paths from the denominator.
   The power criterion combines semantic recovery AND economic promotion. If even the
   reference fails, report limited economic detectability, not automatically a search
   bug. These signal strengths are declared benchmark cases, not empirically certified
   minimum detectable effects. A FAIL is allowed and cannot trigger weaker thresholds.
6. Exact binomial intervals at 100/200/500 paths per scene, delta_cal=.05 split over
   four scenes × three looks × two tails. Power lower bound >=.80; any-promotion
   null FWER upper bound <=.05. No mixed-population FDR claim. At limit unresolved
   -> INCONCLUSIVE. Errors are ENGINEERING_FAIL, never successful negative controls.
7. Economic diagnostic promotion: paired mean >=1bp/day, HAC t>=2.5 and positive
   means in both evaluation halves under both positive cost models. It is not Court
   PASS. Full historical DSR/PBO/placebo remain NOT_IDENTIFIABLE/null because the
   required historical comparable-return matrix is not supplied. No invented probabilities.
8. Single-use reserved audit binds pipeline hashes, scenario distribution and exact
   seed schedule; globally shared local claim, no caller-injected source/ledger path.
   Development tests may repeat with records; only one reserved audit opening in v12.0.
   Changed pipeline requires a separately numbered/approved audit; no auto retries.
   Report honestly: held-out random seeds in known synthetic families, not double-blind
   human research and not evidence that future real-market Alpha exists.
9. Runtime and source hashes, actual operation ledger, all synthetic attempts/fits/
   account runs and failures retained. Source arrays hashed before labels are read.
   No production database/path/credentials exposed to the calibration entry point.
10. Deliver CLI, adversarial tests, full regression, bilingual result and interpretation.
    M0–M2 software can complete even if statistical readiness FAIL/INCONCLUSIVE.

## Reuse and gaps / 复用与缺口

- Reuse StatefulBar/TargetAllocation/native execution, SearchField/SearchCandidate,
  SHA manifests and native ExperimentRegistry. No replacement of historical hashes.
- Add typed finite operators, paired estimands, pipeline-level finite-look calibration,
  scope guards and synthetic audit/operation evidence.
- Existing V11.21 B5b proved one strong source-level recovery; the new multi-seed
  suite tests this new bounded search, not every old or future DSL operator.
- Not implemented here: real-domain adapters, new PIT data, generic arbitrary AST,
  live brokerage economics, optimization of old candidates, deep learning or M4.

## Commands and operational limit / 命令与运行边界

```powershell
stephen-quant research-reset status
stephen-quant research-reset plan --mode development --development-paths 4
stephen-quant research-reset run --plan <returned-plan-path> --output artifacts/development-unique
# Once only, after pipeline freeze; never rerun this as a new seed lottery:
stephen-quant research-reset plan --mode audit
stephen-quant research-reset run --plan <returned-audit-plan-path> --output artifacts/v12-reserved-audit
```

Output must be a new artifacts subdirectory. Plans/claims live in a gitignored
control directory shared by this repository's worktrees. Source paths cannot be
passed to this CLI. Python/NumPy/platform versions and executable file bytes bind
the plan. A crash retains the claim and partial native ledger; do not delete it.
Maximum runtime: four hours; at most 500 paths per scenario, 2,000 total. No automatic
replacement, subjective veto/recursion, or second reserved audit in V12.0. Development
cases, including failed runs and repeated known seeds, are not readiness evidence.

`status` previews the static capability/authorization contract; it does not load a
previous audit result. Read the hashed RESULT/TERMINAL and bilingual report for an
executed suite. From an uninstalled worktree, use its `src` on PYTHONPATH and invoke
`python -m stephen_quant.cli research-reset ...`; do not silently use another
worktree's older editable installation. NumPy is provided by `[research]` or `[dev]`.

The cheap training score is a gross matched-group horizon spread, whereas the final
diagnostic uses a continuous fixed risk-baseline account with costs. Their mismatch
is an explicit limitation to measure, not an assertion that proxy ranking is optimal.
No learned transform is enabled; daily cross-sectional ranks use decision-time
common support. Existing fold-local fit rules remain unchanged for future operators.

## Research increment / 本轮研究增量

Distinguish failure to detect an injected tradable mechanism from failure of a real
mechanism to add matched-risk net value. Null paths diagnose spurious promotion.
No claim that a new version, nonlinear operator or new dataset guarantees Alpha.
Known diagnostic failure is a valid terminal result, not permission to expand search.
