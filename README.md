# Stephen Quant Agent

## V4.3 information-domain breadth

V4.3 unifies the historical safe-DSL generation plans, canonicalizes 202 proposals into 152
unique hypotheses, applies per-domain proposal budgets, and adds explicit counter-direction
tests for the underexplored chip and limit-event domains. It also fixes sparse-signal CPCV dates,
bounds dynamic memberships by the research window, and provides an append-only forward-shadow
ledger starting on 2026-08-19.

```powershell
stephen-quant --db artifacts/v4.3/registry.sqlite3 v4.3-domain-breadth `
  --paths-config configs/qd-paths.local.json `
  --output reports/v4.3-domain-breadth
```

The strict 2022 discovery run passed the signal gate but failed Alpha Court: the best candidate
had net Sharpe -0.2709 and DSR 0.0139. See the [English result](docs/V4_3_RESULT.en.md) and
[V4.3 中文结果](docs/V4_3_RESULT.zh.md).

## V4.2 stability-first economic conversion

V4.2 freezes the twelve V4.1 representative mechanisms and replaces maximum full-year Sharpe
selection with four chronological 2023 subwindows, double-cost stress, adjacent-breadth
robustness and an explicit burden for regime wrappers. The selected mapping is evaluated on 2024
only after selection; 2025/2026 remain sealed.

```powershell
stephen-quant --db artifacts/v4.2-stable-conversion/registry.sqlite3 v4.2-stable-conversion `
  --paths-config configs/qd-paths.local.json `
  --output reports/v4.2-stable-conversion
```

See the [English V4.2 report](docs/V4_2_TEST_REPORT_EN.md) and
[V4.2 中文报告](docs/V4_2_TEST_REPORT_ZH.md). Generated artifacts and local paths remain
gitignored.

## V4.1 semantic A-share alpha search

V4.1 adds a 288-candidate semantic search grammar, IC-to-economic-shape diagnostics,
separate `BUY` / `AVOID` / `TIMING` mappings, prior-information regime states, and
A-share-specific price, auction, fund-flow, margin and limit-event mechanisms. The frozen
research sequence remains 2022 discovery, 2023 usage selection and 2024 retrospective shadow;
2025/2026 remain sealed.

```powershell
stephen-quant --db artifacts/v4.1-semantic-alpha/registry.sqlite3 v4.1-alpha-search `
  --paths-config configs/qd-paths.local.json `
  --output reports/v4.1-semantic-alpha
```

The local path file and generated reports remain gitignored. See the
[English V4.1 report](docs/V4_1_TEST_REPORT_EN.md) and
[V4.1 中文报告](docs/V4_1_TEST_REPORT_ZH.md) for the frozen real-data result.

V4.0 completes the single-user OHLCV research and historical paper-trading platform. It expands
the frozen grammar to 990 candidates, reduces them to 218 effective mechanism clusters, applies
family quotas and decision-local residualization, searches cost-aware portfolio conversion on
2023 only, shadows the frozen choice on 2024, records 1,239 Trials, and emits a sealed release
manifest plus 990 research-memory nodes. The honest decision is `NO_DEPLOYABLE_ALPHA`: the
120-session reversal candidate confirms strongly in 2023 but produces negative excess performance
in 2024. A 222-period aggregate paper-broker ledger records cash, orders, fills and NAV without
submitting live orders. The 2025/2026 windows remain sealed.

```powershell
stephen-quant --db artifacts/v4.0-ohlcv-platform/registry.sqlite3 v4-ohlcv-platform `
  --paths-config configs/qd-paths.local.json `
  --output reports/v4.0-ohlcv-platform
```

See the [English V4.0 technical report](docs/V4_0_TECHNICAL_REPORT_EN.md) and
[V4.0 中文技术报告](docs/V4_0_TECHNICAL_REPORT_ZH.md).

V3.1 adds a predeclared 630-candidate OHLCV discovery grammar and a layered Alpha Court. It
separates factor efficacy from long-only feasibility, freezes a Top 60 on 2022, confirms only that
shortlist on 2023/2024, supports a single survivor, audits purged/embargoed CPCV, and reports DSR,
PBO, placebo tests and every holding-period offset. The current honest result is
`RESEARCH_CANDIDATE`, not a deployable alpha: 120-session price reversal has stable positive
RankIC, but fails multiplicity-adjusted DSR and cost-aware economic gates.

