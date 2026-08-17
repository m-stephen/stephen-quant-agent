# V2.2: Frozen-Signal Portfolio Breadth Research Epoch

## Objective

V2.2 tests one bounded question: can a broader portfolio improve the executable risk-adjusted
performance of the frozen V2.1 signal? The signal schema, source snapshot, research window,
cost model, capital, holding period, and selection rule are fixed before the run. This is a
portfolio-construction experiment, not a new factor search.

## Frozen boundary

- Signal: `flow_confirmation_20_20d`, fingerprint
  `13f4ddc002cb8f0bb59f057895f3fe8ca89eeb4a819820c11041f043ac8c117e`.
- Source snapshot: `99b037baf97721ab438c54392b419ea96c994b68ef616a20b5fa234223928b23`.
- Research window: 2022-01-04 through 2024-12-31; 2025 and 2026 remain sealed.
- Reference NAV: CNY 3 million; V2.1 commissions, taxes, slippage, impact, and capacity rules.
- Holding period: 20 trading days.
- Single variable: `top_k` in 5, 10, 15, and 20.
- Selection: highest raw net Sharpe, with smaller `top_k` as the deterministic tie-breaker.
- Multiplicity: 37 inherited trials plus four breadth trials and one reverse-rank negative
  control, for 42 cumulative trials.

The prior evidence fields are bound into a canonical SHA-256 hash. Top-5 must reproduce the
V2.1 annualized net Sharpe, net return, and maximum drawdown to machine precision or the run
fails closed.

## Pre-registered gates

The epoch accepts a breadth upgrade only if all of the following hold:

1. selected breadth is not Top-5;
2. annualized net Sharpe is at least 0.5265716607, a 0.10 improvement over V2.1;
3. maximum drawdown is no worse than -25%;
4. net return is positive and no capacity clipping occurs;
5. reverse-ranking annualized Sharpe is non-positive;
6. both placebo p-values are at most 0.05, inherited PBO is at most 0.20, and DSR is at least
   0.95;
7. the 2025 validation and 2026 final-test windows remain unopened.

Any failed gate produces a rejection, not a relaxed threshold or a second selection rule.

## Operating modes and evidence

- `dry-run`: validate frozen configuration and local path keys without reading research data or
  mutating the registry.
- `research`: register five trials, run the four breadth portfolios and reverse control, rerun
  placebos, calculate DSR, and write JSON plus bilingual Markdown.
- `replay`: verify artifact hashes and cumulative trial count without local data paths.
- `kill`: stop before data or registry access.

Machine-local paths, raw data, registries, and generated reports remain git-ignored.
