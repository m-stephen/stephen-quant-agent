# V11.21: CI timeout diagnostics recovery

## Findings and limits

On September 7, 2026, run34089011614 / job101638545074 was cancelled. The approved-host REST check annotation explicitly states that the configured 40-minute job limit was exceeded. The job spans06:01:09Z–06:46:10Z including termination. Its actual runner label is ubuntu-24.04, so this is not B7's ubuntu-slim 15-minute hard limit.

Connector log download returned BlobNotFound; CLI also returned log not found. The slow test or dependency therefore remains unknown. Local1399passed/2skipped does not establish remote success. No empirical launch, claim or new Trial exists; the inherited lower bound remains3660.

## Changes

- Keep every test and assertion, with no filtering, new skips, automatic retry or continue-on-error.
- Record individual test names,25slowest durations,120-second hanging-test stacks and JUnit; tee output to a diagnostic log.
- Bound the test step at45minutes and the job at60minutes, reserving time for diagnostic upload after step failure. Upload or runner failures can still prevent artifact preservation.
- Bound BLAS/OpenMP threads to1 in CI only. This controls possible nested contention; it is not proof that contention caused the timeout and does not change the local empirical resource contract.
- Upload only CI-generated synthetic-test logs, package configuration and JUnit with7-day retention. Do not upload local market data, configuration, experimental databases or secrets.

NumPy documents multithreaded BLAS backends and backend-dependent thread controls.[NumPy](https://numpy.org/doc/stable/reference/global_state.html)
GitHub documents step-level timeouts and workflow artifacts.[Workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax),[artifact upload](https://github.com/actions/upload-artifact)

## Plan and continuation

Only CI and documentation change; numerical code, tests, research contract and prior evidence remain unchanged. Preserve launch-plan-001.json bound to ff7421b. It cannot authorize a new commit. Verify the new commit's CI first; then prepare a separate launch-plan-002.json and publish its complete new hash-bound preregistration on Issue184, explicitly superseding the unconsumed old plan. This is not a replay of a consumed experiment; none has started.

If the new CI fails, use its logs/stacks to diagnose the actual test, rather than repeatedly raising timeouts or bypassing remote validation with local success. This checkpoint makes no new market-return, power or Alpha claim.
