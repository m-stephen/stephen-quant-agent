# V11.21 phase B1: shared feature fits and historical series

## Decision

Three engineering foundations for the next bounded research epoch are implemented and regression-tested. **No market experiment was run; no new Alpha was discovered or certified.** V11.21 remains incomplete, PR199 remains Draft, the package remains11.20.0, and historical empirical Trial debt remains3660.

V11.20's negative conclusion is unchanged: before costs, the full models still underperformed their matched risk controls. Costs alone do not explain that failure. This phase changes representation and traceability, not the number of attempts or acceptance thresholds.

## Implemented scope

| Component | Implemented | Not established |
|---|---|---|
| `integrity/feature_sources.py` | Predeclared shared providers and consumers; native model/result evidence; append-only edges | No new authorization system; no historical Trial ID changes |
| `discovery/flow_response_series.py` | Explicit calendar, in-memory daily/flow join, per-day multi-stock bundles, native label-free fit records | No real Parquet reader or empirical runner yet |
| `mechanism_inventory.freeze_lineage_packet` | Finite canonical policy deduplication, merged legacy IDs and explicit family/policy/legacy tombstone rejection | Not yet wired into the empirical workflow; old packets/generators unchanged |

### Separate feature estimation from return prediction

One predeclared provider Trial owns all daily label-free bundles. Each stock uses exactly60 contiguous global sessions strictly before the signal, with fixed ridge0.01. Candidates and cost variants share these bundles; each consumer still owns its supervised fit or explicit no-fit contract.

All provider/consumer declarations precede any related fit. Binding requires the provider's completed result to identify its exact native fit lineage. Missing bindings block consumer fit registration, result completion and current-value access through the guarded feature entry point. Registration guards cannot retroactively constrain arbitrary calculations performed by a caller; the future runner must check dependencies before actually fitting its supervised model.

The synthetic end-to-end fixture has one provider, two cost consumers and two daily bundles: two native fit rows and two consumer edges, not four duplicated fits. These synthetic Trials exist only in temporary pytest databases, not in the empirical ledger.

### Source and timing rules

- Daily `amount` is converted from thousand CNY to CNY; `net_inflow_amount` is CNY. Their ratio is the flow input.
- Returns use adjacent global-session `close * adjustment_factor` values. Missing sessions are not compressed, and legacy execution/adjustment semantics are not rewritten.
- Observation time is15:00 Shanghai; availability is the maximum relevant daily, flow, previous-close and observation timestamp. Explicit timezones are required.
- This bounded protocol permanently excludes records unavailable by the end of their own signal day, rather than retrospectively backfilling them. Vendor historical availability is not a live first-seen certificate.
- Invalid/missing inputs have explicit exclusion reasons. A stock missing any of60 contiguous observations produces no model. A whole fit day with zero identifiable models must fail and be recorded, never fabricate a successful fit. With valid past models but empty current support, the feature interface returns an empty set; account-level cash behavior still awaits the runner.
- Bundles bind assets, snapshot, observation digests, actual training dates, global indices, calendar windows and actual file bytes. Future-value mutation or calendar extension does not change an earlier model. An independent numerical source-to-model audit is still pending.

## Actual verification

Final local verification on2026-09-07:

- Targeted: **105 passed in5.52s**.
- Full suite: **1146 passed,1 skipped in190.93s**. JUnit totals1147 tests,0 failures,0 errors,1 skipped.
- Ruff `check src tests scripts` passed; format checks passed for six new/dedicated files; `git diff --check` passed. Existing `registry.py` / `fit_lineage.py` were not broadly reformatted; this is not a claim that every inherited file passes the current formatter.
- Tests cover units/adjustment, calendar gaps, availability checks before numeric access, duplicate/orphan keys, future poisoning, calendar-extension invariance, shared fits, failed providers, late declarations, file/model/calendar mutation, append-only lineage, legacy compatibility, renamed duplicates and tombstone bypasses.

A previous full-run terminal result was lost to context-output truncation. After confirming no old pytest process remained, the suite was rerun with persisted evidence. No empirical experiment was duplicated. The gitignored JUnit artifact is `artifacts/flow-response/phase-b1-regression-20260907.xml`, SHA-256 `27a190e4a94e3c87926bf8d8a7b36a8ca4981c96ee5e8dffee8d60fd302b83c0`; targeted evidence is `phase-b1-targeted-20260907.xml`. Total test count is not passed count.

New market numeric reads0; new empirical Trials0; supervised return fit, account backtest and Alpha Court NOT_RUN. No new DSR/PBO/placebo values exist. Phase-A CI34069051824 was verified successful; this phase's remote CI must be checked against its exact commit independently.

## Next phase

1. Wire the frozen daily/flow files with strict scope and byte verification. Do not silently reuse the legacy five-source loader to read auction, chip or minute values. Freeze calendar and coverage rules.
2. Construct features as they were available on each historical training date, then fit mature future-return labels with annual prefix training and purge/embargo. Never backfill an end-of-year model into earlier dates.
3. Preregister a small exact candidate set and complete Trial budget. Same-support controls must address risk, raw flow plus own return, standardized flow plus own return, old absorption and a fixed shuffle. Original stable/low-volatility targets remain unchanged; report their support differences separately.
4. Complete the runner, independent audit, planted/null tests and full preregistration before one exclusive2022–2024 operation. Keep CNY3m,82/164bps, capacity/execution semantics and all previous gates. No2025/2026 reads or main merge.

These control requirements are not an already-frozen empirical budget. Within-family revisions retain negative evidence and debt3660; the representation is neither independent information nor proof of causality. The analysis-validation workflow explicitly separates engineering success, market performance and independent Alpha certification.
