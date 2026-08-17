# QD authoritative PIT source candidate

This candidate closes the implementation gap between AlphaPai announcement metadata and verified
source bytes. It does not claim that unavailable data has been found and it does not promote data
to the formal Research layer.

## Inputs

- A gitignored local configuration based on `configs/authoritative-pit-sources.example.json`.
- Original SSE/SZSE announcement bytes for financial or corporate-action evidence.
- A licensed or otherwise authoritative stock-level historical industry-membership source.
- JSONL records using the existing `IndustryMembershipPIT` and `CorporateActionPIT` contracts.

## Guarantees

- Every admitted row references a document whose bytes are read and SHA-256 verified at runtime.
- Provider transient IDs appear only as SHA-256 identities.
- Output is an immutable operation directory physically separate from every input directory.
- The manifest binds source-document bytes, normalized record files, the PIT bundle, and the
  announcement-link set.
- Missing documents, unsupported source types, hash mismatches, invalid PIT timing, overlapping
  industry intervals, duplicate revisions, and replay attempts fail closed.
- `formal_research_eligible` remains `false` and `inferential_trial_delta` remains zero.

## Execution

```powershell
$env:PYTHONPATH = "src"
python scripts/build_authoritative_pit_sources.py --config configs/authoritative-pit.local.json
```

Original documents, normalized local records, output bundles, machine paths, and credentials stay
outside Git. A successful candidate bundle is still subject to core review and Issue #84 Gate 5.

## Completion gate

`scripts/build_source_completion_report.py` combines the immutable AlphaPai manifests for
2022-2026 with authoritative-source manifests. It exits with code 2 while any quarantine remains,
industry or corporate-action evidence is absent, provenance is broken, or restricted-year state is
incorrect. A passing report proves source completeness only; it deliberately does not set formal
Research eligibility, which remains an explicit Issue #84 Gate 5 decision.

## Local maintenance evidence (2026-08-18)

The previously quarantined 2023-2024 AlphaPai identities were re-queried with live provider IDs.
Eight PDF responses were requested and seven provider downloads succeeded; the failed provider
download returned HTML and was rejected before persistence. The corresponding duplicate identity
was bound to the byte-verified PDF returned for the same title, stock, report period and disclosure
date. Two visually similar Rabbit Baby disclosures had different PDF hashes and were retained as
distinct source versions rather than deduplicated. The two Tongxiang duplicate pairs were byte
identical within each pair.

| Partition | Accepted rows | Verified document identities | Quarantine | Bundle SHA-256 |
|---|---:|---:|---:|---|
| 2023 | 6,211 | 4 | 0 | `63e9096cbbc3f8fa67c05ff3f3b54970ab946308881b28ff4dfe395bee14b03b` |
| 2024 | 5,858 | 4 | 0 | `57f0a09e20b98038968af4e2d426d577589aa44c0dbabdcb320377b8fb629a55` |

Each partition was rebuilt under a separate replay operation and produced the identical bundle
SHA-256. Original PDFs, provider IDs, local paths, configurations and generated bundles remain in
the gitignored Data Maintenance area. These results close the eight-record document ambiguity but
do not claim authoritative historical industry-membership or full corporate-action coverage.
