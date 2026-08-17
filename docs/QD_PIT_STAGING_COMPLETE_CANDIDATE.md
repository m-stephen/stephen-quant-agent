# QD PIT Staging Candidate

## Status

This candidate targets `data-test` only. It does not promote 2025 or 2026 into Research, does not
change the default data source, and does not permit performance feedback or factor tuning.

## Local maintenance evidence

- 2025 frozen manifest: `0f9d1b2de6fb4fed1fbd81a3b4eaf83741ac78dfc35cca358f8ebb671fca29e6`
- 2026 frozen manifest: `ed984ff75a080df20114e26bf54079b9d7185f7ad1b7f426649cadf64f4667a9`
- Both years completed independent Inventory, Unlock, and Manifest-bound Maintain operations.
- Every operation reported `inferential_trial_delta = 0`.
- Manifests, ledgers, raw data, and machine paths remain outside Git.

The hashes above identify local control artifacts; they do not expose source paths or content and
do not make either year formally research eligible.

## PIT contracts

`FinancialVisibility` requires:

- code and report period/type;
- announcement and actual publish timestamps with timezone;
- revision ID;
- source document ID and SHA-256.

Financial revisions become visible only after both announcement and actual publication boundaries.
Duplicate revisions, publication before announcement, and publication before the report period ends
fail closed.

`IndustryMembershipPIT` requires an industry system/level/code/name, an effective interval, and a
source. Overlapping intervals for the same instrument/system/level fail closed. Daily Shenwan index
quotes are not treated as historical stock constituent mappings.

## Admission policy

- `A`: hashed daily OHLCV, same-day valuation snapshots, and public daily microstructure fields,
  usable only after the declared close/next-session boundary.
- `B`: security master changes, financial snapshots, and stock-industry membership. These require
  effective or publication metadata before formal use.
- `C`: attention/hotness and opaque vendor technical fields. These remain candidate-only and cannot
  enter formal Alpha acceptance.

The default contract sets `formal_research_eligible = false` for this complete staging package.

## AlphaPai evidence and remaining gap

The configured AlphaPai endpoint was used for read-only A-share financial-announcement metadata
collection. Raw responses and normalized bundles remain in gitignored local artifacts.

- 2025: 5,871 normalized visibility rows; bundle SHA-256
  `cc0d961ceb4585600917774177d48457176ea74fc642cabdbf323f71258295fe`.
- 2026 through the conservative `2026-08-16` cutoff: 6,351 normalized visibility rows from 82
  frozen source pages; bundle SHA-256
  `60fc4b468e664c9a458138f09ee11c0a74c25293cc0c0cf7213906dc82d58814`.
- Both batches have `inferential_trial_delta = 0` and `formal_research_eligible = false`.
- A wider 2026 year-end query was rejected because its availability time exceeded ingestion time.
- Long-window offset pagination exposed source drift and duplicate page boundaries. The accepted
  2026 snapshot uses progressively narrowed month/week/day partitions and requires stable page
  count, total size, continuous page numbers, zero duplicate revision keys, and deterministic replay.
- Transient AlphaPai announcement IDs are excluded from durable records. Content-derived document
  and revision IDs, source-page hashes, byte sizes, partitions, query bounds, parser version, and
  fixed ingestion time are retained in the local evidence bundle.

The repository command `scripts/build_alphapai_pit_bundle.py` rebuilds a candidate bundle from a
gitignored local configuration containing explicit source pages and output location. Missing
credentials still produce an explicit `not_run_missing_credentials` ledger state rather than
fabricated data.

Each build configuration must provide a unique `operation_id`. The builder creates that operation
directory exclusively, never overwrites an existing snapshot, binds manifest page numbers to the
API envelope rather than config ordering, and rejects output beneath any source-page directory.

## Remaining promotion gates

- download and hash source documents for records whose metadata alone is insufficient to prove a
  financial value or revision;
- acquire genuine historical stock-industry constituent intervals rather than infer them from index
  quotes;
- populate corporate actions from authoritative documents; the contract, revision gates, and PIT
  market-cap constructor are implemented, but no event is fabricated from adjustment factors;
- rerun leakage/provenance gates on normalized local staging artifacts;
- obtain core review and explicit promotion approval before changing Research or `main`.
