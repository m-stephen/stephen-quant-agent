# QD PIT source completion candidate

This candidate extends the `data-test` PIT staging layer with Research-allowed-year AlphaPai
announcement provenance. All raw responses, documents, local configurations, and normalized
bundles remain outside Git.

## Local maintenance evidence

| Year | Accepted rows | Source pages | Conservative delays | Duplicates removed | Quarantined | Bundle SHA-256 |
|---|---:|---:|---:|---:|---:|---|
| 2022 | 6,708 | 78 | 266 | 280 | 0 | `b970640432865c5a117ef49a51c5b50b08e0cf6524ce60fada3a0e067b4c0a88` |
| 2023 | 6,208 | 75 | 3,194 | 484 | 4 | `ba901025a7e7e6d5577a3eaaa958383266d11cd36602939f05d9f54ff927e23c` |
| 2024 | 5,856 | 75 | 4,695 | 840 | 4 | `381611cfacdcd1801f43920390a2134a7a33895bb21500b92208e5f1bf3d0cc8` |

Each year was rebuilt under a second unique operation ID from the same frozen source pages,
configuration, parser, and ingestion time. The replay hashes matched exactly. Every operation has
`inferential_trial_delta = 0` and remains `formal_research_eligible = false` pending Gate 5.

The v3 operation also replayed the complete quarantine identity set. The 2022 empty-set hash is
`4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`; the four 2023 identities
produce `5ad23209989b4612b242b99fc1ac9d8f9bc2f1750e0842b263230e63810aba38`; and the four 2024
identities produce `8f10fd128175b6219290d5438ad0de0d0f247690f3af56911101b510ee185bad`.
Configured and runtime-auto quarantine identities are merged before hashing, and every identity is
validated as a 64-character hexadecimal SHA-256 rather than accepted as a raw provider ID.

## Evidence rules added

- The exact AlphaPai empty-partition envelope (`pageNum=1`, `totalPageNum=0`, `totalSize=0`, empty
  data) is accepted. Any inconsistent zero-page response fails closed.
- Missing `actualPublishTime` remains null. The record is marked `nominal_plus_delay` and receives
  a deterministic 24-hour conservative availability delay; invalid quality values and inconsistent
  quality/time combinations fail closed.
- Repeated records with the same transient retrieval ID or the same source-document hash are
  removed and counted in the Remote Retrieval Ledger.
- A transient ID is never persisted. Local source-document configuration maps its hash to a file;
  the builder reads the real document bytes and records size and SHA-256. Declared hashes are
  rejected.
- Metadata-identical records with different IDs require document evidence. If neither parsed text
  nor PDF is available, every ambiguous record is automatically quarantined and excluded from the
  PIT bundle. The complete quarantine hash set and its set hash are bound into operation evidence.

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
