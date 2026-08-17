# V3.0 Continuous Factor Research Result

## Decision

`NO_ALPHA_IN_CURRENT_MECHANISM_SET`

Across five preregistered epochs in the frozen 2022–2024 research window, no candidate jointly
passed Alpha Court, annualized net Sharpe 0.50, 25% maximum drawdown, cost-aware walk-forward and
cumulative multiplicity gates. The 2025 validation and 2026 final-test windows were never opened.
This does not claim that no market alpha exists; it means that the current data, mechanisms,
horizon and portfolio protocol did not produce acceptable evidence.

## Frozen boundary

- Research: 2022-01-04 through 2024-12-31; primary horizon 20 sessions.
- CNY 3m initial NAV with commission, stamp duty, slippage, impact and a 5% ADV cap.
- Gates: training RankIC >= 0.005; CPCV >= 0.015; positive paths >= 8; PBO <= 0.05;
  both placebo p <= 0.05; DSR >= 0.95; annualized net Sharpe >= 0.50; drawdown >= -25%.
- Multiplicity: 52 inherited V2.9 trials plus 27 V3.0 ledger trials, or 79 cumulatively.
- Every V3.0 trial has a result, including three failed engineering trials from the first sparse-
  event attempt.

## Epoch results

| Epoch | New mechanism | Screen/CPCV | Final result |
|---|---|---|---|
| 1 | Financing/large-flow acceleration and auction absorption | Two entered CPCV; PBO 0; both 10/10 positive paths | Auction absorption won, but net Sharpe -0.1323, drawdown -66.79%, DSR 0.1078 and WF Sharpe -0.4793; rejected |
| 2 | Liquidity, financing crowding and cash absorption | Two entered CPCV; PBO 0; both 10/10 positive paths | Financing crowding won, but net Sharpe -0.7617, drawdown -64.62%, DSR 0.0100 and WF Sharpe -0.1489; rejected |
| 3 | Chip-distribution levels | Only profit-crowding reversal survived, RankIC 0.04179 | Fewer than two synchronized candidates; CPCV refused |
| 4 | Chip-distribution dynamics | All three RankIC values were negative | Falsified in the training screen |
| 5 | Densified limit-up events | RankIC -0.03825, -0.10318 and -0.06613 | Falsified in the training screen |

Epochs 1 and 2 both had placebo p-values of 0.005/0.005, which only indicates that the signals were
not simple random permutations. Cost-aware performance, DSR, walk-forward and drawdown failed
together, so neither could pass. Epochs 3–5 did not meet the prerequisite for a full court and did
not consume sealed evidence or present a single attractive RankIC as alpha.

## Engineering delivered

- Five immutable candidate configs, mechanism-epoch routing and a 52-trial historical offset.
- Explicit Sharpe and maximum-drawdown gates in the final Alpha Court execution decision.
- Chip-distribution fields, unit normalization, EOD timing and multisource factor support.
- A 开盘啦 limit-event adapter with label filtering, deterministic duplicate aggregation, dense
  non-event zeros, null preservation for measured-event gaps, next-open execution and snapshots.
- Constant cross-sections contribute no fabricated correlation while failed attempts remain in the
  append-only trial ledger.
- Bilingual JSON/Markdown output, gitignored local paths and sealed 2025/2026 controls.

## Next research boundary

Do not flip Epoch 4/5 signs or continue tuning 5/20-day windows. A new preregistered issue should
add genuinely new point-in-time evidence or mechanism semantics: corporate actions/share changes,
historical industry membership, analyst-estimate revisions, announcement/research text events, or
an independent risk-neutral portfolio protocol. The negative limit-event result may motivate a
new event-reversal hypothesis, but it must be registered as a new trial family rather than rewriting
this result.
