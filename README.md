# Stephen Quant Agent

An **integrity-first** quantitative research system inspired by three research directions:

1. LLM-assisted factor/state/reward design;
2. reinforcement learning for portfolio allocation;
3. strict financial-ML evaluation integrity to detect leakage and backtest overfitting.

The project deliberately starts with **V1.0: Evaluation Integrity Foundation** before building alpha models.

## V1.0 includes

- SQLite Experiment Registry
- deterministic SHA-256 data snapshot manifests
- point-in-time metadata structures
- monotonically increasing Trial Counter
- feature timing look-ahead audit
- Codex project instructions in `AGENTS.md`
- GitHub Actions CI

## V1.1 factor foundation

- immutable, versioned factor definitions
- 15 momentum, trend, relative-strength, liquidity, and risk seed factors
- deterministic dependency-light calculations
- explicit failures for insufficient history, missing values, and future-unavailable inputs

See `docs/V1_1_SPEC.md` for the factor and timing contracts.

## V1.2 alpha evaluation

- cross-sectional IC, RankIC, ICIR, hit rate, and horizon decay
- subperiod, market-regime, turnover, and factor-redundancy diagnostics
- deterministic JSON and Markdown Alpha Cards with complete research lineage

See `docs/V1_2_SPEC.md` for metric definitions and sample-integrity rules.

## Quick start

```bash
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

Initialize the registry:

```bash
stephen-quant --db artifacts/registry.sqlite3 init-db
```

Freeze a data snapshot:

```bash
stephen-quant --db artifacts/registry.sqlite3 snapshot data \
  --vendor-version "vendor-2026-08-16"
```

The command prints a `snapshot_id`. Use it to start an experiment:

```bash
stephen-quant --db artifacts/registry.sqlite3 start-experiment \
  --name "momentum_seed_v1" \
  --hypothesis "60-day relative momentum has positive out-of-sample RankIC" \
  --snapshot-id "snap_xxxxxxxxxxxxxxxx" \
  --search-space '{"lookback":[20,60,120]}'
```

Register every attempt as a trial:

```bash
stephen-quant --db artifacts/registry.sqlite3 start-trial \
  --experiment-id "exp_xxxxxxxxxxxxxxxx" \
  --model baseline \
  --factor-set ret60 \
  --hyperparams '{}' \
  --seed 42 \
  --train-start 2020-01-01 --train-end 2022-12-31 \
  --validation-start 2023-01-01 --validation-end 2023-12-31 \
  --test-start 2024-01-01 --test-end 2024-12-31
```

Run the registry audit:

```bash
stephen-quant --db artifacts/registry.sqlite3 audit
```

## Roadmap

- **V1.1** Factor Registry and 15 seed momentum/risk factors
- **V1.2** IC, RankIC, ICIR, decay and Alpha Cards
- **V1.3** Purge/embargo + CPCV research evaluator
- **V1.4** Placebo/falsification + DSR/PBO
- **V1.5** Momentum Top-K baseline and realistic costs
- **V1.6** PPO long-only allocation + cash
- **V1.7** LLM Factor Research Agent

## Principle

> LLM discovers → statistics verifies → RL allocates → evaluation attacks.
