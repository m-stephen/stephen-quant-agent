# V11.21 engineering verification / 工程验证

## Latest checkpoint: B8 once-only entrypoint and read-only audit

Full regression **1399 passed, 2 skipped in514.80s**; JUnit1401total/0failures/0errors/2skips,time513.612s. Session12859 completed exit0. FullJUnit `artifacts/flow-response/phase-b8-regression-20260907.xml`, SHA256 `15a1cfefdf9691cd5cfba37e188e043d69434c8cef19066585434e1fa6902e7a`. Ruff src/tests/scripts and4changedPythonformat PASS. No Python changes after this fullrun. Same two platform/symlink skips are not passes.

Targeted launcher/supervisor56passed18.67s/session14543: `phase-b8-final-targeted-20260907.xml`, SHA `a5b582f2eeed4f3217727264f31df142e4214443151572022e418ce004d30101`. Initial28tests had1failure27passes14.27s, SHA `f5d602a9427b6d3316f5776d3072cac6341753fb4f0312f29c61760199520009`: invalid JSON was correctly rejected but a test expected the wrong exception message. The assertion was corrected, not the fail-closed behavior. One unused fixture variable lint finding was fixed before finalfullrun. Intermediate tests are subsets, not additive.

34newlaunchtests verify frozen bytes/protocol/code,DATE-only two-sourceprepare,nondecodedoriginaltargets,all23native reservations,priorledger,preregistrationAPI/times/hash,globalclaim across actualGitworktrees,resource/refusal/failure retention,partialnativecount honesty,child-evidence tampering and sequentiallifecycle. Lifecycle numerical stages are stubs,not new fullpower experiments. Existing complete numericalepoch now audits through ReadOnlyRegistry(mode=ro/query_only),with unchangedRESULT/nativeDBhashes. Windowsownedchildmeasurement remains inexisting tests. No real numericalrun has been certified by these tests.

B7CI34086974315/job101632767939 CANCELLED at05:44:17Z after05:29:05Zstart(~73%). Root cause correction: ubuntu-slim hard15minute runnerlimit,not configurable20minutejoblimit. B7 YAML40minutechange didnot solveit. Repo public verified by GitHubapp and approvedhostnetworkCLI; B8 uses standardubuntu-24.04/fullsuite/40minjob,not largerpaidrunner. Officialsource and caveats inPHASE_B8.zh/en. B7Issue184comment5565525869 andB7docs explicitlycorrected,oldtestresults unchanged. Newcommit remoteCI must be independentlychecked afterpush;no rerun of obsoletecancelledheads.

Ready next: commit/testedcode,prepare actualhash/date-onlyplan inignoredartifacts,publish fullIssue184preregistration withplanSHA,thenone bounded realrun onlyafterCI/preflight. Main/rootdirtyfiles untouched. Empiricaldebt remains3660 untilactualglobalclaim;thatclaim commits23evenifnative reservationfails,withactualnativecountreported separately. All financial/source/Court gates remainfrozen. B8 code alone is not a marketAlpha result.

## Historical checkpoint: B7 day-scoped views and owned-child supervision

Full regression **1365 passed, 2 skipped in498.90s**; JUnit1367total/0failures/0errors/2skips,time497.712s. Session92582 complete exit0. FullJUnit `artifacts/flow-response/phase-b7-regression-20260907.xml`, SHA256 `85130f405c826734e7f21f51fbf08dc1c3dd82fed061b89fe52401543226d8ae`. Skips: non-Windows measurement capability branch and unavailable symbolic links. Ruff src/tests/scripts and9changedPythonformat PASS; no Python edit after the full regression.

Earlier views/series/history63passed61.51s, JUnit `phase-b7-views-initial-20260907.xml`, SHA `fa85dada7d6ce94510e4621fb4f51bc12978b7c87863a9f92e6dcb1034f64318`; guards/views28passed1.72s, JUnit `phase-b7-guards-initial-20260907.xml`, SHA `3fe8d7caf9f30735f403267e7e0eb8206b702b7421b448fab65d58559fa34b42`. These are subsets, not extra passes. Initial twoBLE001 lint findings were corrected with justified boundary-only suppressions and interrupt propagation before final regression.

