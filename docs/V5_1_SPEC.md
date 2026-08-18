# V5.1 Frozen Candidate Reliability Audit

## Objective

Audit the two-factor V5.0 candidate without changing its formula, breadth, horizon, universe,
capital, or revealed 2022–2024 evidence. V5.1 is a falsification release, not another search.

## Frozen candidate

- `chip_cost_gap_reversal_5_20_20d`
- `flow_price_divergence_20_20d`
- Equal cross-sectional rank ensemble
- BUY top 50, 20-session holding horizon, CNY 3,000,000 NAV
- 2021 is lookback only; 2022–2024 is reused development evidence

## Predeclared audit grid

Exactly four signal representations are evaluated under exactly three execution scenarios,
creating 12 inferential Trials. No cell may be selected as a replacement factor.

Signal representations:

1. frozen raw ensemble;
2. raw ensemble residualized against prior-known size tier, liquidity tier, 20-session momentum,
   and 20-session volatility;
3. raw ensemble demeaned by the daily-file industry label;
4. style-residual ensemble demeaned by the daily-file industry label.

Execution scenarios:

1. standard: commission 3 bps, sell tax 5 bps, slippage 5 bps, impact 10 bps,
   participation 5%;
2. double cost: commission 6 bps, sell tax 10 bps, slippage 10 bps, impact 20 bps,
   participation 5%;
3. conservative: commission 3 bps, sell tax 5 bps, slippage 15 bps, impact 25 bps,
   participation 2%.

## Gates

- All feature timestamps must precede the execution/label timestamp.
- Raw standard and raw conservative incremental returns must be positive.
- Raw standard and raw conservative must have at least 15 positive offset paths out of 20.
- Style-residual standard incremental return must be positive and 2023/2024 RankIC must be
  positive.
- Capacity clipping must be zero at CNY 3,000,000.
- DSR >= 0.95, inherited candidate-selection PBO <= 0.05, and both current placebo p-values
  <= 0.05.
- A historical-vintage or immutable-source proof must exist for every revision-prone source.

The daily-file industry field is `B_CURRENT_LABEL_PROXY`: it is a diagnostic control only and
cannot satisfy the authoritative historical-industry requirement. The chip source has an
end-of-day availability clock but no historical vintage proof; unless such proof is supplied,
`chip_revision_provenance_unverified` is a blocking finding.

## Decision vocabulary

- `RELIABLE_ALPHA_CANDIDATE`: every gate passes; still requires genuinely new forward data.
- `FORWARD_CANDIDATE_WITH_BLOCKERS`: economic/path evidence survives, but one or more integrity
  or multiplicity gates fail.
- `REJECT_CANDIDATE`: economic/path evidence fails the frozen stress or attribution gates.

V5.1 must never report deployable or proven Alpha from the reused 2022–2024 window.
