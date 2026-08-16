# QD A-share price-limit calculation

This document records the rule set used by `qd-daily-directory-1.2.0`. It is a point-in-time data
contract for conservative next-open execution, not a general exchange matching engine.

## Formula

For a stock with a daily price limit:

```text
upper limit = previous close × (1 + limit rate)
lower limit = previous close × (1 - limit rate)
```

The result is rounded half-up to the A-share minimum price tick of CNY 0.01. The daily open is then
compared with those calculated prices. An open at the upper limit blocks a modeled buy; an open at
the lower limit blocks a modeled sell.

The open itself does not determine the limit price. It determines whether the opening execution is
at the limit after the limit price has been calculated from the previous close.

## Board and historical rules

| Scope | Recognized code or marker | Limit |
|---|---|---:|
| Shanghai main board | `600`, `601`, `603`, `605` + `.SH` | 10% |
| Shenzhen main board | `000`, `001`, `002`, `003` + `.SZ` | 10% |
| ChiNext | `300`, `301` + `.SZ` | 20% |
| STAR Market | `688`, `689` + `.SH` | 20% |
| Beijing exchange | `.BJ`, or `4`/`8` prefix | 30% |
| Main-board ST before 2026-07-06 | name contains `ST` | 5% |
| Main-board ST from 2026-07-06 | name contains `ST` | 10% |
| ChiNext/STAR ST | board takes precedence over `ST` | 20% |
| IPO no-limit phase | normalized name starts with `N` or `C` | no limit |

The exchange rules state that IPO stocks have no daily price limit for their first five trading
days. `N` identifies the listing day and `C` is used by the supplied daily data during the later
no-limit phase. An authoritative listing-date join is preferable if the vendor ever stops carrying
those markers. Relisting, the first delisting-consolidation day, and exchange-specific exceptional
decisions remain outside this adapter's supported rule.

## Official sources

- [Shanghai Stock Exchange Trading Rules (2026 revision)](https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml): 10% general limit, first five IPO trading days without limits, previous-close formula, CNY 0.01 tick, and rounding rule.
- [Shenzhen Stock Exchange Trading Rules (2026 revision)](https://docs.static.szse.cn/www/lawrules/rule/trade/W020260424690713155663.pdf): 10% main board, 20% ChiNext, first five IPO trading days without limits, and previous-close formula.
- [SSE STAR Market trading explanation](https://www.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20190719_4866745.shtml): 20% STAR Market limit after the first five trading days.
- [SZSE ChiNext special-rule explanation](https://investor.szse.cn/knowledge/stock/chinext/t20200729_580056.html): 20% ChiNext limit after the first five trading days.
- [SSE 2026 main-board risk-warning change](https://www.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20260424_10816474.shtml): main-board ST limit changed from 5% to 10%, effective 2026-07-06.
- [SZSE 2026 risk-warning trading guide notice](https://www.szse.cn/lawrules/service/member/t20260630_621404.html): the revised main-board risk-warning arrangement took effect on 2026-07-06.
- [SZSE ChiNext risk-warning arrangement](https://www.szse.cn/disclosure/notice/general/t20200710_579459.html): ChiNext risk-warning shares use the 20% board limit.
