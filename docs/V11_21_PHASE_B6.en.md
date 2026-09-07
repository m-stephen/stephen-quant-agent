# V11.21 B6: Lower-copy storage and resource verification

## Conclusion

Lower-copy decoding and chunked canonical hashing passed content checks at both fixed synthetic sizes. The large file contains 2,534,755,919 bytes, 4,003,840 bars and 3,686,400 rank rows. The new path completed; the legacy path was stopped by the predeclared 10 GiB private-commit guard. **This is storage engineering evidence, not full-pipeline headroom certification or market Alpha.**

Empirical Trial delta is zero; historical debt remains 3660. No new market numeric read, changed candidate/cost/gate, or rerun of B5b models/accounts occurred.

## Measurement definitions and results

Each case ran sequentially in its own Windows child process on a fixed file derived from the same synthetic source. Private commit and RSS are kernel-reported lifetime process peaks; GiB = 1,073,741,824 bytes. Elapsed time includes child startup and file-hash preflight, but excludes parent fixture construction. These are single observations, not repeated-run averages or confidence intervals.

| Size and path | Peak private GiB | Peak RSS GiB | Elapsed seconds | Outcome |
|---|---:|---:|---:|---|
| 1x legacy | 0.484112 | 0.491074 | 3.441546 | Complete |
| 1x lower-copy | 0.298965 | 0.306015 | 6.869375 | Complete, identical hash |
| 32x legacy | 10.042259 | 10.030937 | 26.081035 | Memory guard stopped it, incomplete |
| 32x lower-copy | 8.660313 | 8.651581 | 204.270306 | Complete, identical hash |

At the small size, private commit fell about 38.24%, but elapsed time roughly doubled. The large legacy case's 26.08 seconds is **time to termination**, not a comparable completion time. Its 10.04 GiB is the observed peak before termination, not its hypothetical full-run peak. The new large case has only about 1.34 GiB below the guard; source/model/account coexistence could still exceed it.

## Changes and invariants

- Numeric source rows use `fetchmany(2048)`, avoiding simultaneous full tuple and dict matrices; selected rows are still retained in memory.
- Text-stream JSON decoding freezes containers bottom-up, removing a separate whole-tree immutable copy. Standard-library JSON still loads a whole document, not a bounded streaming parser.
- Large training-prefix SHA-256 uses chunked canonical encoding matching the legacy bytes. The largest scalar token or mapping sort can still allocate memory.
- Historical construction releases obsolete observation/risk matrices and replaces bar objects one day at a time. Temporary training bars are released after label-pair construction.
- Each immutable year's identical prefix is hashed once. Every fit still verifies current native sources, actual history bytes and all model bundles before cache use; memoized content is not cached authorization.
- The independent model audit also hashes once per year, while retaining its independently constructed labels, solver and target reconstruction.

## Predeclared resource guards

The resource plan bound all four size/path cases, source hash and actual driver/storage/measurement code bytes before execution. The supervisor samples only its own child every 0.2 seconds and terminates it at private commit >=10 GiB, physical availability <4 GiB, unavailable measurement, or 1200 seconds. It retains receipts and does not inspect or kill arbitrary processes.

Polling can overshoot; this is **not an OS-enforced hard limit**. The large legacy case exercised this failure branch in practice. Replicated, renamed synthetic identifiers only enlarge a storage fixture; they are not independent stocks or statistical observations. About 2.61 GB of generated fixtures plus failure logs remain in ignored artifacts; no raw data or prior evidence was removed or overwritten.

## Tests and evidence

Final targeted tests: 41 passed, 1 skipped in57.45 seconds. The skip is the platform-inapplicable resource branch. See the latest `V11_21_VERIFICATION.md` entry for the final complete regression.

Checks cover Unicode, float extremes, signed zero, nesting/large strings, legacy nonfinite-token compatibility, ordinary immutable-container mutations, malformed JSON, prefix memoization, changed-source rejection, owned-child measurement, memory/availability/unavailable-measurement guards. Hash compatibility does not authorize NaN in numerical computation; finite-value gates remain unchanged.

- Plan: `artifacts/flow-response/resources/b6-storage-001/RESOURCE_PLAN.json`, SHA-256 `6419a5b42dd158a00b22635bc57c52a1e9e9b72a18c637247eee8c561c7a5b68`.
- Result: same directory, `RESOURCE_RESULT.json`, SHA-256 `2676b939000f515b2a57cadb1b6f69f2822e81945dbaa80660dabe9e3eb49b8f`.
- Small fixture: `372c645e7db7638a3a0dc8966f7d52c48ffc7cc2e933f29f5758e85a11ce6f38`; large fixture: `fbdfb569b6fb32c15c19019205792815c657beac869f39ce6bb76e901860f477`.
- Targeted JUnit: `phase-b6-final-targeted-20260907.xml`, SHA-256 `551033ea6bf63ea8afe1012669b623c8cf6adceb9e822ef8b8001cdb30919046`.

## Next steps and unresolved questions

The storage benchmark is complete; do not rerun it on a heartbeat. Next finish the single production entrypoint and end-to-end resource lifecycle: bind actual parent results/audits/registry, source/original-target/code/auditor hashes and Issue #184 preregistration. A global exclusive claim must precede the full 23 empirical reservations and all numeric reads. Avoid retaining production history alongside independent audit copies or duplicate account sessions; retain failed reservations and artifacts.

Only the original frozen2022–2024 daily/flow sources remain in scope. No numeric2021 warmup,2025/2026 or new warehouse sources. Complete those checks before the one bounded empirical run; report every registered control and both costs. Freeze and deeply falsify any complete exploratory survivor; otherwise use an explicit failure diagnosis to justify a new finite plan.

End-to-end peak resources and runtime remain unmeasured. DSR >=0.95, PBO <=0.05, placebo <=0.05, historical Trials, independent fresh evidence and broker-execution requirements remain unchanged. Reused development windows do not become independent OOS evidence.
