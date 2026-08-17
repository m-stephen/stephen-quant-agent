# Label-Free Semantic Search Controller — Specification

## Purpose

Improve factor proposal quality before any real return, IC, RankIC, Sharpe or backtest access.
The controller is an engineering and search-efficiency prototype, not an empirical Alpha epoch.

## Identity model

```text
SemanticPlan
→ MechanismFamily
→ ExpressionVariant
→ ParameterVariant
→ PolicyVariant
```

`ResearchContractVersion` is independent of candidate identity. It freezes PIT readiness,
horizons, falsification rules, snapshot/window authority and zero empirical-trial budget.

Context is typed as `CONSTITUTIVE`, `ELIGIBILITY` or `POLICY_CONDITION`. Only constitutive
context enters family identity. Formula sign/rank controls remain expression controls and cannot
create a new mechanism family.

## Static funnel

1. schema, enum, horizon and budget validation;
2. restricted-window reference rejection;
3. required-data and PIT-readiness gate;
4. canonical typed-DSL compilation;
5. semantic-family duplicate gate;
6. expression duplicate gate;
7. deterministic family tombstone gate;
8. Search Ledger decision.

Missing PIT data returns `DATA_NOT_RESEARCH_READY`. Exact semantic duplicates and tombstone
descendants are rejected before any empirical access.

## Remote and replay contract

Remote records are content-addressed by rendered request and raw response bytes. Provider/model,
prompt and parser versions, sampling config, tool calls, retry parent and hashes are retained.
Offline cache misses fail closed; there is no network fallback during replay.

## Synthetic benchmark

The committed fixture has isolated `train`, `validation` and `sealed_test` partitions and three
fixed seeds. It compares the bounded exact-expression baseline with semantic/tombstone-aware
selection. Success requires better worst-seed duplicate recall, correct PIT rejection,
deterministic replay and zero empirical or restricted-window access.

## Hard boundaries

- `inferential_trial_delta=0`;
- real market matrix reads = 0;
- restricted-window access = 0;
- remote model requests = 0;
- no Alpha Court or live-trading authorization;
- #92, #93 and Gate 5 remain unchanged.
