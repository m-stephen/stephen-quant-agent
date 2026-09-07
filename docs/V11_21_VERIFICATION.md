# V11.21 engineering verification / 工程验证

## Latest checkpoint: phase B3 / 最新检查点

**163 targeted passed in45.03s;1204 full passed,1 skipped in226.11s.** JUnit reports1205total,0failures,0errors,1skip (suite time226.003s). Ruff check src/tests/scripts,format check of7new/modifiedPythonfiles and Git whitespace pass. Sessions82285targeted and25359full completed exit0; no test/market process remains. Prior B2headbbe3944d208d88df5e12f942aca58bbdeb078256/CI34072443592 verified SUCCESS; new B3commit CI must be verified separately.

Saved ignored artifacts:

- `artifacts/flow-response/phase-b3-regression-20260907.xml`, SHA256 `7a9ed3cc729fc44b58f7adc2f52353e2825f87a2460c84e3d3a458ca9e99c934`.
- `artifacts/flow-response/phase-b3-targeted-20260907.xml`, SHA256 `b9baffb77ab891bbe8962b977ef04e92b3b04b1a38aeba1c836dc75651c94b08`.

Targeted command: `python -m pytest -q tests/test_flow_response_panel.py tests/test_flow_response_history.py tests/test_flow_response_inputs.py tests/test_flow_response_predictor.py tests/test_flow_response.py tests/test_flow_response_series.py tests/test_mechanism_inventory.py tests/test_fit_lineage.py`. Full command: `python -m pytest -q --tb=short --junitxml=<new-unique-path>`. Existing JUnit artifacts must not be overwritten.

Initial new-only tests exposed Decimal/float source math and two fixture mistakes, corrected before final runs. Their failed artifacts`phase-b3-new-20260907.xml`and`phase-b3-new-v2-20260907.xml`remain. Interim18new tests passed38.05s (`phase-b3-new-v3-20260907.xml`); final25new tests plus138prior targeted tests pass163. Do not add interim or failed attempts to passed totals.

Source→native daily response bundles→bound historical matrix→mature predictor→all9policies/2costs is synthetic integration only. Independent NumPy statistics spot checks at3dates and per-ordercost/dailyNAV identities pass; they do not substitute for complete empirical source/model/label/target/NAV audit. Real numeric source reads0,empiricalTrials0,debt3660; real account backtest/Court NOT_RUN. See PHASE_B3.zh.md/.en.md for exact boundaries and pending original anchors/packet/budget/runner/preregistration.

## Historical checkpoint: phase B2 / 历史检查点

Phase-B2 reader/predictor primitives: **138 targeted passed in6.66s;1179 full passed,1 skipped in191.64s**. JUnit totals1180tests/0failures/0errors/1skip. Ruff check src/tests/scripts, all4newfiles format and git whitespace checks passed. Full session91563 ended exit0; no tests/market process remains. An earlier138targeted run before test-style cleanup is superseded, not added to the final result.

Saved ignored evidence:

- `artifacts/flow-response/phase-b2-regression-20260907.xml`, SHA256 `b3fb0c2dcde1908089f5c536632dda618ceab2d7f3eb53b0deb69c46aa3e8d99`.
- `artifacts/flow-response/phase-b2-targeted-final-20260907.xml`, SHA256 `aad55442db69bd1ff3eff6e26b69d67009522f17279072e5c56af9624590599b`.

Targeted reproduction: `python -m pytest -q tests/test_flow_response_inputs.py tests/test_flow_response_predictor.py tests/test_flow_response.py tests/test_flow_response_series.py tests/test_mechanism_inventory.py tests/test_fit_lineage.py`. Existing output files are immutable; choose new names for intentional reruns.

All new numerical tests are synthetic. Market numeric reads0/newempiricalTrials0/debt3660; account backtest and Court NOT_RUN. The supervised primitive is now tested with synthetic mature labels, not real market labels. Passing planted/null fixtures is not an Alpha or false-positive-rate estimate. See PHASE_B2 zh/en for complete limitations and the still-unimplemented end-to-end historical feature/target/account chain. Phase-B1 CI34071068619 was verified SUCCESS; B2 CI must be checked for its own exact head.

## Historical checkpoint: phase B1 / 历史检查点

