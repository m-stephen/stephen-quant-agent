# V12.2 bounded runtime diagnostic / 有限运行环境诊断

## Frozen question / 冻结问题

CI 34164462850, commit 79093b1, Python 3.12.14 / scheduled traceback 120s,
failed with native SIGSEGV in `dump_frame` / `faulthandler_thread` while an old
flow-response test was running. Both Python 3.10 arms passed. Local full regression:
1806 passed, 2 skipped. This is not a failed statistical assertion and does not
establish the underlying memory fault's cause. Preserve the failure permanently.

此次失败是原生崩溃，不是统计断言失败；堆栈所在位置不能证明根因。
不得通过重复运行直到变绿或跳过测试来消除该证据。

## Once-only comparison / 一次性对照

Independent reviewer agreed before implementation (PR205 comment5576105416):

- One manually dispatched Python3.12.14 full regression with scheduled dump0.
  Keep all assertions, GDB return-code propagation, completed JUnit check, and
  external45-minute step timeout. Fatal signal handling remains enabled.
- Pin observed NumPy2.5.3, DuckDB1.5.5, pytest9.1.1, Ruff0.16.6, pytz2026.3.post1
  and observed pytest dependencies. Record all resolved packages, interpreter
  and libpython raw-byte hashes, build/configuration, Python-VV, GDB info files.
  A version tag alone does not establish debug-symbol/source-build identity.
- Exactly12 owned synthetic processes: Python frame switching / NumPy variance
  crossed with timer0 / repeating0.05s;3 replicates per cell,5 seconds each.
  Imports precede timer activation. External15-second child timeout; no retries,
  no adaptive repeats. Record actual dump count, exit status, completion marker,
  elapsed time, stdout/stderr hashes, failures and timeouts.
- Run full regression even when a microprobe fails; preserve both outcomes.
  The diagnostic job remains failed when any probe crashes/fails its contract.
- Exclusive local output directory prevents overwriting a diagnostic. The agent
  records the single dispatch commit/runID in STATE before any further dispatch;
  CI dispatch itself is not a global once-only authorization service. A GitHub
  rerun or additional dispatch requires fresh reviewer agreement, not auto-retry.
- Original three regular CI arms, including required Python3.10/trace120, remain.
  Manual diagnostic concurrency is separate so it cannot cancel regular CI.

固定12个合成进程和一次完整回归；所有失败均保留。诊断模式不改变常规三组CI，
不接触真实市场数据、不增加真实研究Trial、不授权运行市场因子。

## Interpretation fixed before results / 预先固定判读

1. Trace0 full suite also crashes: investigate broader native-runtime memory
   behavior; cannot attribute failure solely to the scheduled dumper.
2. Timer-on microprobes crash while timer-off controls and trace0 suite pass:
   supports a reviewed operational mitigation, not a permanent root-cause fix.
3. Everything passes: failure was not reproduced. Retain original failed run;
   do not infer the race is fixed or run additional probes to obtain significance.
4. Timeout, missing evidence or incomplete suite: inconclusive, no release gate.

两位Agent复核证据后才能决定是否调整CI诊断方式。统计、成本、容量、泄漏和
失败关闭规则不变。工程通过不等于发现Alpha。真实V12.2运行计划仍需独立审批。

## Primary references / 官方资料

- [CPython faulthandler](https://docs.python.org/3.12/library/faulthandler.html)
- [GitHub manual dispatch](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)

No claim that a similarly named upstream crash is the same defect.
