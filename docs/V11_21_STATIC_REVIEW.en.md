# V11.21 phase A: static mechanism review and response prototype

## Decision and scope

Proceed with engineering this representation, not with market execution or an Alpha claim. Phase A delivers a source inventory, additive narrative-independent identity keys and synthetic verification of a within-stock past-response estimator. No market values were read and no empirical Trials were added; historical debt remains 3660. The package remains 11.20.0 because the V11.21 release is incomplete.

This is an engineering review, not a backtest-return report. Analysis validation checks mathematical distinction, chronology and identity without treating synthetic signals or source matching as investment evidence. Independent recomputation means a different numerical method, not a second reviewer.

## Source inventory

Already executed: `python scripts/inventory_research_mechanisms.py --output artifacts/flow-response/static-inventory-001.json`.

The explicit allowlist covers 15 Python files and 337 source units. Every source has a raw-byte SHA-256 and every unit an AST SHA-256. Inventory digest: `78908c062133d6d3e5f53e23fc30976d2913781a8b807d66ace2869f4507f6c4`. Output uses exclusive creation. Checkout line-ending differences can change byte hashes; this is not a market snapshot change.

The inventory module uses only the standard library. A fresh subprocess verifies that discovery, qmt, factors and workflows modules are not imported or executed. Functions, declarations and branches can contain one another: 337 is NOT a count of independent candidates. Dynamic expansion is incomplete and an unmatched expression establishes no novelty.

| Existing mechanism | Source evidence | Treatment |
|---|---|---|
| Downside/upside volatility and skewness | factors/seeds.py; workflows/price_discovery_lab.py; workflows/v4_ohlcv_platform.py | Not renamed as new mechanisms |
| Flow/price divergence | discovery/generator.py, flow_price_divergence | Inherit the old economic family |
| Flow consistency times price rank | discovery/risk_stratified.py, flow_price_absorption | Retain as an old-representation comparator |
| Narrative participates in family identity | discovery/mechanism_lineage.py, semantic_plan_id | Add wording-independent keys; preserve old IDs |

A regression confirms that changing only an old proposal's hypothesis changes its old family and policy IDs. The additive keys stay equal, preserve legacy references and disallow debt reset. The alias table is a reviewed conservative grouping, not a universal semantic oracle. Canonicalization handles binary addition/multiplication commutation and equal integral literals, but not division cancellation, reassociation or expression execution.

The old V9 generator and historical ledger remain unchanged. These keys are not yet wired into production packets: phase B must integrate canonical tombstones and legacy aliases. Do not claim every historical deduplication path is already repaired.

## Implemented representation

For one stock, fit the 60 contiguous global sessions immediately before signal session t. Inputs are net-flow ratio f and contemporaneous source-adjusted close return r, observable strictly before fit_cutoff. Use population standard deviations and no future-return labels:

```text
zf = (f - mean_past60(f)) / std_past60(f)
zr = (r - mean_past60(r)) / std_past60(r)
beta = mean_past60(zf * zr) / 1.01
flow_surprise_t = standardized(f_t, past60)
response_residual_t = standardized(r_t, past60) - beta * flow_surprise_t
```

The 60-session window and ridge 0.01 are fixed prototype choices, not parameters selected from a new market backtest. Any future predictive direction must be learned from a preregistered mature training prefix, not reversed after inspecting development returns.

The model binds stock identity, global prediction session, training window, observation hash, frozen snapshot hash and fit cutoff. It applies only to the immediately following global session. Missing or unavailable recent data cannot silently select a stale window. Invalid values inside the window fail; an invalid value can eventually roll off after 60 clean sessions. Constant inputs, nonfinite values, cross-stock use, wrong model hashes, duplicate/unordered sessions and naive timestamps are rejected.

The synthetic counterexample preserves flow history, current flow/return and the 20-session compound return, while changing historical flow/price pairing. The residual changes. This establishes nonidentity with the old summary-rank product, not predictability, independent information or causality. The inherited economic family remains liquidity_impact_absorption.

## Verification and remaining work

Targeted suite: 50 passed; Ruff passed. Final complete regression is recorded in V11_21_VERIFICATION.md. Checks include independent NumPy linear solving, future poisoning, unit changes, stale-window rejection, gap recovery, stock/model binding and no-execution/no-overwrite inventory tests. No supervised return model is implemented, so there is no new predictive planted/null calibration result.

Before market execution:

1. Wire additive keys into the finite candidate packet with inherited families and negative evidence.
2. Build point-in-time per-stock series from the frozen daily/flow sources, preserving adjustment units, global calendar and missingness.
3. Implement native label-free fit artifacts and all consuming Trial edges, separately from mature-label supervised fitting. The current estimator is in-memory only.
4. Freeze candidates and common-support raw-flow/risk/fixed-shuffle/old-stability controls, direction-learning rule, horizons, CNY3m,82/164bps, capacity and the entire budget.
5. Finish synthetic runtime tests, commit code and publish the Issue #184 preregistration before one exclusive operation using authorized frozen 2022–2024 numerical inputs.

Reused 2023/2024 remains development validation, not fresh independent OOS. No 2025/2026 reads. DSR/PBO/placebo are NOT_RUN/null and validated_alpha is false. Exploratory and final Court gates are unchanged. No main merge, trading or data purchase.
