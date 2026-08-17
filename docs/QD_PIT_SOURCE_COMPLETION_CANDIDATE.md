# QD PIT source completion candidate

This candidate extends the `data-test` PIT staging layer with Research-allowed-year AlphaPai
announcement provenance. All raw responses, documents, local configurations, and normalized
bundles remain outside Git.

## Local maintenance evidence

| Year | Accepted rows | Source pages | Conservative delays | Duplicates removed | Quarantined | Bundle SHA-256 |
|---|---:|---:|---:|---:|---:|---|
| 2022 | 6,708 | 78 | 266 | 280 | 0 | `2212b15a3999b9cd5d46e50ea13eee71bbdb5315cb69e997057dad4632fdf5c0` |
| 2023 | 6,208 | 75 | 3,194 | 484 | 4 | `1f37341d99953e3339efaae70e31248a92473fbc3d3cfe5a9edd393e4c775b92` |
| 2024 | 5,856 | 75 | 4,695 | 840 | 4 | `5542899630478956341463751365258d0d8b40dc74ed89cc785fa4f3291a2cc4` |

Each year was rebuilt under a second unique operation ID from the same frozen source pages,
configuration, parser, and ingestion time. The replay hashes matched exactly. Every operation has
`inferential_trial_delta = 0` and remains `formal_research_eligible = false` pending Gate 5.

## Evidence rules added

- The exact AlphaPai empty-partition envelope (`pageNum=1`, `totalPageNum=0`, `totalSize=0`, empty
  data) is accepted. Any inconsistent zero-page response fails closed.
- Missing `actualPublishTime` is never silently replaced with a claimed actual time. The record is
  marked `nominal_plus_delay` and receives a deterministic 24-hour conservative availability delay.
- Repeated records with the same transient retrieval ID or the same source-document hash are
  removed and counted in the Remote Retrieval Ledger.
- A transient ID is never persisted. Local source-document overrides use only a transient-ID hash
  mapped to the downloaded document SHA-256.
- Metadata-identical records with different IDs require document evidence. If neither parsed text
  nor PDF is available, every ambiguous record is quarantined and excluded from the PIT bundle.

## Remaining source limitations

- Four 2023 and four 2024 records are quarantined because AlphaPai exposed distinct document IDs
  with identical metadata but did not provide retrievable parsed text or PDF evidence.
- Historical stock-level industry constituent intervals still require an authoritative constituent
  source. Industry-index quotes are not used as a substitute.
- Corporate-action rows still require authoritative event documents. Adjustment factors are not
  reverse-interpreted into events.
- This candidate does not change default research paths, promote metadata, or unlock 2025/2026.

These limitations are explicit coverage gaps, not inferred facts. Promotion requires zero
unreviewed provenance ambiguity for every promoted field and a separate Gate 5 approval.
