# V11.19 verification / 验证记录

## Final real-data evidence / 最终真实数据证据

Corrected runtime `50afdc55acfe28ebb22bc4217bdc70f75833aea2`, separately preregistered in Issue184 comment5562635689, completed **24/24 accounts,16 models,32 native fits**. Independent audit PASS:3,249,002 source feature rows,189 rank dates,56,320 pair evidence rows,12 target sets and all484-session accounts. Maximum cash/NAV residual is4.656612873077393e-10 CNY. The original aborted24 reservations remain intact; total debt is3648, not3624.

- RESULT SHA-256: `319dcb2dd2e85aa208424c70f4e8e2c2160657f44ab1fae480f3c0a1355c7337`.
- INDEPENDENT_AUDIT SHA-256: `d35a0c906b28e0704c9c7d43df55e9139f0445ace309a1605a78cef3ec2626f7`.
- Corrected runtime CI34064183636: SUCCESS.
- Full synthetic regression1020 passed,1 skipped;38 new tests; RuffPASS. Final post-report rerun also1020 passed,1 skipped in179.40s; scoped src/tests/new-scripts Ruff and git diff whitespace checks PASS. Neither reruns market accounts.
- Two language reports,complete24-row summary and four ordinary-Python notebook cells generated successfully. Native report schema validation PASS,2 datasets/1 source. Jupyter frontend QA NOT_RUN because optional dependencies are absent. Visible/pixel QA is explicitly deferred under the user's quiet-until-usable instruction; no rendering claim.
- **Economic screen0/2;certified usable Alpha0.** Both bases fail annual positivity,Sharpe,drawdown and comparator increments at both cost levels. DSR/PBO/placebo are NOT_RUN/null,notPASS.2025/2026 untouched;no main merge or live trades.

## Archived pre-execution receipts / 运行前记录留档

The following receipts describe their original pre-execution state; pending statuses are superseded by the final evidence above.

V11.19.1 correction suite: **1020 passed,1 skipped in179.19s**, RuffPASS. Two new regression tests cover terminal reduction roundoff, unchanged stationarity tolerance, rejection of nonstationary/materially higher/nonfinite loss and an end-to-end synthetic strictly convex optimizer. The original frozen epoch aborted before account evaluation; see V11_19_ABORTED.md. Corrected market execution remains pending separate preregistration and24additional native reservations. Initial runtime CI34063439437 wasSUCCESS, which did not guarantee real-matrix numerical robustness.

Premarket full suite: **1018 passed, 1 skipped in181.68s**. Thirty-six new synthetic tests cover planted interaction recovery, style-only explanation, heldout noise, temporal gaps, pair membership before outcomes, mature labels, equal-date weighting, analytic gradients/Hessians, native24-trial/32-fit contracts, artifact tampering, independent raw-source SQL, rank/target reconstruction and exclusive evidence writes. Ruff and git diff whitespace checks pass. An unused test import was removed after the full suite; no economic implementation changed.

Synthetic calendars are artificial daily fixtures, not real exchange sessions. Successful algorithm tests do not demonstrate market predictability or Alpha Court power. Training pairs overlap in time.

Actual market execution, independent audit and remote CI are pending this runtime commit. No2025/2026 rows are authorized. No claim of usable Alpha, no main merge and no trading.

中文：全套1018通过、1跳过；新增36项合成及独立复算测试。工程通过不表示金融有效。此提交时真实回测、独立审计和远端CI尚待执行。
