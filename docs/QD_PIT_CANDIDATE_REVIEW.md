# QD Phase 0-1 Local Prototype Review

Issue: #75. Review basis: core-development comment `issuecomment-5314910100`.

Status: local prototype evidence only. This is not a repository capability,
approved dataset, PIT implementation, or promotion request.

## Scope

This first review package contains only Phase 0 dual-plane isolation/read-only
controls and Phase 1A audit of an externally generated, explicit 2022-2024
research allowlist.
It excludes AlphaPai retrieval, PIT layers, inference and default-source changes.

## Information firewall

The auditor cannot discover files. It has no `iterdir`, `glob` or `rglob`
operation. It accepts only relative CSV paths in a pre-generated manifest and
validates partition dates before checking existence, opening or hashing files.
The manifest records its external generation owner and exclusion proof; the
research workflow does not generate it from a mixed root.

Research Plane cannot receive 2025/2026 paths, content, hashes, statistics or
remote-query results. Data Maintenance Plane may maintain 2025, and may
maintain 2026 only with separate explicit authorization. Both remain in
restricted manifests and can expose only non-content control metadata to the
research plane.

The three states are `RESEARCH_ALLOWED_2022_2024`,
`CONSUMED_2025_DATA_MAINTENANCE_ONLY`, and
`SEALED_2026_DATA_MAINTENANCE_ONLY`.

## Ledgers and outputs

- Static audit routes to Data/Search Ledger.
- Remote Retrieval Ledger is not used in Phase 0-1.
- Inferential Trial Ledger delta is exactly zero.
- Every authorized 2025/2026 maintenance access requires a Data Operations
  Ledger record with subject, approval, purpose, scope, hashes, versions and result.
- Output is deterministic JSON, Chinese Markdown, English Markdown and JSONL.
- Reports contain hashes and relative labels, not absolute source paths.

## Approval

Promotion requires automated gates, core-development review, and explicit user
or repository-maintainer approval bound to manifest SHA-256, schema/audit
version and PR/commit. Every 2026 maintenance access needs its own auditable
authorization, which does not authorize research unsealing. No Agent can
self-approve generated data.
