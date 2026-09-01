# V8.8 final test report

## Verdict

The on-demand minute data service is operational. It locates the requested instrument inside a
historical master archive, extracts only that member, filters the requested dates, materializes the
result and exposes it immediately through `qd_minute_current`. Exact and overlapping requests do
not rewrite dates already covered by prior scopes.

## Real validation

- Request: `000001.SZ`, 5-minute bars, 2020-01-02 through 2020-01-10.
- Located source: `2000-2025/5分钟.zip`.
- Master archive size: approximately 10 GB; selected member bytes: 16,319,073.
- Materialized: 336 rows, seven observed trading days and seven partitions.
- Source gaps: 0; quarantined rows: 0.
- Exact replay: `REPLAY_NOOP`, zero new members and revisions.
- Query surface: `qd_minute_current`.

Snapshot after the real scoped load:
`7717a68f53441b828324be7260b16efdcdd171a07a9d0c5f1a07337cdfac5c32`.

- Snapshot verification: pass.
- Revision rows: 8,763,648.
- Partitions: 32.
- Duplicate current keys: 0.
- PIT timing violations: 0.

## Risks and boundaries

1. **High, confirmed:** historical market-wide requests require an instrument allowlist to prevent
   accidental expansion of hundreds of gigabytes.
2. **Medium, confirmed:** the first historical request still hashes the complete source archive;
   the real request took about 25 seconds. Replay validates source identity again but writes nothing.
3. **Medium, confirmed:** routing covers the observed 2000-2025 master bundles and dated archives.
   Instruments or dates absent from source are reported as gaps or lower actual coverage.
4. **Low, confirmed:** data availability does not mean a minute factor has passed Alpha Court.
