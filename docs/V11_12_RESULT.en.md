# V11.12 Execution Feasibility Audit

## 结论 / Finding

Retain the frozen allocation as an observation, not usable Alpha. Raw-ticket diagnostics reveal a small-rebalancing-order execution gap. No new account was simulated and no historical return was relabeled as a lot-executable return.

## 范围与定义 / Scope and definitions

Two frozen 82bps accounts,484 sessions in reused2023–2024,starting CNY3m. Only saved executed tickets and prior-close holdings are inspected; no stock selection, tuning or2025/2026 reads. Cumulative unallocated notional sums each original buy minus its raw-price-rounded ticket. Its denominator is cumulative buys,not capital,NAV,independent opportunities or return.

## 买入数量诊断 / Buy-ticket quantities

2,111/4,827 stable-allocation buys (43.73%) are below the minimum quantity; strict low-vol has 1,980/5,484 (36.11%). All buys have matched raw prices and supported SH/SZ rules. Small tickets do not imply a proportional return loss; the table reports ticket counts and notional diagnostics.

|Policy|Buys|Below minimum|Unallocated / buy notional|Extra commission CNY|Held factor changes|
|---|---:|---:|---:|---:|---:|
|lowvol|5,484|1,980|4.22%|23,739.13|415|
|stable_lowrisk|4,827|2,111|4.76%|26,998.52|352|

## 金额和最低佣金 / Notional and minimum commissions

Stable cumulative buys are CNY37,041,808.08;ticket-wise rounding leaves CNY1,764,248.10 (4.76%) unallocated,versus 4.22% for control. Assuming6bps commission with a CNY5 minimum adds CNY26,998.52/23,739.13 on the unchanged saved buy/sell tickets. The broker minimum is unconfirmed. Actual lot-account tickets would change;these are not loss estimates or direct NAV deductions.

## 公司行为复核范围 / Scoped event evidence

Prior-close holdings yield352 adjustment-change keys and35 missing-price keys for stable allocation;control has415/35. Their union is512keys across253stocks:477changes and35missing prices. A private itemized worklist avoids requiring whole-market completion first. Changes are review clues,not dividend/split/rights or payment-date records;no change does not establish event absence. Missing prices may reflect suspensions;none are imputed.

## 方法与质量验证 / Methods and QA

Snapshot,card and parent-account SHA-256 checks precede two explicitly unfitted native Trial reservations and parsed account/source reads;debt3320→3322. Independent SQL recomputes orders/fees,checks10,311buy tickets for quantity limits,maximal affordable sizing and raw-price reconciliation,reconstructs held review keys and checks SQLite.17new targeted tests pass;full suite828passed/1skipped. Public reports contain aggregates only;raw data,stock lists and local paths remain outside Git.

## 推断边界 / Inference limits

No physical-share inventory,odd-lot sale,T+1 inventory,dividend tax/payment/split/rights cashflow or real-opening-capacity proof is supplied. Catalog metadata contains SW industry tables but no corporate/action-named table;this does not prove every older staging source is empty. The allocation was selected post hoc;the old32.06% remains an adjusted fractional-share model return. This diagnostic runs no Alpha Court and issues no DSR/PBO or independent-evidence certificate.

## 下一步 / Next actions

Keep the card frozen. Next preregister a finite matched low-vol-style versus holding-stability comparison using existing data to separate turnover savings from predictive increment. Do not repeat completed stresses or block all research on whole-market PIT completion. Execution engineering is scoped to this worklist and raw-share/cash conservation,never fabricated events. Modified trading policies require new Trials and separate candidate identities;certification still needs independent evidence and full Court.

Sources: [SSE STAR](https://edu.sse.com.cn/tib/), [SZSE 2023](https://investor.szse.cn/knowledge/qa/t20230306_599093.html), [SSE quantity notice](https://www.sse.com.cn/lawandrules/guide/stock/jyglywznylc/tz/c/c_20230209_5716007.shtml). Local: docs/V11_12_RESULT.summary.json; scripts/verify_execution_evidence.py; immutable execution-evidence operation.

Notebook QA: code cells replayed sequentially in Python; native Jupyter kernel/nbformat unavailable in both installed runtimes. Widget schema validation recorded separately; visible/pixel QA deferred under the user's quiet-until-usable instruction.
