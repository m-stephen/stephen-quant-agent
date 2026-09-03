# V9.1 Complete minute materialization result

Status: **Local data, replay, integrity, tests, Ruff, and GitHub Actions gates pass.**

## Complete result

| Metric | Result |
|---|---:|
| Recognized minute archives | 194 |
| MATERIALIZED archives | 194 |
| Source members | 4,447,591 |
| Physical Parquet partitions | 1,460 |
| Final snapshot | `fde4ef3e...17dfb` |
| Fully verified rows | 6,340,365,218 |
| Duplicate current keys | 0 |
| PIT timing violations | 0 |
| stderr | 0 bytes |

The run started with 31 AVAILABLE and two PARTIAL archives. Eight parser workers fed a single
DuckDB-writing parent process, adding 103,615 members, 3,829,898,531 revisions, and 420 partitions.
The source directory remained read-only throughout.

## Storage and safety

- V9.0.1 reduced the existing 1,040 partitions from 123.43 GiB to 28.50 GiB, a 76.91% reduction.
- After V9.1 added the remaining data, range Parquet occupies 71.85 GiB and daily Parquet 3.58 GiB.
- The run consumed about 45.79 GiB net. The E drive retained about 418.28 GiB free, above the
  100GB reserve.
- Three orphan files not referenced by the Catalog, migration ledger, or any snapshot were removed
  only after exact proof, releasing about 1.34 GiB. Physical and Catalog partition counts now both
  equal 1,460.
- 4,818,223 source rows that did not satisfy the parser contract remain explicit in quarantine
  evidence; none were fabricated or silently filled.

## Replay and verification

A second run returned `pending_archives_at_start=0`, `archive_results=[]`, and
`estimated_parquet_bytes=0`, with an unchanged final snapshot ID. Streaming verification checked
every file SHA-256 and scanned all 6,340,365,218 rows. It returned `passed=true`, zero duplicate
current keys, and zero PIT timing violations.

## Decision

V9.1 passes the local data gate. It increases data availability and research throughput but is not
itself Alpha evidence. The next phase builds the minute feature layer, cross-source factor grammar,
and unified Alpha Court on this warehouse.
