# V1.3 Purged and Embargoed CPCV

## Goal

Produce deterministic research splits that prevent overlapping financial labels and near-test observations from contaminating training evidence.

## Split rules

- Samples are ordered by feature timestamp.
- Complete timestamps are assigned to contiguous groups; a cross-section is never split across groups.
- Every combination of `n_test_groups` from `n_groups` produces one CPCV fold.
- A training sample is purged when its closed label interval overlaps any test label interval.
- A remaining training sample is embargoed when its feature timestamp falls after a test label end and within the configured embargo duration.
- Random K-fold is intentionally not implemented.

## OOS paths

Test-group appearances are deterministically assigned to `C(n_groups - 1, n_test_groups - 1)` OOS paths. Every path contains every chronological group exactly once. A fold may supply more than one segment to a path when the group/test-group combination requires it.

## Fold-local preprocessing

`fit_transform_fold` creates a fresh transformer for each fold, calls `fit` with training IDs only, and only then transforms training and test IDs. This prevents global scaling, imputation, or feature selection from learning from test samples.

## Manifest and audit

The manifest includes:

- sample-set SHA-256
- Snapshot, Experiment, Trial, and code lineage
- test groups and retained/purged/embargoed IDs
- train and test temporal boundaries for every fold
- deterministic OOS path assignments

Audits verify train/test disjointness, absence of label overlap, embargo compliance, and recorded lineage/boundaries.

The manifest and audit report can be written as deterministic JSON artifacts with separate SHA-256 hashes.

Walk-forward deployment simulation remains a separate later milestone. CPCV is the research evidence generator.
