# V11.6 final test report

Engineering repairs delivered; no new validated Alpha in this epoch.

## Engineering checks

- Full local suite:702 passed,1 skipped; Ruff passed.
- The skipped case requires symbolic-link creation unavailable under this Windows permission context; no failed factor test was suppressed.
- Repaired gate direction, future exit-price eligibility, unused-field filtering, minute availability joins, daily accounting and statistical definitions.
- 96 account-window reconciliations passed; maximum balance residual CNY0.0000000005.
- An independent process replayed all96 accounts from frozen inputs. Every metric and target hash matched exactly;zero additional trials;SQLite registry byte hash unchanged.
- Synthetic audit:actual1/8-worker parity,24/24 first-place recovery,0/100 false positives (95% Wilson upper bound3.70%).
- Economic detection is not Court calibration:the raw-count DSR sensitivity rejects all24 strong planted signals; this limitation remains explicit.

## Frozen winner accounts

2023 selector: `low_volatility`. Identity: `4807b4173348b9b430a61e041d649a2fbe1be670de2bb39a61a7e749109edde9`.

Each year starts independently with CNY3m. Net of modeled costs. Benchmark:theoretical matched-availability equal weights, not CSI300 or a verified board-lot product.

| Year | Round-trip bps | Account return | Profit CNY | Benchmark return | Excess pp | Max drawdown |
|---|---:|---:|---:|---:|---:|---:|
| 2023 | 41 | 4.79% | 143,819.97 | 5.24% | -0.44 | -10.31% |
| 2023 | 82 | 1.02% | 30,660.83 | 4.85% | -3.82 | -11.70% |
| 2024 | 41 | 29.61% | 888,449.58 | 2.58% | 27.04 | -9.67% |
| 2024 | 82 | 25.10% | 752,859.43 | 2.16% | 22.94 | -10.67% |

## Statistical conclusion and limits

- DSR sensitivity=0.00000562; PBO diagnostic=0.55; family placebo p=1.0.
- Daily observations=242; effective=153; minimum CPCV training fold=17.
- 2023 positive mean active return: 0/24. 2024 positive total excess: 6/24 (post-hoc diagnostic count, not winner replacement).
- Train2022/select2023/contaminated diagnostic2024; no independent out-of-sample claim. Zero2025–2026 returned rows this epoch; previous exposure remains disclosed.
- Missing aligned historical candidate returns means DSR extrapolates current-family dispersion to raw debt. Smallest purged folds are short; PBO remains diagnostic.
- This compares24 controlled mechanism/baseline proposals including ridge and a stump; zero external LLM calls. Free-form autonomous discovery is not declared mature.
- Adjusted prices, fractional shares, fixed fees and ADV capacity are approximations, not board-lot/minimum-commission/open-auction-volume brokerage simulation.

## Evidence and next step

- Completed48 trials; aborted48 retained; historical raw trial lower bound=2866.
- Protected files=3; unchanged=True.
- Snapshot SHA-256: `b813a94d5342013488b8192e8ecf940c898ce984e47fbe2fdcb95a3c570c5a51`.
- Result SHA-256: `e2a4bb5344c7f17e1033b9dba6ed9069e749fbad4c9e32a0296e353a95958bc9`.
- Runtime SHA-256: `9c4312c345ed46c0b4785a59e89a374003e1f0e11036d56715ff6f8548e25ee8`.
- Replay operation:`47446023-0023-46af-987b-732002e3f13b`;evidence SHA-256:`15f9fffc8d426aa87d563d7f871eb19a06cc6a6274aa733bfffccb403d262140`. Machine evidence:`V11_6_REPLAY.json`.
- Next:investable benchmark and cost/style attribution, then an identifiable historical statistical contract. Do not manufacture PASS by increasing random templates or relaxing thresholds. Keep this epoch frozen.