```powershell
stephen-quant --db artifacts/v3.1-price-discovery/registry.sqlite3 v3-price-discovery `
  --paths-config configs/qd-paths.local.json `
  --output reports/v3.1-price-discovery
```

See the [English V3.1 result](docs/V3_1_PRICE_DISCOVERY_RESULT_EN.md) and
[V3.1 中文结果](docs/V3_1_PRICE_DISCOVERY_RESULT_ZH.md). Detailed machine-readable and bilingual
runtime reports remain under the gitignored output directory.

V3.0 adds a preregistered continuous factor-research loop over 2022–2024 daily bars, fund flow,
auction, margin, chip-distribution and limit-event data. Five mechanism epochs were tested with
immutable Alpha Court, Sharpe, drawdown, cost and multiplicity gates. The honest current result is
`NO_ALPHA_IN_CURRENT_MECHANISM_SET`; 2025/2026 were never opened.

Each epoch is replayed from a gitignored local path configuration, for example:

```powershell
stephen-quant --db artifacts/v3.0-continuous.sqlite3 qd-auto-discover `
  --paths-config configs/qd-paths.local.json `
  --manifest configs/v3.0-continuous-epoch-5.json `
  --ingested-at 2024-12-31T23:59:59+08:00 `
  --output reports/v3.0-continuous-epoch-5
```

See [V3.0 result](docs/V3_0_CONTINUOUS_RESEARCH_RESULT_EN.md),
[V3.0 中文结果](docs/V3_0_CONTINUOUS_RESEARCH_RESULT_ZH.md), and the bilingual specifications.

The PIT-Lite daily-bar industry audit can be replayed with the gitignored local path configuration:

```powershell
stephen-quant qd-industry-proxy-audit --paths-config configs/qd-paths.local.json
```

It reads only explicit 2022–2024 date partitions and emits a frozen manifest, JSON and bilingual
Markdown. See `docs/PIT_LITE_INDUSTRY_PROXY_AUDIT_EN.md` and the Chinese companion for the current
evidence and usage restriction.

The bounded V2.9 PIT-Lite research operation is replayed from a gitignored local path config:

```powershell
stephen-quant --db artifacts/issue-98-pit-lite.sqlite3 pit-lite-research `
  --paths-config configs/qd-paths.local.json `
  --config configs/v2.9-pit-lite-research.json `
  --ingested-at 2025-01-02T00:00:00+08:00
```

Its current decision is `NO_ROBUST_ALPHA_POPULATION`; see the bilingual PIT-Lite research result.

## V2.8 point-in-time data-source upgrade

V2.8 promotes the tested data-maintenance and point-in-time staging foundation from
`data-test` into the main release line. It adds deterministic raw-byte inventory and manifests,
single-user local unlock and append-only operation ledgers, QD/AlphaPai PIT staging, finance
revision chains, industry and corporate-action contracts, authoritative announcement-document
binding, and source-completion reporting.

The 2022–2024 announcement-document quarantine is resolved with byte-verified source files and
deterministic replay. The release still fails closed for missing authoritative historical
stock-level industry membership and complete corporate-action/share-capital source staging.
Consequently, Gate 5 remains blocked and the 2025/2026 research restrictions remain unchanged.

See the [English V2.8 release audit](docs/V2_8_RELEASE_AUDIT_EN.md) and
[中文 V2.8 发布审计](docs/V2_8_RELEASE_AUDIT_ZH.md).

The label-free semantic search prototype improves candidate design while the remaining PIT
sources are acquired. It introduces five-layer candidate identity, deterministic tombstone and
duplicate gates, an offline Remote/Search Ledger, and synthetic train/validation/sealed-test
benchmarks without reading real returns:

```powershell
stephen-quant v2-label-free-search `
  --config configs/v2.8-label-free-semantic-search.json `
  --output reports/v2.8-label-free-semantic-search
