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
