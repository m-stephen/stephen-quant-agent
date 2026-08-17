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
  --qmt-home "<QMT_DATADIR>" `
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
  --datadir "<QMT_DATADIR>" `
  --output-csv "data\raw\qmt-daily-none.csv" `
  --start 2018-01-01 --end 2025-12-31 `
  --stocks "000001.SZ,000002.SZ,600000.SH"
```

The fallback always supports raw (`none`) bars. Install the optional read-only LevelDB dependency
to add point-in-time-safe QMT `back_ratio` adjustment from `DividData`:

```powershell
pip install -e ".[qmt-dat]"
stephen-quant qmt-dat-export `
  --datadir "<QMT_DATADIR>" `
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
  --datadir "<QMT_DATADIR>" `
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
  --daily-dir "<QD_DAILY_DIR>" `
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

V1.8.6 replaces the manually supplied universe with a reproducible selection made only from the
training window. It ranks complete-history, non-ST stocks that were already listed at the start of
training by their training-period mean daily amount, then freezes the selected files and result:

```powershell
stephen-quant qd-select-universe `
  --daily-dir "<QD_DAILY_DIR>" `
  --fundamental-dir "<QD_FUNDAMENTAL_DIR>" `
  --train-start 2022-01-01 --train-end 2023-12-31 `
  --top-n 20 --output "artifacts\qd-v1.8.6-universe"
```

The resulting stock file can be evaluated against a declared benchmark and two deterministic
placebo tests:

```powershell
stephen-quant --db artifacts\qd-v1.8.6.sqlite3 qmt-backtest `
  --daily-dir "<QD_DAILY_DIR>" `
  --stock-file "artifacts\qd-v1.8.6-universe\qd-universe.txt" `
  --benchmark-csv "<CSI300_CSV>" `
  --benchmark-name "沪深300" --placebo-repetitions 199 `
  --output "reports\qd-v1.8.6" --adjustment back_ratio --factor ret_60 `
  --train-start 2022-01-01 --train-end 2023-12-31 `
  --validation-start 2024-01-01 --validation-end 2024-12-31 `
  --test-start 2025-01-02 --test-end 2025-12-30 `
  --top-k 5 --rebalance-every 5 `
  --commission-bps 3 --sell-tax-bps 5 --slippage-bps 5 --impact-bps 10
```

See `docs/V1_8_6_SPEC.md`. PBO and DSR are intentionally deferred until the trial ledger contains
enough genuinely independent strategy attempts; they are not inferred from one fixed baseline.

V1.8.7 adds a validation-only mode that deliberately excludes the reserved test window from the
data snapshot. For QD rows with a daily name and previous close, the open execution model also
blocks buys at the inferred upper limit and sells at the inferred lower limit:

```powershell
stephen-quant --db artifacts\qd-v1.8.7.sqlite3 qmt-backtest `
  --daily-dir "<QD_DAILY_DIR>" `
  --stock-file "artifacts\qd-v1.8.6-universe\qd-universe.txt" `
  --evaluation-window validation `
  --benchmark-csv "<CSI300_CSV>" `
  --benchmark-name "沪深300" --placebo-repetitions 199 `
  --output "reports\qd-v1.8.7" --adjustment back_ratio --factor ret_60 `
  --train-start 2022-01-01 --train-end 2023-12-31 `
  --validation-start 2024-01-02 --validation-end 2024-12-31 `
  --test-start 2026-01-05 --test-end 2026-08-14 `
  --top-k 5 --rebalance-every 5 `
  --commission-bps 3 --sell-tax-bps 5 --slippage-bps 5 --impact-bps 10
```

The 2026 dates are ledger reservations only in this command. Their files are neither loaded nor
hashed. See `docs/V1_8_7_SPEC.md` and the frozen reference decision in
`docs/V1_8_7_RESULT.md`.

The versioned board prefixes, IPO no-limit markers, historical ST handling, rounding formula, and
official exchange references are documented in `docs/QD_PRICE_LIMIT_RULES.md`.

V1.8.8 expands the immutable registry to 23 definitions and makes research status explicit. Build
the catalog before starting new factor Trials:

```powershell
stephen-quant factor-catalog --output "artifacts\factor-catalog-v1.8.8"
```

Eight new QD-compatible candidates cover skip-recent momentum, trend efficiency, range position,
intraday strength, volume surprise, volume-confirmed momentum, dollar liquidity, and Parkinson
range volatility. `ret_60` remains registered for lineage but is marked rejected and excluded from
the candidate screen.

Use training data only to identify redundant definitions before any return-based validation:

```powershell
stephen-quant qd-factor-screen `
  --daily-dir "<QD_DAILY_DIR>" `
  --stock-file "artifacts\qd-v1.8.6-universe\qd-universe.txt" `
  --data-start 2022-01-01 `
  --screen-start 2023-01-03 --screen-end 2023-12-29 `
  --adjustment back_ratio --threshold 0.80 `
  --output "artifacts\qd-factor-screen-v1.8.8"
