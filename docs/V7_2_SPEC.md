# V7.2 — Source-balanced Automatic Factor Discovery

## Objective

Search orthogonal continuous data sources after the V7.1 low-volatility candidate exceeded the
final PBO threshold, without retuning its window or direction.

## Frozen protocol

- Labels: 2022–2024 only; 2025/2026 remain sealed.
- Dynamic universe: at most 300 stocks per decision date.
- Candidate budget: 16 formula identities, both directions, 32 training Trials.
- Source-pair quotas: four daily, four fund-flow, three margin, four chip and one
  fund-flow-plus-margin formula.
- Within-source selection prefers distinct required-field signatures before window variants.
- Validation: V7.1 purged-fold train-winner/complementary-OOS PBO.

Every included source is content-hashed into the composite experiment snapshot. Missing alternative
observations remain null and fail the coverage gate rather than being interpreted as zero.

Auction and limit-event fields are excluded because they require an event-study engine. Industry
fields remain excluded until point-in-time stock-to-industry alignment exists. Neither class is
silently forced through the continuous-ranking evaluator.