Phase A below is retained as historical evidence, not the current implementation boundary. See `V11_21_PHASE_B1.zh.md` and `.en.md` for the implemented shared native fit/source bridge/packet primitives and limitations.

Final phase B1:105 targeted passed in5.52s; full1146passed/1skipped in190.93s. JUnit tests1147/failures0/errors0/skipped1. Persisted ignored full result `artifacts/flow-response/phase-b1-regression-20260907.xml`, SHA256 `27a190e4a94e3c87926bf8d8a7b36a8ca4981c96ee5e8dffee8d60fd302b83c0`; targeted result `phase-b1-targeted-20260907.xml`. Test session72632 completed, exit0; no active market run. One earlier full-run output was lost in context truncation; only after confirming its process ended was this verified rerun started. Do not rerun it merely because the earlier terminal output is unavailable.

Ruff check of src/tests/scripts and git diff --check passed. Format passed for6new/dedicatedfiles; inherited registry/fit_lineage whole-file formatting is not claimed. These are synthetic/regression results, not evidence of Alpha. Actual empirical reads0/newTrials0/debt3660; supervised fitting/backtest/Court NOT_RUN. Phase-A CI34069051824 succeeded; phase-B1 head CI requires separate verification.

Reproduce targeted phase B1 with `python -m pytest -q tests/test_flow_response.py tests/test_flow_response_series.py tests/test_mechanism_inventory.py tests/test_fit_lineage.py`. Full suite and Ruff commands below are unchanged. Do not overwrite existing JUnit artifacts when intentionally rerunning.

## Historical phase A / 阶段 A 历史记录

Scope: source-only inventory and an in-memory response prototype. 本记录不是市场实验或 Alpha 测试报告。

| Check / 检查 | Actual result / 实际结果 |
|---|---|
| Targeted synthetic tests / 针对性合成测试 | 50 passed in 2.42s |
| Final complete suite / 最终完整回归 | 1107 passed, 1 skipped in 189.09s |
| Ruff src/tests/scripts | All checks passed |
| Formatting of 5 new Python files / 新文件格式 | 5 already formatted |
| Git whitespace / Git 空白检查 | git diff --check passed |
| Source inventory / 源码盘点 | 15 files, 337 source units; exclusive artifact produced |
| Empirical market values read / 实证市场数值读取 | 0 |
| New empirical Trials / 新实证 Trial | 0; inherited debt 3660 |
| Supervised predictor, account backtest, Court / 监督预测、账户回测、Court | NOT_RUN; unavailable, not passing |

The final suite completed after stock-identity binding was added. An earlier interim suite was1106passed/1skipped; it is superseded by the final1107passed/1skipped result, not added to it. Final local test process99605 is complete; there is no active market or audit process. Targeted process ended successfully. Credentials for AlphaPai were removed from test-child environments without printing their values.

最终完整测试在增加股票身份绑定之后执行；之前1106项的中间结果已被替代，不相加。所有测试过程已经结束，未启动真实市场实验。父 V11.20 的 operation、审计、报告也没有重复执行。

Reproduction from this checkout / 在此工作树复现：

```text
python -m pytest -q tests/test_flow_response.py tests/test_mechanism_inventory.py
python -m pytest -q
python -m ruff check src tests scripts
```

The source-only inventory command is recorded in both STATIC_REVIEW documents and has already run. Its output is ignored and immutable: `artifacts/flow-response/static-inventory-001.json`,411037bytes,inventory digest`78908c062133d6d3e5f53e23fc30976d2913781a8b807d66ace2869f4507f6c4`. Its 337 units must not be presented as independent candidates. Raw-byte source digests are checkout-specific; no cross-platform byte-identity claim is made.

Assessment: ready to review as an engineering checkpoint; not ready for a real V11.21 epoch. Native unsupervised fit artifacts/consumer edges, production semantic deduplication, source bridge, supervised mature-label fit, finite controls/budget and preregistration remain pending. No charts or return tables are appropriate because no new market results exist. CI status belongs to the exact remote head and must be checked separately; local success does not establish GitHub Actions success.

结论：可以审查这份工程检查点，尚不能执行真实 V11.21 实验。原生拟合血缘、生产去重、数据桥接、监督训练、完整对照/预算和预登记仍未完成。没有市场结果，因此不制作收益图表。远端 CI 需独立核验，不用本地通过代替。
