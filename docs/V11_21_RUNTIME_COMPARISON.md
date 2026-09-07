# B18 runtime comparison / 运行环境对照

Latest verification: `b58f5c2` completed all three groups in CI34122881453, each1494 passed/2 skipped. The original3.10/trace120 group emitted its120-second dump and continued successfully. Details and retained limitations: [B19 English](V11_21_CONTINUATION_AUDIT.en.md) / [B19 中文](V11_21_CONTINUATION_AUDIT.zh.md). The earlier failures below remain immutable evidence; their root cause is not proven.

Date / 日期: 2026-09-07. Engineering-only synthetic evidence; no new market Trial, no Alpha claim. 本文只记录合成工程测试，真实 Trial 下界仍为3707。

## Native crash / 原生崩溃

- `fec262e`, CI34118784744: SIGSEGV / exit139 after a120-second traceback; no complete JUnit.
- `00f000b`, CI34120458298: GDB caught another SIGSEGV immediately following a120-second traceback. Native frames included `PyObject_Hash`, `tuplehash`, `_PyDict_LoadGlobal`. GDB's stopped-child status255 remained a failure. Ruff passed.
- Neither stack establishes the original memory-corruption cause. The traceback timer is a hypothesis, not a proven sole cause. Do not treat successful repetitions as erasing either failure.
- 两次原生故障均保留；具体根因未定位。定时栈输出可能相关，但不能据此认定是唯一原因，也不能把后续成功当作原故障不存在。

## Fixed comparison / 固定对照

[CI34121374556](https://github.com/m-stephen/stephen-quant-agent/actions/runs/34121374556), commit`6ab2d85`, same complete suite in all groups:

| Environment / 环境 | Actual result / 实际结果 | Seconds / 秒 |
|---|---|---:|
| Python3.10, trace120 |1480 passed,2 skipped; JUnit checker and Ruff PASS|357.96|
| Python3.10, trace0 |1480 passed,2 skipped; JUnit checker and Ruff PASS|477.66|
| Python3.12, trace120 |1478 passed,2 skipped,1 failed,1 error; Ruff PASS|292.77|

The whole workflow failed. The successful3.10/trace120 log did not contain a timeout dump, so it did not exercise the previously observed timing boundary. Timing differences are not a controlled performance benchmark.

整个工作流仍为失败。成功的3.10/trace120日志未出现超时栈输出，不能据此排除相关故障。耗时也不能直接作为严谨的性能比较。

## Separate score-summation compatibility defect / 独立的分数累加兼容性缺陷

The3.12 failure was a strict `diagnostics:response.scores_sha256` mismatch, not a native crash. Production used built-in `sum`; the independent reference used sequential float addition. [Python3.12 changed float summation](https://docs.python.org/3/library/functions.html#sum).

A pure synthetic cancellation input `[1e16,1,-1e16]` was evaluated with the current predictor on two installed interpreters: Python3.10.9 returned0.0 and Python3.12.14 returned1.0. The original sequential-reference result is0.0. This supports making the original3.10 accumulation order explicit; it does not explain the earlier SIGSEGV.

3.12的失败是分数哈希不一致，不是段错误。两种解释器上的纯合成抵消例子确认了内置`sum`行为变化；修复应显式保留原3.10累加顺序，不放宽哈希或数值门槛。这并不构成旧段错误的根因解释。

Any resulting change needs its own tests and new CI. This document does not certify a fix, change the empirical interpreter, consume a Trial or revise frozen models/results. 后续修复必须单独验证；本文不声明修复通过、不迁移实证运行环境、不计入新市场试验、不修改冻结模型和结果。

## Implemented correction and test scope / 已实现修正与测试范围

Production prediction now explicitly accumulates products left-to-right, preserving the existing3.10/reference semantics. The independent implementation, exact score-hash comparison, model weights, selector and tolerances were not relaxed.

- Full local suite on preceding backend commit`ac6b043`:1493 passed,2 skipped in595.24s; this preceded the summation change.
- Predictor tests after the summation change:24 passed in0.81s on Python3.10.9.
- Python3.12.14: the manual synthetic cancellation regression passed, returning exact positive0.0. The bundled runtime lacks pytest; a local3.12 pytest invocation could not run and is **not** reported as passing. Full3.12 verification remains the CI group's responsibility.
- Ruff passed. A new full CI must verify the final commit; these checks do not prove the earlier intermittent native crash fixed.

预测实现已显式固定逐项累加；独立参考实现、模型权重、选择器、严格分数哈希和容差保持不变。上一份后端提交的本机全量测试1493通过、2跳过，不冒充最新累加修正后的全量测试。修正后3.10定向24项通过，3.12只完成手动纯合成回归；其本机pytest不可用，完整验证由CI继续执行。真实Trial仍为3707。
