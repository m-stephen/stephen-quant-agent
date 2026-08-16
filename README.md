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

## V1.3 leakage-resistant validation

- label-interval purge and configurable post-test embargo
- deterministic combinatorial purged cross-validation folds and OOS paths
- fold-local preprocessing hooks that fit on training IDs only
- hashed split manifests and per-fold integrity audits

See `docs/V1_3_SPEC.md` for split semantics and audit guarantees.

## V1.4 falsification and multiplicity control

- seeded cross-sectional signal-shuffle and forward-return placebos
- repeated null distributions with finite-sample empirical p-values
- trial-ledger-aware Deflated Sharpe Ratio
- PBO computed from complete, audited CPCV path results
- deterministic Alpha Court reports with explicit pass/reject thresholds

See `docs/V1_4_SPEC.md` for evidence contracts, default thresholds, and limitations.

## V1.5 executable Momentum Top-K baseline

- deterministic point-in-time Top-K selection and equal weighting
- configurable rebalance schedule, cash reserve, and concentration cap
- commissions, slippage, and participation-sensitive market impact
- ADV capacity limits with explicit capacity and funding clipping
- net-of-cost NAV, drawdown, turnover, and execution audit reports

See `docs/V1_5_SPEC.md` for portfolio, execution, cost, and timing contracts.

## V1.6 PPO long-only allocation with cash

- dependency-light linear Gaussian actor-critic reference policy
- softmax long-only asset-plus-cash allocations
- generalized advantage estimation and PPO clipped surrogate updates
- net-of-cost reward with turnover and drawdown penalties
- training-only normalization and frozen deterministic validation
- reproducible policy hashes and JSON/Markdown training reports

See `docs/V1_6_SPEC.md` for policy, reward, training, and validation integrity contracts.

## V1.7 LLM Factor Research Agent

- trial-first, provider-neutral LLM proposal workflow
- point-in-time research sources and explicit knowledge cutoffs
- exact JSON proposal schema with evidence citations and falsification plans
- AST-validated factor DSL with no arbitrary code execution
- persistent candidate fingerprints, duplicate rejection, and `proposed`-only status
- deterministic prompt/response hashes and JSON/Markdown audit reports

See `docs/V1_7_SPEC.md` for the agent boundary, safe DSL, and candidate lifecycle.

## V1.8 QMT end-to-end backtest

- dependency-light Guojin QMT daily CSV adapter with Chinese and English header aliases
- exact single-file SHA-256 snapshots and dataset quality audits
- prior-close factor signals, next-session open execution, and next-open returns
- Trial-first orchestration over the existing seed-factor and Momentum Top-K engines
- China-compatible sell-side tax plus commissions, slippage, impact, and ADV capacity
- deterministic JSON/Markdown reports registered to the Trial ledger

See `docs/V1_8_SPEC.md` for the input contract, timing semantics, limitations, and acceptance test.

Run a locked-window QMT backtest:

```bash
stephen-quant --db artifacts/qmt-v1.8.sqlite3 qmt-backtest \
  --csv /private/path/qmt_daily.csv \
  --output reports/qmt-v1.8 \
  --adjustment front_ratio \
  --factor ret_60 \
  --train-start 2018-01-01 --train-end 2021-12-31 \
  --validation-start 2022-01-01 --validation-end 2023-12-31 \
  --test-start 2024-01-01 --test-end 2025-12-31 \
  --top-k 10 --rebalance-every 5 \
  --commission-bps 3 --sell-tax-bps 5 --slippage-bps 5 --impact-bps 10
```

The raw CSV, registry database, and generated reports are ignored by Git. Keep them outside the
public repository. Reuse the printed `experiment_id` with `--experiment-id` for every related retry
so rejected and successful attempts accumulate in one multiplicity ledger.

If QMT data is stored in its native `datadir` binary cache, keep the QMT client logged in with its
quote/Python service running and export through the official local-only `xtquant` API first:

```powershell
stephen-quant qmt-export `
  --qmt-home "E:\path\to\QMT\datadir" `
  --output-csv "data\raw\qmt-daily.csv" `
  --start 2018-01-01 --end 2025-12-31 `
  --adjustment front_ratio `
  --stocks "000001.SZ,000002.SZ,600000.SH"
