# PIT-Lite Daily-bar Industry Proxy Audit

## Decision

The 2022–2024 daily-bar industry field is classified as
**`B_CURRENT_LABEL_BACKFILL`**. It is permitted only for exposure, concentration and sensitivity
diagnostics. It cannot be used for within-industry ranking, industry rotation or proxy-industry
neutralization.

## Evidence

- 726 explicitly allowed daily partitions, 3,731,699 rows, 5,523 securities and 110 industries;
- zero duplicate security-day keys and zero conflicting labels;
- 1.8753% missing industry labels;
- 5,343 securities have at least 20 valid observations, but zero have a historical label change;
- candidate returns were not read and `inferential_trial_delta=0`;
- input manifest SHA-256: `7bf9f460aaed611dcfdb3977ebed456a2ab2f1243d64e832d748a02e10e8681b`;
- result SHA-256: `0c7de0e6d93cc1de11565321d90519a0a3c691803bc5314c9106e9b3fa7fec21`.

This does not assert that vendor data is wrong. It means the field provides no stock-level evidence
of historical industry changes. Issue #92 remains the future authoritative-membership source, while
current factor research proceeds through the industry-independent lane.

## Replay

The machine-local path comes from a gitignored config:

```powershell
stephen-quant qd-industry-proxy-audit `
  --paths-config configs/qd-paths.local.json `
  --output artifacts/issue-98-industry-proxy-audit
```

The command selects only CSV date partitions whose names begin with 2022, 2023 or 2024 and writes a
manifest, JSON and bilingual Markdown. Real absolute paths and generated artifacts are not committed.
