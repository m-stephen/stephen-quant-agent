# V11.21 B5: Independent numerical audit and measured resources

## Conclusion: continue engineering validation, not an Alpha release

This checkpoint adds an independent numerical path from frozen source files through models and targets to account execution. The complete synthetic pipeline passed its initial audit. This demonstrates reproducibility of the disclosed implementation, not predictive market returns. V11.21 has no real market epoch, zero new empirical Trials and an inherited lower bound of 3660. PR #199 remains Draft; main and package version 11.20.0 are unchanged.

Final full regression: **1306 passed,1 skipped in417.96s**. Ruff,formatting of14changedPythonfiles and Git whitespace checks passed. Artifact hashes are in `V11_21_VERIFICATION.md`. Resource observations below are measured process statistics,not backtest results.

## Definitions: independent computation is not an independent sample

The full fixture has 80 synthetic stocks and 550 weekdays, covering 2022 training and continuous 2023/2024 accounts. There are 488 historical bundles containing 39,040 stock-level response fits, 14 actual supervised model files, 28 cross-cost native fit bindings, 22 accounts and 23 native reservations. Temporary fixture ledgers do not increase empirical search debt.

Independent means the audit does not call production numerical readers, response/risk/rank calculations, supervised fitting, labels, selection or execution to manufacture agreement. Native lineage, canonical hashes and data structures remain shared infrastructure. This is neither a separately developed third-party certification nor proof of vendor first-seen timestamps, broker execution or Alpha Court eligibility.

## Sources, models and targets have a separate calculation path

- Independent DuckDB projections verify actual source hashes, row counts, unique keys and dates. Numeric reads cover only daily/fund_flow and the permitted years in batches of 2048 rows. The other three sources appear only in manifest metadata; their files are not opened.
- The daily reference reconstructs every bar, risk-cell rank and past-only stock response fit. Availability is checked before numeric inspection, with explicit global gaps, adjustment, suspension and conservative opening restrictions.
- Supervised audits independently construct mature pair labels, date-equal designs and fixed shuffled controls. Augmented weighted SVD least-squares replaces production normal equations. Prefix, training/design hashes, coefficients, gradients and both cost bindings are compared.
- After coefficients have been independently verified, original persisted coefficients drive an independent nine-policy/four-phase target reconstruction. This avoids changing tied scores through solver rounding. The two original anchors retain actual original card/target-byte verification.

General float tolerances are relative 2e-10 and absolute 2e-12. Identity, key support, order and actual byte hashes do not receive numerical tolerance. Tests include future poison, gaps, unavailable observations, splits, zero turnover, duplicate identities and native-evidence mismatches.

## Accounts validate intent as well as cash arithmetic

An independent path reconstructs requested orders from previous holdings/cash, opening information and targets. It checks pending target_changes requests, capacities and analytic proportional funding under the frozen linear fee model, then reconstructs fills, shares, cash, marks, daily/annual returns, Sharpe, writeoffs, recoveries and numerical summaries.

Full account reports are written exclusively and bound by actual hashes in native outcomes. The offline audit checks both compact JSONL and full reports without executing another account or mutating RESULT/Trials. The end-to-end fixture verifies unchanged RESULT and SQLite hashes before and after audit.

Order reason text labels, and the blocked_orders count partly defined by those labels, are not independently certified; that limitation is explicit. Requested, filled and blocked monetary amounts are independently checked. Daily opening-limit proxies and fractional adjusted shares remain disclosed approximations, not broker certification.

## The 320-stock probe ran; full-market memory safety remains unproven

A separate process generated two synthetic source files with 176,000 rows each (320 stocks × 550 days), built native history and loaded/verified the immutable cache. It did not run supervised models, all accounts or the complete offline audit.

| Completed stage | Cumulative seconds | Process peak RSS bytes | Current RSS bytes |
|---|---:|---:|---:|
| After imports | 0.00 | 66,551,808 | 66,547,712 |
| Synthetic sources | 1.73 | 131,911,680 | 71,475,200 |
| Native history | 189.71 | 536,477,696 | 205,410,304 |
| Verified cache | 193.59 | 577,728,512 | 541,573,120 |

RSS measures resident physical memory; MiB means 2^20 bytes. Final peak RSS was 550.96 MiB and peak private commit 631.51 MiB. Measured physical RAM was 31.92 GiB, with 15.46 GiB available at the final sample, not a guarantee for a later operation. History JSON occupied 107,557,523 bytes and bundles 101,732,413 bytes.

One scale point does not establish linear memory/time scaling. The reference source scan is batched, but full history JSON, immutable cache, training designs, targets and accounts still require whole-process resource validation. Bounded source scanning is not a bounded-memory pipeline. Original manifest totals include 2021 metadata and are not the selected 2022–2024 numeric row counts.

The first direct probe invocation failed before source generation because imports resolved to an older installed checkout. Explicit local src resolution fixed it; the subsequent exclusive probe completed. No market budget was replayed.

## Next: prove recoverability, then run one controlled empirical epoch

1. Add source-file-level planted/null fixtures with known raw price/flow mechanisms. The full pipeline must recover a planted relationship without promoting null data; array-level fixtures and numerical agreement alone do not establish that.
2. Measure history, training and complete-audit resources further; use bounded persistence/sequential release if required before market scale. Resource measurement does not expand market-read scope.
3. Finish a globally exclusive entrypoint binding fixed parent RESULT/AUDIT/ledger, source/card/target/code/auditor hashes, complete budget and Issue #184 preregistration. Append AUDIT and later ASSESSMENT rather than modifying old RESULT.
4. Only after those checks and freezing, reserve all 23 Trials for one permitted 2022–2024 epoch, retaining inherited debt. Keep CNY3m, 82/164 bps, every control and gate; no 2021 numeric warmup or 2025/2026 reads.
5. Freeze a promising survivor before deeper falsification. Preserve failures and develop a newly justified finite plan when rejected. Repeated tuning on revealed samples is not independent validation. DSR≥0.95, PBO≤0.05, placebo≤0.05 and path/independent-evidence requirements remain unchanged.

The open research question is whether within-stock flow/price response adds tradable information beyond risk, raw flow, own returns and original anchors. This checkpoint does not answer it or guarantee a usable Alpha exists.