```

`--qmt-home` accepts either the installation root or its `datadir`. For a larger universe, replace
`--stocks` with `--stock-file path/to/stocks.txt` or `--sector "沪深A股"`. The exporter calls only
`xtdata.get_local_data`; it does not download history, start QMT, or connect to a trading account.

Some broker-wrapped QMT terminals cannot start the `xtquant` quote service. V1.8.2 provides a
version-locked, read-only fallback for explicit A-share instruments in `SH/SZ/BJ/86400/*.DAT`:

```powershell
stephen-quant qmt-dat-export `
  --datadir "E:\path\to\QMT\datadir" `
  --output-csv "data\raw\qmt-daily-none.csv" `
  --start 2018-01-01 --end 2025-12-31 `
  --stocks "000001.SZ,000002.SZ,600000.SH"
```

The fallback always supports raw (`none`) bars. Install the optional read-only LevelDB dependency
to add point-in-time-safe QMT `back_ratio` adjustment from `DividData`:

```powershell
pip install -e ".[qmt-dat]"
stephen-quant qmt-dat-export `
  --datadir "E:\path\to\QMT\datadir" `
  --output-csv "data\raw\qmt-daily-back-ratio.csv" `
  --start 2018-01-01 --end 2025-12-31 `
  --adjustment back_ratio `
  --stocks "000001.SZ,000002.SZ,600000.SH"
```

The adapter normalizes stock volume from lots to shares, keeps amount in CNY, validates the binary
layout and bar semantics, and hash-links both DAT files and the complete corporate-action snapshot
in the provenance manifest. Minute, tick, index, ETF, bond, and futures parsing remain out of scope.

On the `data-test` branch, run the complete engineering validation in one command:

```powershell
stephen-quant --db artifacts\qmt-dat-validation.sqlite3 qmt-dat-validate `
  --datadir "E:\path\to\QMT\datadir" `
  --output "reports\qmt-dat-validation" `
  --data-start 2020-01-01 --data-end 2025-12-31 `
  --adjustment back_ratio `
  --stock-file "private\validation-universe.txt" `
  --factor ret_60 `
  --train-start 2020-01-01 --train-end 2021-12-31 `
  --validation-start 2022-01-01 --validation-end 2023-12-31 `
  --test-start 2024-01-01 --test-end 2025-12-01 `
  --top-k 10 --rebalance-every 5 `
  --commission-bps 3 --sell-tax-bps 5 --slippage-bps 5 --impact-bps 10
```

The command creates the canonical CSV and raw-source manifest, freezes the CSV snapshot, registers
the Trial before evaluation, executes the net-of-cost backtest, and writes
`validation-summary.json` plus `validation-summary.md`. A successful direct-DAT run is deliberately
reported as **engineering validated / research claim ineligible** until a point-in-time historical
universe is available. V1.8.4 removes the unadjusted-price blocker when `back_ratio` is selected,
but it does not remove survivorship bias from a current constituent list. See
`docs/V1_8_3_SPEC.md` and `docs/V1_8_4_SPEC.md`.

V1.8.5 also accepts the private QD dataset stored as one full-market CSV per trading date. The
adapter validates the filename/row date contract, converts lots to shares and thousand CNY to CNY,
and can apply the file's cumulative adjustment factor as point-in-time `back_ratio` prices:

```powershell
stephen-quant --db artifacts\qd-v1.8.5.sqlite3 qmt-backtest `
  --daily-dir "E:\QD\基本数据\股票日K_按日期" `
  --stock-file "private\qd-validation-universe.txt" `
  --output "reports\qd-v1.8.5" `
  --adjustment back_ratio `
  --factor ret_60 `
  --train-start 2022-01-01 --train-end 2023-12-31 `
  --validation-start 2024-01-01 --validation-end 2024-12-31 `
  --test-start 2025-01-02 --test-end 2025-12-30 `
  --top-k 5 --rebalance-every 5 `
  --commission-bps 3 --sell-tax-bps 5 --slippage-bps 5 --impact-bps 10
```

The fixed universe must be declared before the test window. Missing sessions are not forward-filled.
See `docs/V1_8_5_SPEC.md` for the data and integrity contract.

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
- **V1.8** QMT data adapter and end-to-end out-of-sample backtest

## Principle

> LLM discovers → statistics verifies → RL allocates → evaluation attacks.
