# V11.21 frozen-model continuation: B19 independent audit

Date: 2026-09-07. **This is software development and synthetic testing, not a new market backtest or usable-Alpha certification. The actual cumulative Trial lower bound remains 3707.**

## Implemented audit chain

`audit_complete_continuation` verifies all22 new accounts read-only. It does not execute accounts, call production fitting/selection, or modify old databases, failed outcomes or the new RESULT.

1. Before inherited numerical reads, verify22 unique native Trials, complete results, one experiment, code/snapshot bindings, zero new fits and hypothetical debt3707+22. Reject missing controls, premature statistical claims or partial results.
2. Verify the old database/history,14 annual models and28 actual two-cost fit bindings. A failed inherited epoch does not need a fabricated completed RESULT.
3. Independently scan frozen daily/flow sources and reconstruct support, past-visible prices/capacity/risk/response features and cross-sectional ranks.
4. Independently rebuild mature labels/pairs, check ridge weights with augmented least-squares SVD, then reconstruct all nine generated target sets. Previously saved targets must agree; both original anchors retain their exact bytes.
5. Reconstruct order intent, fees, capacity, shares, cash, NAV and annual metrics for all22 accounts. Reconcile full reports, compact paths and native outcomes, including daily returns, dates, profit and execution summaries. Self-consistent hashes alone cannot validate false cash or positions.
6. Recheck inherited files and new RESULT/spec/database bytes at completion. Return an independently screened result separately, without changing the original unaudited output.

The numerical audit stages share one native-verified immutable history decode, not a caller-supplied matrix. This removes repeated full-history copies; it is not an empirical memory-bound measurement.

## Tests and retained failures

The preceding `b58f5c2` commit completed [CI34122881453](https://github.com/m-stephen/stephen-quant-agent/actions/runs/34122881453):

| Group | Result | Seconds |
|---|---|---:|
| Python3.10.21 / trace120 |1494 passed,2 skipped|522.22|
| Python3.10.21 / trace0 |1494 passed,2 skipped|537.94|
| Python3.12.14 / trace120 |1494 passed,2 skipped|439.09|

Every JUnit completion check and Ruff check passed. The3.10/trace120 group actually emitted a120-second dump during the complete synthetic epoch and subsequently completed. The3.12 score-hash failure did not recur. Both earlier SIGSEGV failures remain evidence of an unproven root cause; one success does not establish a permanent fix.

Intermediate B19 development run:33 passed,1 failed in246.10s. The failure occurred when a fixture tried to update an append-only fit contract and its native trigger correctly refused. The fixture now first asserts this protection, then simulates corruption only in a copied synthetic temporary database to test the offline audit too. This intermediate batch is not complete verification of the final source.

Final local full-suite and new-CI results must be supplied by subsequent actual runs. The previous commit's CI is not evidence that the new audit version has already passed.

The full local `cad54e3` batch produced **1520 passed,4 failed,2 skipped in637.55s**. The new continuation audit/adversarial tests passed. All four failures were legacy source-audit tests whose `read_verified_history` module entry point was removed by the refactor, preventing their forged-source injection from running. This is a compatibility regression, not four accepted forgeries. The correction restores the original no-cache reader and retains the immutable-cache path as an explicit option. Keep all four assertions and retest; no comparison is weakened. The new commit still requires its own CI evidence.

After correction, source/history tests: **28 passed in85.00s**, including rejection of all four forged support-evidence cases. The JUnit completion check and Ruff passed. This set overlaps the full suite; counts must not be added or reported as complete new-CI verification.

## Still not enabled

- The empirical launcher still needs actual code/input/two failed operations/B17 original diagnostic and append-only explanation pins, verified GitHub preregistration, a shared exclusive claim, all22 reservations before numerical work, and separate bounded producer/auditor children.
- No new real claim was consumed; actual debt has not increased to3729.
- Statistical Court is NOT_RUN. Numerical reproducibility is not DSR/PBO/placebo, live-execution or independent-new-sample certification.
- Reused2023–2024 history remains development data. No2025–2026 tuning, main merge or trading.

Engineering evidence is shareable with these caveats. A usable-Alpha conclusion still lacks complete empirical/statistical validation. Chinese and English versions state the same boundaries.