6newviewtests and22newsupervisortests:exactbar/order/pair/account/hash equivalence,excludedfutureprojection rejection,4800constructions/<=160livebars,earlyflowrelease,actualproducercacheweakref releasebeforeaudit,exclusiveoutputs,resourcepreflight/guards/measurementfailure/nonzeroexit/no-sampleexit/interruption/terminationfailure/platformgaps and realhiddenWindowschild. No new empiricaldata,model/account replay or B5b/B6 benchmark. Underlying source/history remains materialized; no end-to-end resource or Alpha certificate. Details/limitations in PHASE_B7.zh/en.

B6 CI34084914378 confirmed CANCELLED;job101626978133 logs reached~80% beforecancellation,consistent with20min joblimit. CI timeout changed20→40min with same runner/fullsuite; newremote status must be checked afterpush. No source/math/gate changes in that CI edit. Debt3660,PR199Draft,nomerge. Next B8 globalactualparent/source/anchor/code/auditor/preregistration-bound launcher and syntheticguardtests, then oneauthorized23Trialepoch. Do not repeat completedtests on wake.

## Historical checkpoint: B6 lower-copy storage

Full regression **1337 passed, 2 skipped in478.79s**; JUnit1339total/0failures/0errors/2skips,time478.688s. Session77668 completed exit0. Ruff src/tests/scripts and10changed Python file format checks PASS. FullJUnit `artifacts/flow-response/phase-b6-regression-20260907.xml`, SHA-256 `2e776827468adad9f94609da21182ffa4f10c5c6ba1166d639485f7cf48d8b9f`.

Final targeted41passed1skipped57.45s/session68578exit0; JUnit `phase-b6-final-targeted-20260907.xml`, SHA-256 `551033ea6bf63ea8afe1012669b623c8cf6adceb9e822ef8b8001cdb30919046`. Earlier initial43pass/54.51s and probe18pass1skip/.86s are subsets, not additive. Newtests cover12storage,2prefix-cache and5supervision/fixture guards plus platform-owned-process measurement. Fullsuite's two platform-related skips are not passing tests.

Owned storage benchmark session85966 completed exit0. All4fixed cases finished or were deliberately stopped; nothing remains running. Plan1x/32x andlegacy/lower-copy was bound beforeexecution. Large legacy was stopped by the10GiBguard at peakprivate10782793728bytes/26.081035s;large lower-copy completed at9298939904bytes/204.270306s with exact canonicalhash. Small cases519811072/321011712bytes private and3.441546/6.869375s. Single-shot timing, no fullpipelinecertificate. The lower-copy implementation is a memory/CPU tradeoff, not an across-the-board speedup.

PlanSHA `6419a5b42dd158a00b22635bc57c52a1e9e9b72a18c637247eee8c561c7a5b68`; RESULTSHA `2676b939000f515b2a57cadb1b6f69f2822e81945dbaa80660dabe9e3eb49b8f`. Detailed counts,limits,fixturehashes,limitations and bilingualresults are inPHASE_B6.zh/en. All benchmark code hashes were rechecked unchanged after finaltests; no old model/account replay. Source batching, bottom-up immutable decoding,chunked canonical hashing,early panel release and once-per-yearprefixhashes preserve contracts. Actualnative/source/bundle guards still precede eachfit.

B5bhead e6a0fcb2d23b440e3596126b3ae7758a67583aed / CI34082559337 nowverifiedSUCCESS. Empiricaldelta0/debt3660. PR199 remainsDraft, no mainmerge. Next: fullpipeline memorylifetimes and globallyexclusive actualparent/source/code/auditor/preregistration-bound once-only launch; no realnumericread or23empiricalreservations until ready. Do not rerun completed B5b/B6 operations or finishedtests on a wakeup.

## Historical checkpoint: B5b paired source-level recoverability

Full regression **1317 passed, 1 skipped in483.04s**; JUnit1318total/0failures/0errors/1skip,time483.003s. Session75063 completed exit0. Ruff src/tests/scripts and format of4new Python files PASS. FullJUnit `artifacts/flow-response/phase-b5b-regression-20260907.xml`, SHA256 `9fd33df91e50c04d1a45d14c1912734b07dd0e582e3a880e1237f6da410bf8d2`.