```

The screen compares direction-adjusted cross-sectional factor ranks. It does not use forward
returns and does not authorize testing every surviving factor. See `docs/V1_8_8_SPEC.md` and the
frozen training-screen decision in `docs/V1_8_8_RESULT.md`.

V1.8.9 validates the five predeclared V1.8.8 survivors as five independent Trials under one
shared Experiment. After all Trials finish, produce one multiplicity-aware family decision:

```powershell
stephen-quant --db "artifacts\qd-v1.8.9.sqlite3" factor-family-report `
  --experiment-id "exp_xxxxxxxxxxxxxxxx" `
  --output "reports\qd-v1.8.9-family"
```

The family report selects the strongest accepted validation Trial, then requires positive net
Sharpe, positive excess return versus CSI 300, a passed placebo audit, and DSR of at least 0.95.
The sealed 2026 test window remains unopened unless the family passes. See
`docs/V1_8_9_SPEC.md` and the frozen validation decision in `docs/V1_8_9_RESULT.md`.

V1.8.10 treats the observed 2024 result as consumed research evidence and evaluates four
predeclared composite rules with fold-local CPCV weighting. The command loads only the research
history and the single next-open boundary bar; 2025 validation begins on the following session:

```powershell
stephen-quant --db "artifacts\qd-v1.8.10.sqlite3" qd-composite-cpcv `
  --daily-dir "<QD_DAILY_DIR>" `
  --stock-file "artifacts\qd-v1.8.6-universe\qd-universe.txt" `
  --data-start 2021-07-01 `
  --research-start 2022-01-04 --research-end 2024-12-31 `
  --validation-start 2025-01-03 --validation-end 2025-12-31 `
  --test-start 2026-01-05 --test-end 2026-08-14 `
  --groups 6 --test-groups 3 --embargo-days 5 `
  --output "reports\qd-v1.8.10-cpcv"
```

The frozen research gate requires mean path RankIC at least 0.02, at least 8/10 positive paths,
clean CPCV hygiene, and PBO no greater than 0.20. See `docs/V1_8_10_SPEC.md` and the frozen
research decision in `docs/V1_8_10_RESULT.md`.

V1.8.11 builds a point-in-time daily investable universe instead of carrying a present-day or
training-end list backward through history:

```powershell
stephen-quant qd-dynamic-universe `
  --daily-dir "<QD_DAILY_DIR>" `
  --fundamental-dir "<QD_FUNDAMENTAL_DIR>" `
  --research-start 2022-01-04 --research-end 2024-12-31 `
  --top-n 300 --minimum-history-sessions 120 `
  --liquidity-lookback 20 --minimum-mean-amount 20000000 `
  --output "artifacts\qd-v1.8.11-universe"
