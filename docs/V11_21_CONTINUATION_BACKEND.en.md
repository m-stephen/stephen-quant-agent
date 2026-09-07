# V11.21 frozen-model continuation: B18 engineering status

As of 2026-09-07, this increment has only synthetic development evidence. No new market experiment was executed and no usable Alpha is claimed. The actual cumulative Trial lower bound remains **3707**.

## Implemented

- `flow_response_continuation.py` reserves all22 native account Trials before reading inherited models/data.
- The original read-only registry, frozen history,14 annual models and28 cost bindings are inherited. Production models are not refitted and no new fit records are fabricated.
- Prediction still passes the original registry's timing/lineage guards. Saved targets must agree; the two original anchors retain their exact bytes.
- All candidates and controls at both costs are run, each account independently reconciled. Failures retain every reservation and failure artifact; same-operation retries are rejected.
- New snapshots bind inherited evidence and consumed failures. Original native database bytes remain unchanged.
- Even complete output is `COMPLETE_PENDING_INDEPENDENT_AUDIT`, not an Alpha Court pass.

## Synthetic tests

- Continuation boundary tests:12 passed.
- Complete history generation, frozen continuation and original audits:14 passed in210.08s.
- The continuation actually generated22 synthetic accounts. Metrics, account audits and compact-account SHA-256 matched the original synthetic run. Production fitting functions were poisoned to reject any call.
- CI result-checker:11 passed; Ruff passed.
- The earlier Windows native-crash reproduction group:34 passed in162.71s. This does not establish that the Linux fault is fixed.

## CI failure and fixed comparison

[Original CI](https://github.com/m-stephen/stephen-quant-agent/actions/runs/34118784744) received SIGSEGV inside the complete synthetic account test and did not finish JUnit output.
[GDB diagnostics](https://github.com/m-stephen/stephen-quant-agent/actions/runs/34120458298) caught another SIGSEGV, with native frames including `PyObject_Hash`, `tuplehash`, and `_PyDict_LoadGlobal`, immediately following the120-second traceback dump.

This is not an ordinary assertion failure; the specific cause remains unproven. Diagnostics preserve nonzero status, native stacks and resource logs. Missing or failing JUnit cannot be reported as success.

The next fixed comparison consists of Python3.10/trace120, Python3.10/trace0, and Python3.12/trace120. Every group runs the same full suite, with the original group still required. Disabling scheduled stack printing does not skip assertions or disable fatal-fault detection. No runtime migration can be justified by unfinished results.

## Pending: real execution is not enabled

1. A continuation-specific independent source → feature → mature-label/model → target → order/cash/NAV audit.
2. A launcher pinning actual code, consumed failures, B17 evidence and inputs, with a shared atomic claim, verified GitHub preregistration and bounded child processes.
3. Local tests and CI for that complete version.
4. Only then may one preregistered real22-account continuation consume debt3707→3729. **Those22 real Trials have not been reserved.**

Keep failed operations and B17's original UNRESOLVED status immutable. Candidates, costs, screening and Court thresholds stay frozen. No2025–2026 tuning, main merge, trading or new data purchase.