```

See the [English specification](docs/LABEL_FREE_SEMANTIC_SEARCH_SPEC_EN.md),
[中文规格](docs/LABEL_FREE_SEMANTIC_SEARCH_SPEC_ZH.md),
[English result](docs/LABEL_FREE_SEMANTIC_SEARCH_RESULT_EN.md), and
[中文结果](docs/LABEL_FREE_SEMANTIC_SEARCH_RESULT_ZH.md). This prototype does not authorize
real-return factor search or change the #92/#93/#84 boundaries.

## V2.7 integrity-first reset

M0 records rejected factor families and seals research-window governance. M1 adds a source-specific point-in-time readiness audit without reading raw directories or observing returns:

```powershell
stephen-quant v2-pit-readiness --config configs/v2.7-m1-pit-readiness.json --output reports/v2.7-m1
```

The current M1 decision authorizes only price-derived M2 controls on the frozen 2022–2024 evidence. Stock-level industry membership, corporate-action events, expectation revisions, and unproven revision histories remain fail-closed.

M2 implements causal, fold-local price controls and deliberately reports a partial model:

```powershell
stephen-quant v2-risk-controls --config configs/v2.7-m2-price-risk.json --output reports/v2.7-m2
```

The M2 engineering gate does not observe candidate returns and does not make the partial model eligible for Alpha Court.

An **integrity-first** quantitative research system inspired by three research directions:

1. LLM-assisted factor/state/reward design;
2. reinforcement learning for portfolio allocation;
3. strict financial-ML evaluation integrity to detect leakage and backtest overfitting.

The project deliberately started with **V1.0: Evaluation Integrity Foundation** before building alpha models. **V2.0** now adds a budgeted, auditable autonomous research loop in shadow mode; it does not promise profitable alpha or permit live autonomous trading.

> **Release status: research preview.** V2.x is disabled for autonomous live trading, has not
> passed Alpha Court, and must not be represented as a proven profitable strategy. The 2025
> validation and 2026 final-test windows remain sealed.

**V2.1** connects that loop to the real QD point-in-time dataset. It adds a fail-closed
readiness gate, 13 mechanism-distinct factor families, a bounded 26-candidate search, reliability
controls, offline replay, and bilingual reports while keeping 2025/2026 sealed.

```powershell
stephen-quant --db "artifacts\v2.1-real.sqlite3" v2-real-research `
  --paths-config "configs\qd-paths.local.json" `
  --config "configs\v2.1-real-research.json" `
  --mode research `
  --ingested-at "2026-08-17T00:00:00+08:00" `
  --output "reports\v2.1-real-research"
```

Machine-local paths, raw data, generated reports, and registries remain ignored. See the
[English V2.1 specification](docs/V2_1_SPEC_EN.md), [中文 V2.1 规格](docs/V2_1_SPEC_ZH.md),
[English validation](docs/V2_1_RESULT_EN.md), and [中文验证结果](docs/V2_1_RESULT_ZH.md).

**V2.2** is a deliberately narrow research epoch: it freezes the V2.1 signal and varies only
portfolio breadth across Top-5/10/15/20. The real-data result is
`REJECT_NO_IMPROVEMENT`: broader portfolios reduced drawdown but did not improve Sharpe, so
V2.1 remains the reference and the sealed 2025/2026 windows stay unopened.

```powershell
stephen-quant --db "artifacts\v2.2-breadth.sqlite3" v2-portfolio-breadth `
  --paths-config "configs\qd-paths.local.json" `
  --config "configs\v2.2-portfolio-breadth.json" `
  --mode research `
  --ingested-at "2026-08-17T00:00:00+08:00" `
  --output "reports\v2.2-portfolio-breadth"
```

See the [English V2.2 specification](docs/V2_2_SPEC_EN.md),
[中文 V2.2 规格](docs/V2_2_SPEC_ZH.md),
[English result](docs/V2_2_RESULT_EN.md), and
[中文结果](docs/V2_2_RESULT_ZH.md).

**V2.3** freezes the same signal and Top-5 portfolio, then removes same-day exposure to
five-day price momentum and `log(ADV20)`. It improves research-period net Sharpe from 0.4266
to 0.6028 and maximum drawdown from -28.42% to -21.12%, but remains research-only because
moment-corrected trial-aware DSR is 0.6044 rather than the required 0.95. Industry neutralization remains
blocked until point-in-time stock-industry membership is available.

```powershell
stephen-quant --db "artifacts\v2.3-style.sqlite3" v2-style-residualization `
  --paths-config "configs\qd-paths.local.json" `
  --config "configs\v2.3-style-residualization.json" `
  --mode research `
  --ingested-at "2026-08-17T00:00:00+08:00" `
  --output "reports\v2.3-style-residualization"
```

