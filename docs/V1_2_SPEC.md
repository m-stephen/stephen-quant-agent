# V1.2 Alpha Evaluation and Alpha Cards

## Goal

Turn point-in-time factor observations into reproducible statistical evidence without using the final test set to tune acceptance thresholds.

## Metrics

- Daily cross-sectional Pearson IC and Spearman RankIC
- Mean IC and RankIC across evaluation dates
- Annualized ICIR and RankICIR with an explicit annualization factor
- Positive-IC hit rates
- Separate results for every forward horizon to expose signal decay
- RankIC breakdowns by declared subperiod and market regime
- Mean normalized rank turnover across consecutive dates
- Mean daily rank correlation against supplied existing factors

The primary horizon is the shortest numeric horizon. It is used for turnover, subperiod, regime, and redundancy diagnostics. Every horizon remains visible in the Alpha Card.

## Timing and sample rules

- Ranking occurs only within a single timestamp.
- Every factor value must be available strictly before its label starts.
- Duplicate `(timestamp, instrument, horizon)` observations fail.
- Non-finite values and reversed label intervals fail.
- Each cross-section requires at least three instruments by default.
- Each horizon requires at least two evaluation dates.
- Constant inputs fail because correlation is undefined.

## Artifacts

Alpha Cards are emitted as deterministic JSON and Markdown with SHA-256 hashes. Both formats include factor/version, snapshot ID, experiment ID, trial ID, and code version.

V1.2 reports evidence but does not decide whether a factor is accepted. Formal placebo tests, multiplicity adjustment, DSR, and PBO belong to V1.4.
