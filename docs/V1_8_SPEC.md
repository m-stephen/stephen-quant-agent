# V1.8 — QMT Data Adapter and End-to-End Backtest

V1.8 proves that the integrity, factor, registry, and portfolio layers can execute together on a
local Guojin QMT daily-bar export. It is an engineering and evaluation milestone, not evidence that
the included momentum baseline is profitable.

## Public/private boundary

The public repository contains only the adapter, schema, tests, and workflow. Raw QMT data, account
identifiers, credentials, installation paths, registry databases, and generated reports remain
local and are ignored by Git. CI deliberately does not require `xtquant` or a running QMT terminal.
At runtime, the optional exporter reads local market data only; trading/account integration remains
outside the public project.

### Native QMT cache conversion

A QMT installation may store data in proprietary binary form instead of CSV. The observed layout is:

```text
datadir/
  SH|SZ|BJ/
    86400/*.DAT                  daily bars
    60/*.DAT                     one-minute bars
    300/*.DAT                    five-minute bars
    0/<instrument>/<date>.dat    tick/detail data
  DividData/*.ldb                corporate-action LevelDB data
```

These files are not decoded directly. V1.8.1 dynamically loads the installation's official
Python-compatible `xtquant` package and calls `xtdata.get_local_data` with `period="1d"`,
`fill_data=False`, and server reads disabled by that API. The QMT client must already be logged in
and its quote/Python service must be running. The exporter never starts the client, downloads
history, subscribes to quotes, accesses a trading account, or places orders.

The exporter accepts an explicit comma-separated stock list, a UTF-8 stock-list file, or a QMT
sector. It writes to a temporary file, validates that file through the canonical V1.8 adapter, and
only then atomically moves it to the destination. Existing destinations are refused unless the
operator explicitly supplies `--overwrite`. Empty instruments and partially corrupt bars fail;
fully unavailable zero/NaN bars are omitted and counted so the later strict-panel backtest can
reject non-executable windows rather than invent prices.

## Input contract

Input is one long-form daily CSV: one row per instrument and trade date. UTF-8/UTF-8-BOM and
GB18030 are supported. Required canonical fields and common aliases are:

| Canonical field | Accepted examples |
| --- | --- |
| `trade_date` | `trade_date`, `date`, `datetime`, `time`, `日期`, `交易日期`, `时间` |
| `instrument` | `instrument`, `stock_code`, `code`, `symbol`, `证券代码`, `股票代码` |
| `open` | `open`, `开盘`, `开盘价` |
| `high` | `high`, `最高`, `最高价` |
| `low` | `low`, `最低`, `最低价` |
| `close` | `close`, `收盘`, `收盘价` |
| `volume` | `volume`, `vol`, `成交量` |
| `amount` | `amount`, `turnover_value`, `成交额`, `成交金额` |

Dates may be `YYYYMMDD`, ISO date/time, Unix seconds, or Unix milliseconds. Prices must be finite,
positive, and OHLC-consistent. Volume and amount must be finite and non-negative. Duplicate
instrument-date rows fail. The price-adjustment mode is mandatory metadata and is never inferred.

V1.8 uses a strict complete panel over the supplied universe. A missing instrument-date bar fails
instead of silently dropping a suspended, delisted, or unavailable security. The adapter reports
zero-volume bars and an explicit survivorship-bias warning.

## Point-in-time execution contract

For execution trading day `T`:

1. The factor uses bars ending at the close of `T-1`.
2. The signal and trailing average daily traded value become available at `T-1 15:01 Asia/Shanghai`.
3. Orders execute at the open of `T`.
4. The daily forward return is `open(T+1) / open(T) - 1`.
5. Portfolio rebalancing occurs every configured number of execution periods; holdings drift between rebalances.

The final test date therefore requires one later trading bar. Test observations never enter the
factor window for an earlier decision.

## Trial-first workflow

Each command performs:

```text
exact source-file snapshot
  -> experiment lookup/creation
  -> Trial registration
  -> CSV validation
  -> point-in-time factor observations
  -> net-of-cost Momentum Top-K backtest
  -> JSON/Markdown artifacts
  -> immutable Trial result
```

Validation and backtest failures are recorded as rejected Trial results. Related retries should use
the same `experiment_id`; a changed source snapshot is rejected rather than silently attached to an
existing experiment.

## Cost and output contract

Reports include commission, sell-only tax, slippage, square-root market impact, ADV participation
limits, funding clipping, turnover, net return, annualized return/volatility, Sharpe, and drawdown.
All assumptions are stored in Trial hyperparameters. The exact source file, data audit, JSON report,
and Markdown report are hash-linked through the registry.

## Known limitations

- Universe membership is user-supplied and may contain survivorship bias.
- V1.8 does not reconstruct historical index constituents, ST status, listings, or delistings.
- Limit-up/limit-down execution, lot size, minimum commission, dividends, and corporate-action
  verification are not modeled.
- A single sell-tax rate applies to the whole run; historical tax changes require separate windows.
- QMT adjustment semantics are declared by the operator and are not independently verified.
- The CLI evaluates a locked test window; it must not be repeatedly tuned against that window.

## Acceptance target

The shipped test suite runs a representative QMT-shaped panel through snapshot registration,
experiment and Trial creation, `ret_5` factor calculation, next-open Momentum Top-K execution,
cost accounting, artifact registration, and immutable success/failure results. A real performance
claim requires the operator's own frozen QMT export and a predeclared untouched test window.