See the [English V2.3 specification](docs/V2_3_SPEC_EN.md),
[中文 V2.3 规格](docs/V2_3_SPEC_ZH.md),
[English result](docs/V2_3_RESULT_EN.md), and
[中文结果](docs/V2_3_RESULT_ZH.md).

**V2.4** freezes the V2.3 formula and audits calendar-year and rolling 12-period stability.
Engineering and replay gates pass, so the platform is ready for a disabled-by-default
`research-preview` release. Alpha gates do not pass: 2023 Sharpe is -0.4145, the weakest
rolling Sharpe is -0.5095, and DSR is 0.6029.

```powershell
stephen-quant --db "artifacts\v2.4-temporal.sqlite3" v2-temporal-stability `
  --paths-config "configs\qd-paths.local.json" `
  --config "configs\v2.4-temporal-stability.json" `
  --mode research `
  --ingested-at "2026-08-17T00:00:00+08:00" `
  --output "reports\v2.4-temporal-stability"
```

See the [English V2.4 specification](docs/V2_4_SPEC_EN.md),
[中文 V2.4 规格](docs/V2_4_SPEC_ZH.md),
[English result](docs/V2_4_RESULT_EN.md),
[中文结果](docs/V2_4_RESULT_ZH.md), and the
[release audit](docs/V2_4_RELEASE_AUDIT_EN.md) / [发布审计](docs/V2_4_RELEASE_AUDIT_ZH.md).

**V2.5** preregisters a zero-threshold market-regime definition and exactly two portfolio-use
policies on the consumed 2022–2024 research data. `risk_off_cash` improves net Sharpe to
0.8537 and drawdown to -8.87%, while momentum fallback fails. The result remains research-only:
strategy-family PBO is 46.83%, DSR is 66.72%, and the top 10% of absolute period returns
contribute 69.98%.

```powershell
stephen-quant --db "artifacts\v2.5-regime.sqlite3" v2-regime-portfolio `
  --paths-config "configs\qd-paths.local.json" `
  --config "configs\v2.5-regime-portfolio.json" `
  --mode research `
  --ingested-at "2026-08-17T16:30:00+08:00" `
  --output "reports\v2.5-regime-portfolio"
```

See the [English V2.5 specification](docs/V2_5_SPEC_EN.md),
[中文 V2.5 规格](docs/V2_5_SPEC_ZH.md),
[English result](docs/V2_5_RESULT_EN.md),
[中文结果](docs/V2_5_RESULT_ZH.md), and the
[release audit](docs/V2_5_RELEASE_AUDIT_EN.md) / [发布审计](docs/V2_5_RELEASE_AUDIT_ZH.md).

**V2.6** performs the preregistered, one-shot 2025 validation of V2.5's frozen
`risk_off_cash` policy. The data-readiness gate passed and exactly one inferential trial was
registered, but the policy lost 11.87%, produced a -0.1854 annualized net Sharpe and a
-25.05% drawdown. The decision is therefore `VALIDATION_FAIL_STOP`: the candidate is
rejected, retries are blocked, and the 2026 final-test window remains sealed.

See the [English V2.6 specification](docs/V2_6_SPEC_EN.md),
[中文 V2.6 规格](docs/V2_6_SPEC_ZH.md),
[English result](docs/V2_6_RESULT_EN.md),
[中文结果](docs/V2_6_RESULT_ZH.md), and the
[release audit](docs/V2_6_RELEASE_AUDIT_EN.md) / [发布审计](docs/V2_6_RELEASE_AUDIT_ZH.md).

**V2.7 M0** starts the post-validation research reset without opening any market-data
window. It records the V2.6 failure as an append-only family tombstone, marks 2025 as
consumed validation evidence, keeps 2026 sealed, and adds an explicit-manifest information
firewall. The rejected family and wrapper/horizon descendants are stopped deterministically,
while a genuinely distinct mechanism fixture remains eligible for a future data-readiness audit.
No new inferential trial or remote-model request is created.

