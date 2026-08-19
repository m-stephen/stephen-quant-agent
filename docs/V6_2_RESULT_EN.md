# V6.2 Test Result: Automatic Alpha Court

Decision: `READY_FOR_FROZEN_PROTOCOL`

There is no new unseen sealed window and no formal candidate in this run, so V6.2 does not fabricate
a Court PASS. It validates the generic adjudication protocol and adds zero Trials.

Tests require every gate for PASS, return FAIL on any gate, prohibit DSR below 0.95 or PBO/placebo
above 0.05, reject mismatched candidate/snapshot/window/protocol evidence, and prevent research-only
evidence from impersonating the one-time sealed scope.