One fixed paired source calibration completed successfully, session83045 exit0; childplanted6832 andnull35256 ended.160stocks×782synthetic weekdays;2sourcefiles×125120rows each;522account periods;23synthetic native reservations/14annualmodels/28bindings/22accounts percase. Total46synthetic reservations,0empirical trials,debt3660. Actual source→history→model→target→account independent audits PASS on both cases. No market numerical reads or Alpha certification.

Predeclared planted checks: positive interaction coefficients both years and positive net increments over risk/shuffle at82/164bps PASS. Pairednull: neither primary survives the complete audited exploratoryscreen PASS. As additional descriptive evidence,theplantedinteraction passescompleteexploratoryscreen,butthisisnotstatisticalpowerorCourt. No threshold/seed/strength tuning. See bilingual PHASE_B5b reports for definitions,all four candidate account summaries,resources and limitations.

Planted full413.118128s/peakRSS639655936bytes/peakprivatecommit753876992bytes;null full415.527840s/peakRSS656289792bytes/peakprivatecommit769900544bytes. Sequentialprocesses,notadditiveRSS;doesnotcertifyfullmarketresourcebounds. Actual two-phase source/backend/audit results never overwritten.

- Plan SHA-256: `f7d5e608401f2cef9413c119d8dac6c5c75ba92d90fa3c0804af9c08f1562dba`.
- Calibration RESULT SHA-256: `7c91a31af1187dad13adc3e10893b7092d9844f27f941cd39da58e7b30dcf498`.
- Planted account RESULT: `ed235ee38ada643a7985b72e4423ac9d6e2bc1bda287df1536d0313a5e325169`; AUDIT: `905f4182fd420b570b672c991c482577fb4fd4935f5528ff7a2edac0edf5c076`.
- Null account RESULT: `f6561da19865a0805c189f2df6307c3572e62e495d4ed21791af5899242d388d`; AUDIT: `27442ed0c05cded8bed7414b2f0f3ba40e60d2cac0729720aee576cf1cb501a7`.
- Driver/unit11 JUnit: `da1bd1f719ff6078e276a0123d8ef200dd36194bf7d8741ed9b3d8d75a499719`.

All evidence above is ignored under artifacts/flow-response; originalfailed1/5sourceunitJUnit and corrected6pass/1.00s remain. Targeted11passed2.37s adds5orchestration guards and is a subset of finalfullsuite,not additive. B5headf8d58f1cb814ddddac0646317694c6d8a798afbe/CI34080278086 nowverifiedSUCCESS;newheadneedsitsowncheck.

Next: B6market-scaleheadroom/memorywork andfullglobalexclusiveparent/preregistrationlauncher;not another B5b seed search. Noempiricalreservationsuntilready. Keep all frozen gates and original source/targets. Do not reruncompleted sourceexperimentorfulltests merely onheartbeat wake.

## Historical checkpoint: B5 independent audit and resources

**Final full regression: 1306 passed,1 skipped in417.96s.** JUnit1307total/0failures/0errors/1skip,time417.890s. Ruff src/tests/scripts,format of14changed Python files and Git whitespace pass. This includes all final source/model/target/intent/account-summary additions. Session75139completed exit0. B4head3889d1ccb94affbcb1810edc08019624b65af993/CI34077310076 verified SUCCESS; the new B5 head requires its own CI check.

Earlier complete-audit targeted run90passed220.53s(session6493); after extra numerical summary checks,replay25passed2.27s. The targeted90predates those6additional tests; it is not a second final full result. Final1306includes54newtests overB4. Initial source fixture2failed48passed51.92s exposed an English display name containingST; replacing it withExample corrected fixture semantics. Initial67passed167.73s predates the full offline/intent connection. All old/failed/intermediate artifacts remain and are not added to final pass counts.

Immutable ignored evidence:

- `artifacts/flow-response/phase-b5-regression-20260907.xml`, SHA256 `b17b6029cd9b919992c44158994ddb2a1be321db3cd0c6d50f352dcdd507cc8e`.
- `artifacts/flow-response/phase-b5-audit-final-20260907.xml`, SHA256 `2e01552a2036af33fd6fbe2c8291b751e322f1adb19507cd18f651fa47f137f5` (90-test intermediate audit).
- `artifacts/flow-response/probes/b5-320-20260907/RESOURCE_RESULT.json`, SHA256 `5d55e4d2f83d9bf375c1cbf35fb12424581894e8750c5e0a6a64f2c80723e47b`.

