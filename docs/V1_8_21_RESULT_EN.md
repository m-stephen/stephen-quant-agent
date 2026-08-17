# V1.8.21 Test Result (English)

## Conclusion

- **Engineering acceptance passed.** Six frozen portfolio definitions, five NAV levels, cost/capacity execution, incremental benchmarking, Trial registration, bilingual reports, and sealed-window auditing are connected.
- **Avoidance value is supported on a relative basis.** At CNY 3m, excluding the bottom decile improves net return by 11.28 percentage points, Sharpe by 0.151, and maximum drawdown by 5.13 percentage points versus the all-eligible equal-weight benchmark.
- **The reference is not independently investable.** Its absolute net return remains -10.29%, Sharpe -0.012, and maximum drawdown -41.10%.
- **Top-decile remains the best absolute mapping but still fails deployment standards.** Net return is +3.29%, Sharpe 0.178, and maximum drawdown -38.11%.
- **Control residualization does not improve monetization.** The controlled exclude-bottom-decile mapping returns -15.00%, below the uncontrolled exclusion mapping.
- **Research decision: retain a reference portfolio, do not promote an alpha.** The result is a real comparison baseline for the V2 Marginal Alpha Engine, not fresh out-of-sample evidence.

## Frozen run

- Final experiment: `exp_9f69d4068df04559`
- Campaign: `campaign_39a198e218c341ee`
- Data snapshot: `eb6b8b61030a338f417f79f969d7ebecd60bb3b3ff1103a57b718aabf25e3ccd`
- Portfolio config hash: `a8b671726c1fee3df614fb4099c855c186357151216767c4150efb0406975355`
- Research period: 2022-01-04 through 2024-12-31 (consumed research data)
- Reference NAV: CNY 3m; capacity curve: CNY 1m/3m/5m/10m/20m
- Global Trials in the V1.8.21 registry: 87, including the retained pre-benchmark first run
- 2025 validation / 2026 final test: not opened
- Alpha Court: `REJECT_ALPHA_COURT`

## CNY 3m comparison

| Mapping | Net return | Sharpe | Max drawdown | Δ return | Δ Sharpe | Drawdown improvement | Turnover |
|---|---:|---:|---:|---:|---:|---:|---:|
| All-eligible benchmark | -21.57% | -0.163 | -46.23% | 0.00% | 0.000 | 0.00% | 11.77 |
| Top decile | +3.29% | 0.178 | -38.11% | +24.86% | +0.341 | +8.12% | 23.11 |
| Top 30% | -8.65% | -0.035 | -36.67% | +12.91% | +0.128 | +9.56% | 17.12 |
| Exclude bottom decile | -10.29% | -0.012 | -41.10% | +11.28% | +0.151 | +5.13% | 12.02 |
| Bottom-decile underweight | -13.44% | -0.054 | -42.51% | +8.12% | +0.109 | +3.71% | 11.94 |
| Controlled exclude bottom decile | -15.00% | -0.072 | -44.24% | +6.56% | +0.091 | +1.99% | 12.49 |

## Interpretation

The V1.8.20 residual RankIC of 0.0852 and long-short spread of 4.16% do not automatically produce a strong long-only portfolio. V1.8.21 confirms that the factor improves a broad benchmark on a relative basis, but the improvement is insufficient to turn a weak absolute portfolio into an acceptable risk-return profile.

The preregistered reference remains exclude-bottom-decile at CNY 3m. It is a fixed comparison target for the V2 marginal-alpha layer, not a validated alpha library.

## Integrity note

The first real run exposed a missing all-eligible incremental benchmark. Its Trials were retained. The formal rerun added only the benchmark already required by Issue #37 and registered every attempt in the same database. No post-result threshold or seventh strategy mapping was introduced.

## Next step

Proceed to V2 M0: compatible V1-to-V2 migration, hierarchical canonical IDs, separate Search and Inferential ledgers, and replay manifests while reusing the current FactorSchema, safe DSL, registry, and research-memory foundations.
