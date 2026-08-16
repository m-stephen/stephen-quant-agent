# V1.8.5 — QD date-partitioned daily data

V1.8.5 lives on the long-running `data-test` branch. It adds a read-only adapter for the private
QD A-share dataset stored as one `YYYYMMDD.csv` file per trading session.

## Data contract

The adapter requires an explicit fixed instrument universe and these source columns:

| Canonical field | QD field | Conversion |
| --- | --- | --- |
| trade date | `日期` | filename and row must agree |
| instrument | `代码` | uppercase exchange-suffixed code |
| OHLC | `开盘价/最高价/最低价/收盘价` | raw CNY price |
| volume | `成交量(手)` | multiply by 100 to shares |
| amount | `成交额(千元)` | multiply by 1,000 to CNY |
| adjustment | `复权因子` | optional point-in-time back-ratio price scale |

Only `none` and `back_ratio` price modes are accepted. Front-adjusted series and vendor-computed
technical factors are deliberately excluded because historical front adjustment may be rewritten
after later corporate actions. Volume and amount remain unadjusted.

## Integrity rules

- Snapshot only the exact daily partitions from train start through the first session after test
  end; unrelated archives and later dates are not included.
- Reject schema drift, duplicate instrument-date bars, invalid OHLC, non-positive adjustment
  factors, row/filename date disagreement, and missing requested instruments.
- Keep the fixed-universe survivorship warning in the audit.
- Treat missing daily bars as suspensions or source gaps; the existing strict-panel evaluator must
  reject them rather than silently forward-fill prices.
- Register the Trial before factor evaluation and retain explicit transaction costs.

## CLI

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

This run is an engineering and data validation result, not evidence of live alpha. A historical
point-in-time universe is still required before a strategy becomes research-claim eligible.
