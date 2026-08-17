# QD Single-user Integrity Profile

## Status and boundary

This is an Issue #88 candidate for `data-test`. It replaces mandatory online GitHub approval with
an explicit local inventory, short-lived unlock, and manifest-bound maintenance workflow. It does
not generate research statistics, unseal 2026 by default, promote data to `main`, or authorize
factor tuning on restricted windows.

## Local configuration

Put real paths only in a gitignored local path configuration. The checked-in example contains
placeholders for:

- `qd_single_user_data_root`;
- `qd_single_user_manifest_dir`;
- `qd_single_user_ledger_dir`.

No command emits these absolute paths in its machine-readable result.

## Workflow

```powershell
stephen-quant data-inventory --paths-config local-paths.json --year 2025
stephen-quant data-unlock --paths-config local-paths.json --manifest <manifest> --year 2025 --purpose pit-maintenance --expires-seconds 7200
stephen-quant data-maintain --paths-config local-paths.json --manifest <manifest> --operation-id <operation-id>
```

Inventory walks only the configured root, rejects symbolic links and path escapes, and opens
candidate files only as raw bytes for SHA-256. The deterministic manifest contains relative paths,
partitions, exact byte sizes, file hashes, state, source type, parser version, and schema version.
Scan start and completion times are recorded in the local ledger rather than the deterministic
manifest.

Unlock is an explicit local command. It binds year, purpose, manifest SHA-256, code commit,
parser/schema versions, expiry, requested outputs, and an automatically generated operation ID.
Unlocking 2026 requires a separate explicit sealed-year flag and is denied by default.

Maintain validates the unlock and atomically reserves the operation ID before opening source
files. The reserving process verifies path containment, size, and SHA-256. Success, validation
failure, and I/O failure receive terminal ledger states. A failed operation ID cannot be replayed.

## Threat model

Replay protection covers one operating-system user and the configured local ledger directory. It
does not claim cross-user, cross-host, or malicious-owner protection. Research integrity controls,
snapshot hashes, PIT timing rules, trial accounting, and restricted-window states remain mandatory.
