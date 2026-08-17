# V1.8.8 — Predeclared factor library

V1.8.8 lives on the long-running `data-test` branch. It expands the factor library before any new
validation run and adds a training-only redundancy screen. The purpose is to narrow hypotheses by
economic diversity, not to mass-search backtests.

## New definitions

| Factor | Category | Direction | Predeclared interpretation |
|---|---|---:|---|
| `mom_120_skip_20` | momentum | +1 | persistent movement excluding the most recent month |
| `trend_efficiency_20` | trend | +1 | directional movement relative to total path noise |
| `range_position_20` | trend | +1 | close location inside the trailing high-low range |
| `intraday_strength_20` | price action | +1 | persistent close-to-open strength |
| `volume_surprise_5_20` | volume | +1 | recent participation relative to its baseline |
| `signed_volume_mom_20` | volume | +1 | momentum confirmed by recent relative volume |
| `dollar_liquidity_20` | liquidity | +1 | log mean traded amount |
| `parkinson_vol_20` | risk | -1 | lower high-low range volatility |

All inputs are daily fields available after the prior close. A next-day 09:30 decision therefore
uses only point-in-time history. Each definition has an immutable `1.0.0` version, explicit minimum
observations, required fields, and direction.

## Catalog statuses

- `predeclared_unvalidated`: added in V1.8.8 and not yet judged by returns;
- `available_untested`: older seed definition that still needs its own Trial;
- `rejected_validation`: retained for lineage but excluded from candidate screening.

`ret_60@1.0.0` is `rejected_validation` because of the frozen V1.8.7 result. Renaming or slightly
altering it does not reset that evidence.

## Redundancy screen

`qd-factor-screen` evaluates direction-adjusted factor ranks on a declared training window and
computes the mean daily Spearman correlation for every pair. Pairs whose absolute correlation is at
least the declared threshold are reported as redundant candidates.

The screen:

- freezes and hashes the selected date partitions through the next-open boundary;
- excludes definitions unsupported by current QD fields and all rejected definitions;
- uses no forward-return metric for selection; and
- writes deterministic JSON and Markdown artifacts.

Correlation is a pruning diagnostic, not Alpha evidence. After economic and redundancy review, only
a small, explicitly chosen subset may receive new validation Trials. The 2026 final-test window
remains unopened.
