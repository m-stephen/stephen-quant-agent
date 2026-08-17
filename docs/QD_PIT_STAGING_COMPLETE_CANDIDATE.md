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

`ALPHAPAI_API_KEY` and the configured base URL were verified with a minimal read-only 2025
announcement probe for one security. The probe returned five records successfully. This is
connectivity and schema evidence only: it is not full-market coverage, does not establish complete
revision history, and does not promote any record into research. Transient AlphaPai announcement
identifiers are excluded from durable staging identifiers; source-document and revision identifiers
are deterministically derived from hashed content.

Full-market announcement retrieval, source-document collection, and complete revision-chain
coverage remain outstanding. Missing credentials continue to produce an explicit
`not_run_missing_credentials` Remote Retrieval Ledger record rather than fabricated data.

## Remaining promotion gates

- acquire source-backed announcement metadata and revision chains where financial fields are needed;
- acquire genuine historical stock-industry constituent intervals rather than infer them from index
  quotes;
- rerun leakage/provenance gates on normalized local staging artifacts;
- obtain core review and explicit promotion approval before changing Research or `main`.