Resource process50367/PID37520 completed exit0:320syntheticstocks/550days/176000rows per source; native history189.7065s/cache193.5903s;peakRSS577728512bytes/peakprivatecommit662188032bytes. History107557523bytes,bundles101732413bytes. Actual machine physical34273542144bytes/available16604770304bytes atfinalsample;not future headroom guarantee. Earlier direct command failed import before source generation;explicit local src path fixed it. Resource memoryunit1passed0.31s and is included in full1306. Probe covers history/cache only,not full accounts/audits or full market scaling. No process left running at this checkpoint.

Reproduce full with `python -m pytest -q --tb=short --junitxml=<new-unique-path>`; selected audit tests are `tests/test_flow_response_epoch.py tests/test_flow_response_replay.py tests/test_flow_response_history.py tests/test_flow_response_reference.py tests/test_flow_response_model_audit.py tests/test_response_resources.py`. Synthetic resource command: `python scripts/profile_response_history.py --output artifacts/flow-response/probes/<new-unique-directory> --stocks 320`. Never overwrite or rerun completed evidence solely on heartbeat wakeup. AlphaPai credentials are removed from subprocess environments.

Full offline source/model/target/22account numerical audit now passes on550syntheticdays/80stocks/39040stockresponsefits/14annualmodels. RESULT/nativeSQLite remain byte-identical before/after audit. Order reason text labels and derived blocked_orders are explicitly not independently certified; all key monetary requests/fills/blocks are. Source-file planted/null power,whole-pipeline resource scaling and globally exclusive parent/preregistration-bound production launcher remain pending. No market epoch or new empirical Trial;debt3660,CourtNOT_RUN. See PHASE_B5.zh.md/.en.md for precise boundaries.

## Historical checkpoint: phase B4 / 历史检查点

**62 targeted passed in159.39s;1252 full passed,1 skipped in350.89s.** Full JUnit1253total/0failures/0errors/1skip,time350.749s. Ruff check src/tests/scripts,format check of12new/modifiedPythonfiles and Git whitespace pass. Final sessions22453targeted and29486full completed exit0; no Python test/market process remains. B3headccb88e9b5f69503bb58f5335302a62ec4153a31e/CI34074615494 verified SUCCESS. New B4head CI must be checked independently,not inferred from B3.

Saved ignored immutable artifacts:

- `artifacts/flow-response/phase-b4-regression-20260907.xml`, SHA256 `aad9328de046676a892408f556e8c8ba628dec058d5a38be882d60975becf16c`.
- `artifacts/flow-response/phase-b4-targeted-final-20260907.xml`, SHA256 `6fd1a0429965da01b9246ca8ec6208d4bad459b4d0fd4f98e9bd1b6fbea14316`.

Targeted command: `python -m pytest -q --tb=short tests/test_flow_response_epoch.py tests/test_flow_response_history.py tests/test_flow_response_protocol.py tests/test_flow_response_shared_fit.py tests/test_flow_response_replay.py --junitxml=<new-unique-path>`. Full: `python -m pytest -q --tb=short --junitxml=<new-unique-path>`. Child test environments exclude AlphaPai credentials. Do not overwrite existing evidence.

There are48new tests relative to B3. Earlier targeted35passed and initial cache-inclusive55passed are superseded,not added together. First epoch test run1failed/6passed in112.94s exposed a test-only nonexistent SQL column after the backend completed; it now reads native fit_lineage. `phase-b4-epoch-initial-20260907.xml` and `phase-b4-targeted-initial-20260907.xml` remain. Final full and targeted runs both confirm the550session/80stock/488bundle synthetic epoch,14actualsupervisedfiles/28bindings,23nativecompletedresults and22cost/controlaccounts.

JUnit properties independently record synthetic history26,009,973bytes,bundles25,935,534bytes. Original anchor bytes and bothcost target equality checked. Account cash/holdings/cost/NAV reconciliation passes,not complete independent source/model/label/target audit. Full source-level planted/null/resource scaling/production claim/preregistration are pending. Real source numerical reads0,newempiricalTrials0,debt3660; market backtest/Court NOT_RUN. Manifest row-count/date metadata only was inspected for scaling;2021numericwarmup and2025/26remainexcluded. See PHASE_B4.zh.md/.en.md.

## Historical checkpoint: phase B3 / 历史检查点

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
