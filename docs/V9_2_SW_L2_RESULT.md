# V9.2 real-data result

The local 2020-2026 Shenwan Level-2 export was ingested and independently
verified before V10 development.

| Year | As of | Industries | Stocks | Grade | Research state |
|---:|---|---:|---:|---|---|
| 2020 | 2020-12-31 | 41 | 555 | PARTIAL | training-only with disclosure |
| 2021 | 2021-12-31 | 131 | 4,229 | PIT_LITE_B | training-only |
| 2022 | 2022-12-31 | 131 | 4,803 | PIT_LITE_B | training-only |
| 2023 | 2023-12-31 | 131 | 5,226 | PIT_LITE_B | training-only |
| 2024 | 2024-12-31 | 131 | 5,332 | PIT_LITE_B | training-only |
| 2025 | 2025-12-31 | 131 | 5,416 | PIT_LITE_B | sealed |
| 2026 | 2026-09-02 | 131 | 5,584 | PIT_LITE_B | sealed |

- Membership rows: 31,145
- Derived annual changes: 5,795
- Duplicate year/instrument keys: 0
- PIT timing violations: 0
- Sealed-flag violations: 0
- Snapshot verification: PASS
- Same-source replay: `REPLAY_NOOP`

The snapshot identifier and source hash are recorded in the local warehouse
manifest and intentionally omitted here so this versioned report remains a
portable aggregate result rather than a substitute for machine-verifiable
lineage.
