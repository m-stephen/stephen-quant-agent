# V11.2 Candidate Nursery specification

Status: **FROZEN FOR IMPLEMENTATION**  
Issue: [#175](https://github.com/m-stephen/stephen-quant-agent/issues/175)  
Spec version: `11.2.0`  
Normative contract SHA-256: `09d5e702580c534c425581a24e06592df908d5fb1cb6610d85e4cef40517dd68`

The hash is computed from `SPEC_CONTRACT` in
`stephen_quant.workflows.v112_candidate_nursery` using canonical sorted JSON. Business artifacts
must cite it. This document explains that machine contract; JSON is authoritative and Chinese and
English reports are renderings of the same object.

## Scope

V11.2 builds a machine-readable Candidate Nursery, migrates the exact frozen V11 prospective
protocol, establishes a trusted first-seen observation clock, and prepares at most one orthogonal
information domain without return labels. It performs no historical search and cannot emit
`VALIDATED_ALPHA`.

The raw disclosed Trial baseline is `770`. V11 and V11.1 evidence remains development-only and
immutable. V11.1 adds no forward candidate.

## Orthogonal state model

The result contains four independent fields:

- `candidate_state`: nursery readiness and per-candidate research eligibility;
- `forward_stage`: coverage, day-25 runtime, day-126 descriptive, day-252 evidence or rejection;
- `orthogonal_data_state`: not ready or ready for a future preregistration;
- `run_status`: completed or failed closed.

Completing a run never implies candidate validation. Candidate history is append-only and upward
transitions are limited to `RESEARCH_CLUE -> FORWARD_CONFIRMATION_CANDIDATE -> VALIDATED_ALPHA`.
Terminal rejection and specification-dependent states cannot move upward. V11.2 prohibits the
last transition.

## Frozen protocol migration

`configs/v11-forward-protocol.freeze.json` is the byte-for-byte frozen valid V11 protocol artifact.
Its embedded semantic protocol hash is
`71ba4f198f2f3dcbc4877d684f5a5fd8023d806a469e2d2a482ead4174a77106`; its raw artifact hash is
checked separately. V11.2 never rewrites or reserializes that artifact. The migration wrapper
separates the frozen protocol code version from the current runner version.

The only forward candidates are the exact V10.1 intraday-liquidity and V10.3 closing-volume/chip
fingerprints in that artifact. Candidate formula, direction, holding period, Top-40 portfolio,
ten-name buffer, CNY 3m capital, 41/82 bps costs and five-percent participation remain frozen.

## Trusted first-seen clock

A clock manifest freezes a UTC `ingestion_clock_genesis`, collector identity/version, host clock
source and `Asia/Shanghai` market timezone. Local file mtime, ctime, directory date and later scan
time are never arrival evidence.

- Observations before genesis or on/before the protocol boundary are
  `PREEXISTING_UNVERIFIED_ARRIVAL`.
- A record first observed by the controlled collector after genesis and no later than its explicit
  decision cutoff is `FIRST_SEEN_ACTIONABLE`.
- Later arrivals are `LATE_NOT_ACTIONABLE`.
- Revisions are append-only `REVISION_QA_ONLY` events and cannot rewrite first-seen signals.
- Duplicate and overwrite attempts fail closed in the receipt ledger.

Each receipt binds event, ingest, collector start/completion, decision cutoff, payload hash,
revision identity and the previous receipt hash.

## Calendars and checkpoints

Each candidate has a coverage/actionability calendar based on its own frozen required sources. The
family primary calendar is the intersection of both candidate calendars. Returns cannot select or
change either calendar.

- fewer than 25 family actionable dates: `ACTIONABLE_DATES_INSUFFICIENT`;
- day 25: runtime integrity only;
- day 126: frozen descriptive fields only, with no p-value or promotion advice;
- day 252: the runtime first emits `FORWARD_PRIMARY_EVIDENCE_REQUIRED`; only the separately
  implemented frozen primary estimator may turn this into immutable `primary_forward_evidence`,
  `FORWARD_REJECTED`, or at most `FORWARD_CONFIRMED_PENDING_FINAL_COURT`. Date coverage alone can
  never imply confirmation.

## Frozen day-252 inference

The estimand is long-only Top-40 minus the contemporaneous investable dynamic-universe equal-weight
benchmark, under the frozen V10 stateful execution and missing-data contract. Standard and double
round-trip costs are 41 and 82 bps.

The primary family contains exactly the two frozen hypotheses. Day-252 multiplicity uses Holm at
alpha 0.05. Uncertainty uses HAC lag 19 with a predeclared block-bootstrap fallback of block length
20. The minimum family actionable sample is 252 dates.

Historical Trial/DSR/PBO stays visible as selection-risk provenance. When no prospective
configuration selection occurs, prospective PBO is `NOT_APPLICABLE`. A future, separately approved
Final Alpha Court decides validation; V11.2 does not.

## Orthogonal label-free data preparation

Priority is announcement/expectation surprise, share-supply/corporate-action shocks, then
within-industry relative mechanisms. Authorization/update sustainability, stable IDs,
deterministic deduplication, PIT/revision semantics, replayable raw SHA-256 snapshots and physical
absence of label interfaces are non-compensating gates. Only after passing them may coverage,
missingness, delay and revision completeness be compared. A failed higher-priority domain leaves an
immutable reason before the next is considered.

This stage may propose a future hypothesis, negative control, horizon and Trial budget, but reads no
returns, prices or IC and adds zero inferential Trials.

## Atomic evidence

`content_hash` covers deterministic business content and excludes timestamps and operation IDs.
`run_envelope_hash` binds operation ID, UTC creation time, runner version and content hash. Output
uses exclusive operation directories and fsync plus atomic replace. Partial failed artifacts are
not canonical Nursery state and retries cannot overwrite an earlier operation.

Semantic changes require a new spec version and a `supersedes` chain. Editorial changes must state
whether the canonical machine contract hash changed.

## Non-goals

No historical label search, sealed-window access, backfill, sign reversal, adjacent mutation,
automatic combination, deep learning, RL, live trading authorization or promise of Alpha discovery.
