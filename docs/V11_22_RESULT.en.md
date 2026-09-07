# V11.22 Completed Results and Research Pause

## Conclusion

All four continuous accounts and the independent audit completed at 01:06 Beijing time on 8 September 2026, with terminal status `COMPLETE_DIAGNOSTIC_AUDITED`. Automated search is paused at the user's request. Historical continuation notes must not trigger another search or replay of consumed plans.

This is a portfolio-construction diagnostic, not a new Alpha certification. `validated_alpha=false`; DSR/PBO/placebo remain null with `NOT_RUN_DIAGNOSTIC`. The cumulative raw-attempt lower bound is 3,733. This batch used four native account attempts and zero new fits; the subsequent read-only review added zero Trials.

## All four accounts

3 January 2023 to 31 December 2024, 484 sessions; CNY 3 million initial capital per continuous account, without annual resets. Returns include frozen model costs. The 82/164 bps roundtrip scenarios are standard/double-cost stresses, not actual broker quotes. Sharpe uses zero risk-free return, sample daily standard deviation and 252-session annualization.

| Account | 2023 | 2024 | Total net return | Sharpe | Maximum drawdown | Net profit (CNY) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| global_lowvol-82 | +0.45% | +21.42% | +21.97% | 0.786 | -14.20% | 658,987.54 |
| global_lowvol-164 | -6.28% | +13.50% | +6.38% | 0.293 | -21.58% | 191,353.41 |
| global_hash-82 | +5.31% | +5.13% | +10.71% | 0.366 | -27.39% | 321,184.16 |
| global_hash-164 | +4.80% | +5.00% | +10.04% | 0.350 | -27.43% | 301,167.85 |

Global low-volatility improved on the prior stratified low-volatility control by 27.16 percentage points at standard costs (-5.19% to +21.97%). Risk allocation and retention changed jointly, so this is not an isolated causal effect or proof of predictive signal. Across 93 continuing sleeve refreshes, new-name share fell from 95.75% to 68.47%; this is not notional turnover. Standard-cost global low-volatility traded CNY 104,800,528.42 in absolute buy/sell notional and incurred CNY 428,408.51 of direct modeled costs. Its double-cost 2023 return remains negative.

## Integrity and limits

- Original execution code: `dbd1a3f0623a5199f51b5ea63cc3e40bf17b3334`. This documentation archive does not relabel results as a run of the documentation commit.
- Canonical plan SHA-256: `632253b6620c9fba7ac8c244857121c8aa3029f62f8c050142f502caa8ff315a`.
- RESULT SHA-256: `c5070db5ee9c9d6df8f2f051ce6c2c8f2e1e93bb1177c60698d925af33e6c7ba`.
- AUDIT SHA-256: `f1099e9451f2ec61a26499684f368e0bdcf7432d085b734017a3494273b5cf3b`.
- Native ledger SHA-256: `f60821fa6155da727dbe48174924870875695e61ffbfd93c2d98c9e5bc6a2f23`.
- Independently recomputed 26-account review summary SHA-256: `e7dfff41787d99433d0dbddbcb72481cdef1ec8b800e25337102ff66a1451c09`.
- The independent source audit checked 3,731,699 daily bars, 726 sessions and historical features; targets and all four accounts were separately reconstructed/checked. Producer time was approximately 194 seconds; audit time approximately 1,445 seconds.
- Original-code local regression: 1,627 passed, two skipped. [All three CI groups passed](https://github.com/m-stephen/stephen-quant-agent/actions/runs/34142836423). Engineering PASS is not Alpha PASS.

2023–2024 are repeatedly exposed development history. This batch/review did not read new 2025/2026 return labels. Raw sources, local directories, credentials and full account artifacts stay out of Git. Adjusted prices, fractional shares and capacity proxies do not certify broker lot sizes, minimum commissions or corporate-action cash flows.

Next is discussion of [Issue #200](https://github.com/m-stephen/stephen-quant-agent/issues/200): matched diagnostics, search/validation power and incremental returns. Discussion does not authorize empirical search, additional synthetic search or live trading.
