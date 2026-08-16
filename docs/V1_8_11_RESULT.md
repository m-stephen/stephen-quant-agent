# V1.8.11 — Frozen Dynamic-Universe Result

## Decision

**PASS_DATA_ENGINEERING.**

The QD daily and fundamental partitions can reconstruct a deterministic point-in-time 300-stock
research universe for every trading session from 2022 through 2024. This removes the fixed-list
membership blocker, but it is not an alpha result and does not yet solve portfolio accounting for
already-held suspended or delisting securities.

## Lineage

- Initial implementation: `bdf2185`.
- Final turnover and future-file leakage fix: `5357db0`.
- Method: `qd-point-in-time-dynamic-universe-1.0.0`.
- Source snapshot SHA-256:
  `19e71e9203563aa4825d1f3199628de55289666e67d82c89f3593f9787cf6a54`.
- Dynamic-universe JSON SHA-256:
  `261b45cd7696f934a2392b308ccb6fd79ae1ebb22d4233987775dfbf7e5d19ac`.
- Membership JSONL SHA-256:
  `29dd231b8bc6a56bb9e3fd140f331fa1676a96384416d740c3c8f2d7d65c4061`.

Raw market data, generated memberships, and machine-specific paths remain outside git.

## Coverage

- Decision dates: 2022-01-04 through 2024-12-31.
- Trading sessions: 726.
- Exact same-day fundamental snapshot matches: 726/726.
- Target membership: 300.
- Selected range: 300 to 300.
- Mean eligible candidates: 4,197.26.
- Minimum eligible: 3,650 on 2022-04-19.
- Maximum eligible: 5,038 on 2024-11-21.
- Unique instruments selected at least once: 1,738.
- First-to-last membership overlap: 98 of 300.
- Mean daily one-way membership turnover: 2.2365%.
- Maximum daily turnover: 5.3333% on 2024-10-09, with 16 entries and 16 exits.

The low first-to-last overlap demonstrates why carrying one fixed list backward would materially
misrepresent the historical investable set.

## Aggregate exclusions

| Reason | Instrument-days excluded |
|---|---:|
| Below CNY 20 million trailing liquidity floor | 306,414 |
| Risk warning or delisting name | 234,642 |
| Insufficient observed trading history | 92,636 |
| Instrument absent from the same-day fundamental snapshot | 50,076 |
| Unknown or future listing date | 7 |
| Non-A-share code family | 716 |

An exact fundamental file existed for every date, but some daily instruments were absent from that
same-day file. They were excluded rather than joined to a later or older record.

## Integrity checks

- **PASS** — Membership uses only information available after each decision close.
- **PASS** — All 726 dates have an exact same-day fundamental snapshot.
- **PASS** — Every date has at least 300 eligible instruments.
- **PASS** — ST, delisting, invalid listing-date, non-trading, short-history, and illiquid rows are
  excluded with explicit counts.
- **PASS** — Adding a future partition leaves the historical report byte-identical.
- **PASS** — Two complete final replays produced identical JSON, Markdown, and JSONL SHA-256
  hashes.
- **PASS** — No post-2024 source file is part of the frozen snapshot.

## Remaining blocker

V1.8.11 defines who may receive a new signal. It does not define valuation and forced-exit policy
when an existing holding becomes suspended, enters delisting consolidation, or disappears from a
partition. The next milestone must implement a stateful dynamic-universe execution engine with a
no-forward-fill accounting audit before this universe is used for a cost-aware backtest.
