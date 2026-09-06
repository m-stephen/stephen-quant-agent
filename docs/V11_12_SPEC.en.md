# V11.12 Frozen Allocation Execution-Evidence Contract

Issue184; preregistration5560402441; independently stacked on PR189.

## Objective

Identify execution-evidence gaps in the frozen V11.11 stable low-risk observation.
Do not tune historical parameters or alter the card,policy,targets or old results.
This is not a raw-share backtest and cannot grant Alpha eligibility.

## Fixed scope

- Two already frozen82bps,CNY3m,2023–2024 accounts:stable_lowrisk and lowvol.
- Raw prices from the same daily.parquet snapshot;SHA-256 validation precedes use.
- Single buy tickets rounded down:ordinary SH/SZ main-board and ChiNext100-share
  multiples;STAR minimum200,increment1. Unsupported codes/dates or missing prices
  remain explicit,never silently treated as executable.
- Fixed6bps commission with hypothetical CNY5 minimum on the unchanged tickets;
  the user's broker schedule is unconfirmed.
- Prior-close holdings with adjustment changes or missing prices generate private
  review keys. No dividend/split/rights records are inferred from factors.
- Two explicit unfitted native diagnostic Trials increase3320→3322;new accounts0,
  new fits0. Exclusive claims,retained failures,no repeated old operations.

## Inference limits

Cumulative rounding is neither lost return nor daily idle cash. Summed fee gaps
are not NAV corrections. Adjusted fractional units are not raw shares. An adjustment
factor is not a corporate-event cashflow ledger;no change cannot prove event absence.
Odd-lot sales,T+1 inventory,payment dates,dividend tax and real opening liquidity
remain unverified.2025/2026 remain unread;historical research cannot become new OOS;
Court thresholds remain unchanged.

## Verification and reproducibility

17new tests plus full suite;independent SQL fees and buy-size maximality/budget checks,
frozen-account hashes,complete held-review-key sets and native SQLite reconciliation.
Bilingual reports,JSON and an aggregate-only notebook accompany the private evidence.
Use a gitignored configs/execution-evidence.local.json based on the example.
Never rerun the completed epoch-001. The independent verifier also writes exclusive
outputs;use a separate audit output for another review,not an overwrite. The notebook
only rechecks public aggregates without a new market experiment.

## Rule sources

[SSE STAR investor education](https://edu.sse.com.cn/tib/),
[SZSE2023 main-board FAQ](https://investor.szse.cn/knowledge/qa/t20230306_599093.html),
[SSE order-quantity controls](https://www.sse.com.cn/lawandrules/guide/stock/jyglywznylc/tz/c/c_20230209_5716007.shtml).
Checked September6,2026;the implemented scope is2023–2024,not automatically later rules.