See the [English V2.7 M0 specification](docs/V2_7_M0_SPEC_EN.md),
[中文 V2.7 M0 规格](docs/V2_7_M0_SPEC_ZH.md),
[English result](docs/V2_7_M0_RESULT_EN.md),
[中文结果](docs/V2_7_M0_RESULT_ZH.md), and the
[release audit](docs/V2_7_M0_RELEASE_AUDIT_EN.md) /
[发布审计](docs/V2_7_M0_RELEASE_AUDIT_ZH.md).

## V2.0 shadow-mode validation

V2.0 connects falsifiable hypotheses, a typed safe-DSL compiler, duplicate and cheap-diagnostic gates, marginal portfolio-value ranking, structured failure learning, frozen research epochs, dual ledgers and offline replay.

Run the frozen engineering validation in one command:

```bash
stephen-quant --db artifacts/v2-shadow.sqlite3 v2-shadow-validate \
  --config configs/v2.0-m5-shadow.json \
  --output reports/v2.0-shadow
```

The command uses only a synthetic research fixture. It keeps the 2025 validation and 2026 final-test windows sealed, makes no model request, connects to no execution service, and writes JSON plus Chinese/English reports under git-ignored paths. Use `--dry-run`, `--kill-switch`, or `--replay-manifest <path>` for the corresponding fail-closed modes.

See the [Chinese specification](docs/V2_M5_SPEC_ZH.md), [English specification](docs/V2_M5_SPEC_EN.md), and Issue #36 for the implementation contract.

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

## V1.8.21 preregistered portfolio usage

V1.8.21 compares six frozen signal-to-portfolio definitions at CNY
1m/3m/5m/10m/20m, registers every mapping/NAV pair as an inferential Trial, and preserves 2025/2026
as sealed windows. The output is research-only and supplies the first versioned reference portfolio
for V2.0; it is not fresh out-of-sample evidence.

```powershell
stephen-quant --db "artifacts\qd-v1.8.21.sqlite3" qd-auto-discover `
  --paths-config "configs\qd-paths.local.json" `
  --manifest "configs\v1.8.21-search.json" `
  --ingested-at "2026-08-17T12:45:00+08:00" `
  --output "reports\qd-v1.8.21"
```

See the [English specification](docs/V1_8_21_SPEC_EN.md),
[中文设计](docs/V1_8_21_SPEC_ZH.md),
[English result](docs/V1_8_21_RESULT_EN.md), and
[中文结果](docs/V1_8_21_RESULT_ZH.md).

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

### V1.8.18 flow stability and capacity stress

V1.8.18 adds a frozen 20-day flow-divergence candidate family, prior-information market-regime and ADV diagnostics, fail-closed point-in-time industry grouping, and preregistered 1%/5%/10% participation stress tests. The real 2022–2024 run passed engineering acceptance but was rejected by the Alpha Court; the 2025/2026 sealed windows remain unopened.

- [中文规格](docs/V1_8_18_SPEC_ZH.md) / [English specification](docs/V1_8_18_SPEC_EN.md)
- [中文结果](docs/V1_8_18_RESULT_ZH.md) / [English results](docs/V1_8_18_RESULT_EN.md)

### V1.8.19 NAV capacity frontier

V1.8.19 tests CNY 1m/3m/5m/10m/20m at 1%/5%/10% ADV participation, using CNY 3m as the real-capital reference and CNY 20m as a hard ceiling. The 2022–2024 real run found no ADV-capacity clipping through CNY 20m, but the candidate remains rejected by the Alpha Court.

- [中文规格](docs/V1_8_19_SPEC_ZH.md) / [English specification](docs/V1_8_19_SPEC_EN.md)
- [中文结果](docs/V1_8_19_RESULT_ZH.md) / [English results](docs/V1_8_19_RESULT_EN.md)

### V1.8.20 factor incremental value and return attribution

V1.8.20 residualizes the flow-divergence parent against price reversal and decision-time liquidity, decomposes daily decile returns, and emits structured stop/redesign reasons. The real run finds residual RankIC of 0.085 but shows that most value comes from avoiding the bottom decile; weak long-only Sharpe and excessive drawdown still force rejection.

- [中文规格](docs/V1_8_20_SPEC_ZH.md) / [English specification](docs/V1_8_20_SPEC_EN.md)
- [中文结果](docs/V1_8_20_RESULT_ZH.md) / [English results](docs/V1_8_20_RESULT_EN.md)

## Principle

> LLM discovers → statistics verifies → RL allocates → evaluation attacks.
