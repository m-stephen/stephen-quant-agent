# V7.0 Final Test Report

## Conclusion

System status: `OPERATIONAL`. Alpha status: `NO_VALIDATED_ALPHA`. Not deployable.

V7.0 moves the project from a hand-authored factor list to an engineering loop that can generate,
type-check, count, screen and falsify candidates automatically. This run did not produce a factor
that passed the complete Alpha Court. The 2025 and 2026 labels remained sealed.

## Real research result

- Window: 2022–2024; point-in-time dynamic universe capped at 300 stocks per date.
- Generated: eight formulas in both directions, for 16 candidates and 16 training Trials.
- Training shortlist: six candidates entered CPCV; 22 Trials were recorded (16 training and six
  CPCV).
- Strongest training candidate: inverse 60-session close volatility, a low-volatility ranking, with
  mean RankIC of approximately 0.1092.
- Other shortlisted mechanisms included 60/20/5-session reversal and inverse amount trend.
- The first run produced identical averages for every CPCV path. The old logic misleadingly
  returned PBO=0 and `PASS_SIGNAL_GATE`.
- V7.0 now fails this case closed as `REJECT_DEGENERATE_CPCV_PATHS`. The result is a research clue,
  not an Alpha.

## Engineering validation

The one-command pipeline covers semantic routing, typed DSL, direction-complete proposals, staged
screening, the search controller, portfolio objective, research memory, Alpha Court protocol and
forward-shadow protocol. Reports do not contain machine-local absolute data paths. Snapshot,
candidate, Trial and CPCV-manifest evidence remain reproducible.

The next step is to define non-degenerate temporal/OOS scoring for fixed factors, then test the
low-volatility/reversal family under standard and doubled costs, placebo, DSR and CNY 3 million
capacity gates. Thresholds must not be weakened.
