# V1.8.11 — Point-in-Time Dynamic Universe

## Objective

Replace the fixed 20-stock research panel with an auditable membership list decided independently
at every historical close. Membership decided at date `t` is available after that close and may
only be used for the next trading session.

This milestone builds and audits the universe. It does not run a factor backtest and does not open
the reserved 2025 validation or 2026 final-test windows.

## Frozen research contract

- Research membership dates: 2022-01-04 through 2024-12-31.
- Target size: 300 stocks.
- Minimum observed trading history: 120 sessions through the decision date.
- Liquidity measurement: trailing 20 observed sessions, including the decision close.
- Minimum trailing mean amount: CNY 20 million per session.
- Ranking: descending trailing mean amount, then instrument code for deterministic ties.
- Supported securities: Shanghai, Shenzhen, ChiNext, STAR, and Beijing A-share code families.
- Exclude the security on that date when:
  - listing date is missing or later than the decision date;
  - either daily or same-day fundamental name contains `ST` or the delisting marker `退`;
  - current volume or amount is non-positive;
  - observed history or liquidity history is insufficient;
  - trailing mean amount is below the floor.

The same-date fundamental snapshot must exist exactly; future snapshots and backward-filled names
are prohibited. Every exclusion reason, entry, exit, membership turnover, exact source snapshot
hash, and daily member list is retained.

## Scope boundary

Absence from a daily partition is treated as no new signal and therefore no membership for that
date. A later execution milestone must still define how an already-held suspended or delisting
security is valued and exited without forward filling. V1.8.11 does not silently solve that
portfolio-accounting problem.

Passing V1.8.11 requires complete same-day fundamental coverage, deterministic replay, at least
300 eligible stocks on normal research dates after the initial history warm-up, and no use of
post-2024 files.
