# V1.0 — Evaluation Integrity Foundation

## Why this is milestone zero
The project adopts the paper's three-part evaluation-integrity principle:
- temporal honesty;
- sample hygiene;
- multiplicity awareness.

V1.0 does not claim tradable alpha. It creates the provenance and audit layer required before factor research begins.

## Objects

### DataSnapshot
A frozen view of a directory. The snapshot manifest records every file's path, byte size and SHA-256 plus one aggregate SHA-256.

### PointInTimeRecord
Each source record has `effective_at`, `available_at` and `ingested_at`. `available_at` is the critical time: a strategy cannot use the record before then.

### Experiment
A hypothesis bound to one dataset snapshot and one code version. The intended search space is stored before repeated model selection.

### Trial
Every factor/model/reward/hyperparameter attempt is a numbered trial inside an experiment. This is the foundation for later DSR and PBO calculations.

### Audit
The first audit checks that features were available strictly before the label begins and that the registry contains frozen provenance.

## Acceptance criteria
- deterministic snapshot hashing;
- changed input produces changed snapshot hash;
- experiment cannot reference a missing snapshot;
- trial number increments monotonically within an experiment;
- a look-ahead feature timing example fails audit;
- CI runs tests and linting.

## Explicitly deferred
CPCV, purge/embargo splitters, DSR, PBO, transaction-cost models, factor IC calculations, PPO, and LLM factor generation belong to later milestones.