```

Each close produces a next-session membership list plus entries, exits, turnover, and explicit
exclusion counts. Same-day fundamental metadata is mandatory; future metadata is never
backfilled. See `docs/V1_8_11_SPEC.md` and the frozen data decision in
`docs/V1_8_11_RESULT.md`.

V1.8.12 adds stateful accounting for sparse dynamic-universe panels. A missing held asset is not
dropped: trading is blocked, its mark is explicitly stale, and the stale-session count is audited.
After 20 consecutive missing sessions it is conservatively written to zero; a later quote records
a recovery before any pending exit executes. Limit-down exits remain blocked, and order capacity
must carry a timestamp earlier than the execution open. See `docs/V1_8_12_SPEC.md` and the frozen
engineering decision in `docs/V1_8_12_RESULT.md`.

V1.8.13 connects the frozen dynamic membership, sparse QD bars, factor registry, stateful
accounting, prior-session capacity, costs, and CSI 300 benchmark in one registered engineering
backtest:

Copy `configs/qd-paths.example.json` to `configs/qd-paths.local.json` and fill in the
machine-local paths. Files matching `configs/*.local.json` are ignored by Git. Explicit CLI path
arguments remain available and take precedence over the local file.

将 `configs/qd-paths.example.json` 复制为 `configs/qd-paths.local.json`，再填写本机路径。
`configs/*.local.json` 已被 Git 忽略；如同时传入命令行路径，则命令行值优先。

```powershell
stephen-quant --db "artifacts\qd-v1.8.13.sqlite3" qd-dynamic-backtest `
  --paths-config "configs\qd-paths.local.json" `
  --data-start 2021-07-01 `
  --research-start 2022-01-04 --research-end 2024-12-31 `
  --validation-start 2025-01-03 --validation-end 2025-12-31 `
  --test-start 2026-01-05 --test-end 2026-08-14 `
  --factor mom_120_skip_20 --top-k 20 --rebalance-every 5 `
  --cash-reserve 0.02 --max-position-weight 0.05 `
  --commission-bps 3 --sell-tax-bps 5 --slippage-bps 5 `
  --output "reports\qd-v1.8.13"
```

The fixture factor was already rejected; this command validates execution plumbing and makes no
new alpha claim. Review the bilingual design in `docs/V1_8_13_SPEC.md` and the bilingual frozen
result in `docs/V1_8_13_RESULT.md`.

V1.8.14 starts the next research gate with two newly registered microstructure factors and four
predeclared candidate configurations. The machine-readable search space is frozen in
`configs/v1.8.14-candidates.json`; 2025 and 2026 remain sealed. Review the bilingual design in
`docs/V1_8_14_SPEC.md`.

Run the frozen signal gate with the ignored local path configuration:

```powershell
stephen-quant --db "artifacts\qd-v1.8.14.sqlite3" qd-dynamic-cpcv `
  --paths-config "configs\qd-paths.local.json" `
  --candidate-manifest "configs\v1.8.14-candidates.json" `
  --output "reports\qd-v1.8.14-cpcv"
```

The command registers all four Trials before evaluation and writes JSON plus detailed English and
Chinese Markdown reports. It never loads the reserved 2025 or 2026 partitions.

The frozen V1.8.14 signal gate rejected all four candidates, so execution falsification was not
run and the reserved windows remain sealed. Review the bilingual result in
`docs/V1_8_14_RESULT.md`.

## V1.8.16 automated factor discovery

V1.8.16 provides a one-command, integrity-first loop for structured candidate generation,
training-only screening, purged CPCV, cost-aware execution, placebo/DSR/PBO falsification,
walk-forward validation, research memory, and fail-closed portfolio authorization. The three
horizons are independent Experiments under one frozen global Trial budget.

```powershell
stephen-quant --db "artifacts\qd-v1.8.16.sqlite3" qd-auto-discover-suite `
  --paths-config "configs\qd-paths.local.json" `
  --suite-manifest "configs\v1.8.16-suite.json" `
  --ingested-at "2026-08-17T12:00:00+08:00" `
  --output "reports\qd-v1.8.16"
```

Machine-specific paths and all generated data remain ignored. See the
[English design](docs/V1_8_16_SPEC_EN.md) and [中文设计](docs/V1_8_16_SPEC_ZH.md).
The frozen three-horizon outcome is available in [English](docs/V1_8_16_RESULT_EN.md)
and [中文](docs/V1_8_16_RESULT_ZH.md).

## V1.8.17 normalized multi-source search

V1.8.17 replaces raw alternative-data levels with liquidity-normalized and cross-source
hypotheses, applies point-in-time cross-sectional normalization, limits each factor family in the
CPCV shortlist, and adds yearly-stability and rank-turnover diagnostics to the frozen screen.
It preserves the V1.8.16 CPCV, cost, placebo, PBO, DSR, walk-forward, and sealed-window gates.

```powershell
stephen-quant --db "artifacts\qd-v1.8.17.sqlite3" qd-auto-discover-suite `
  --paths-config "configs\qd-paths.local.json" `
  --suite-manifest "configs\v1.8.17-suite.json" `
  --ingested-at "2026-08-17T00:00:00+08:00" `
  --output "reports\qd-v1.8.17-suite"
```

See the [English design](docs/V1_8_17_SPEC_EN.md) and
[中文设计](docs/V1_8_17_SPEC_ZH.md). The frozen engineering-pass/alpha-reject result is available
in [English](docs/V1_8_17_RESULT_EN.md) and [中文](docs/V1_8_17_RESULT_ZH.md). Local data paths and
generated reports remain Git-ignored.

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
