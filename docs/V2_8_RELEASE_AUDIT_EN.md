# V2.8 data-source upgrade release audit

- Package version: 2.8.0
- Classification: `point-in-time-data-source-upgrade`
- Target branch: `main`
- Engineering state: `DATA_SOURCE_STAGING_READY`
- Alpha state: unchanged; no new alpha claim
- New inferential trials: 0
- 2025: maintenance data may be staged, but remains unavailable to new research
- 2026: maintenance data may be staged up to the permitted as-of time, but remains sealed for research
- Live trading: disabled and unauthorized

## Included capabilities

- Deterministic raw-byte inventory, relative-path manifests, byte sizes and SHA-256 hashes.
- Single-user local path configuration, short-lived maintenance unlocks and append-only ledgers.
- Explicit QD audit allowlists without committing raw data or machine-local paths.
- Point-in-time finance revisions, industry intervals, corporate-action contracts and market-cap construction.
- AlphaPai page manifests, pagination-drift detection, conservative availability timestamps and deterministic PIT bundles.
- Runtime source-document binding for exchange announcements and candidate authoritative sources.
- Source-completion reporting that keeps unresolved source families explicit.

## Verified announcement completion

- 2023: 6,211 admitted rows, 4 document identities, quarantine 0.
- 2024: 5,858 admitted rows, 4 document identities, quarantine 0.
- Independent replays produced identical bundle SHA-256 values.
- No raw documents, provider identifiers, credentials or machine-local paths are committed.

## Remaining release boundaries

V2.8 does not claim that all external data is complete. Authoritative stock-level historical
industry membership with effective intervals is still missing (#92), and complete authoritative
corporate-action/share-capital source staging remains incomplete (#93). Gate 5 (#84) therefore
remains blocked and the parent data-completion work (#75) remains open. Candidate fields must not
be promoted to formal research metadata until their corresponding source gates pass.
