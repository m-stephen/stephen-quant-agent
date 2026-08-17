# QD Phase 1B Runtime Candidate

## Status

This implementation is a synthetic-data-only candidate on `data-test`. It does not authorize
access to 2025 data and does not change the sealed status of 2026 data.

## Maintenance manifest contract

The runtime computes the manifest SHA-256 from the exact UTF-8 bytes and requires every file entry
to include:

- a safe relative path;
- a partition whose year matches the authorized year;
- the SHA-256 of the exact source file bytes;
- the exact file size in bytes.

Before consuming an operation authorization, the runtime resolves every file below the execution
source root, rejects path escapes, reads the file, and compares its size and SHA-256 with the
approved manifest.

## Operation ledger contract

The public authorization API has no ledger-directory argument. The runtime uses one policy-owned
location under the current operating-system user's home directory:

`~/.stephen-quant-agent/maintenance-control/operation-ledger`

The directory is created with owner-only permissions where supported. Each `operation_id` is
consumed through exclusive file creation, so an existing operation record causes the execution to
fail closed. The record freezes the approval comment ID, comment update time, normalized approval
payload SHA-256, manifest SHA-256, state, year, and the actual UTC consumption time.

## Authorization boundary

- A 2025 dry-run requires a new, explicit, single-operation approval comment in Issue #85.
- The approval must bind the operation ID, manifest hash, source scope, purpose, code commit,
  parser version, schema version, and allowed outputs.
- 2026 remains sealed and requires a separate approval.
- No output is promoted to `main` or formal research metadata without a later review.
