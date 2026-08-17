# V2 M2: Bounded Novelty Gate and Cheap Diagnostics

## Objective

Reject duplicate or clearly unusable candidates before CPCV with preregistered, bounded and explainable rules. This gate reduces expensive validation workload; it neither replaces statistical validation nor promises real-alpha recall.

## Novelty Gate

The gate supports canonical AST equality, commutative Add/Multiply normalization, fixed-fixture numerical and rank equivalence, control-residual correlation, exposure cosine and semantic-tag Jaccard. Semantic similarity is audit-only and cannot reject by itself. Every rejection returns a typed reason code.

## Cheap Diagnostics

The report covers coverage, missingness, staleness, daily IC/RankIC, residual IC, quintile shape, long/short decomposition, rank turnover, holding decay, style and industry exposure, date/regime concentration and simplified cost-adjusted spread. Thresholds come from a frozen configuration.

## Engineering benchmark

The frozen fixture contains exact, algebraic, numerical and residual duplicates plus two known-valid unique fixtures. Acceptance requires 100% exact recall, at least 95% empirical duplicate precision/recall, at least 50% CPCV workload reduction and 100% known-valid fixture recall. These are engineering regression metrics, not investment-validity evidence.
