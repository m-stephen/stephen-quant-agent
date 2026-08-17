# V2.6 failed-validation release audit

## Release classification

- Package version: 2.6.0
- Classification: `negative-validation-evidence`
- Engineering conclusion: pass
- Alpha conclusion: `VALIDATION_FAIL_STOP`
- Autonomous live trading: disabled and unauthorized
- 2026 final test: remains sealed

## Audit evidence

- GitHub Issue #64 froze the policy, data window, trial budget and acceptance gates before
  the 2025 result was read.
- Data readiness passed before the formal trial.
- Exactly one inferential trial was added, for 48 cumulative trials; a retry was rejected.
- The structured report records the point-in-time universe, costs, capacity and latest input.
- PBO was not falsely reset by a single-policy validation; the historical warning remains.
- JSON and bilingual results pass SHA-256 offline-manifest replay.
- No 2026 data was accessed and the final test was not opened.

## Release boundary

V2.6 publishes trustworthy negative evidence and reusable one-shot validation infrastructure.
It does not mean the policy passed, does not allow rerun selection or post-hoc optimization on
2025, and does not authorize trading. Only a new research epoch may follow.
