# V11.3 Search Power Lab Final Result

Implementation issue: [#178](https://github.com/m-stephen/stephen-quant-agent/issues/178)  
Initial frozen commit: `cdec8f0f06e52e9311effbefef38568845d09411`  
Runtime-fix commit: `25023ac`  
V11.3.1 specification SHA-256: `7d2662fdd53622671d25d102a1993b16cc8df5b126f397e8d675b226cba35119`

Final calibration-hardening commit: `fe91844`  
V11.3.2 specification SHA-256: `3f587f53a87335dddf4a3da3698c2af02328cb1acc88a96038cce82a64d8adf2`  
Calibration artifact SHA-256: `6ece0d0ca464d4c5a47477680063f44985817edc3620b0121909d28a1a0e35d5`

## Decision

`FITTING_CAPABLE_ONLY`

The current data and generator can automatically produce multiple historically attractive candidates. This rejects the claim that the system cannot even find a good-looking backtest. It does not establish independent ranking generalization or a deployable Alpha.

## Engineering and integrity

- 11,466 type-safe static expressions;
- 1,000 complete real-label candidate identities in the completed epoch;
- 24/24 hardened synthetic planted scenarios recovered in Top 10;
- hardened median signal correlation 0.9562 and median exposure overlap 0.90;
- 100 full adaptive null paths with FWER 0.00;
- identical normalized hashes with one and eight workers;
- 680 tests passed and one skipped; Ruff passed;
- zero 2025–2026 historical-return reads;
- zero V11.2 state changes;
- forced stop is true.

The final V11.3.2 audit adds actual missing-feature neutralization, regime decay, turnover drag and block, circular, date-level cross-sectional and regime-preserving nulls. It did not read real labels again and does not reinterpret the V11.3.1 `FITTING_CAPABLE_ONLY` result.

## Honest treatment of the aborted run

V11.3.0 opened the 2024 diagnostic window and then hit a label-blind runtime guard: after preventing exits from crossing into 2025, the 20-session domain had eleven valid periods while the code incorrectly required twelve. Its 1,000 first label reads remain immutable `ABORTED_AFTER_REAL_LABEL_READ` Trials.

V11.3.1 corrected the guard to the frozen six-period minimum and registered another 1,000 Trials. The repeated 2024 evidence is explicitly `REUSED_CONTAMINATED_DIAGNOSTIC` and cannot create a new holdout claim. Raw global Trials are 2,770.

## Search outcome

- 31/1,000 candidates had positive 2022–2023 double-cost returns;
- 13 passed every inner hard constraint;
- hard-eligible domains: 12 price/liquidity, one auction/close/chip, zero industry-relative flow;
- 98 had positive descriptive 2024 double-cost returns;
- 13 were positive in both windows;
- 55 met descriptive 2024 return/Sharpe/drawdown conditions after that window was viewed and cannot be selected post hoc.

| Candidate | 2022–2023 double-cost | Inner Sharpe | 2024 double-cost | 2024 Sharpe | Universe q25 |
|---|---:|---:|---:|---:|---:|
| `-rank(ret_20)` | 26.19% | 0.954 | 31.45% | 1.360 | 16.26% |
| `-divergence(ret_20, concentration)` | 26.55% | 1.170 | 17.90% | 1.149 | 11.84% |
| `rank(concentration)` | 23.95% | 1.084 | 14.25% | 0.866 | 4.97% |
| `-joint_max(amount_rank_20, ret_20)` | 14.40% | 0.608 | 9.41% | 0.626 | 7.61% |

These figures establish fitting and proposal capacity, not promotion eligibility. In particular, `-rank(ret_20)` is a familiar medium-horizon reversal expression and only appeared strongest after re-reading contaminated 2024 evidence.

## Ranking failure

The frozen inner winner was `majority_state(amihud_intraday, concentration, realized_volatility)`. It earned 15.03% after double costs in 2022–2023 with Sharpe 0.711, then lost 1.82% in 2024 with Sharpe -0.117.

The overall inner/outer Spearman was 0.6526 and the inner Top decile beat the overall outer median, but only one frozen mechanism representative remained positive. Because 2024 was reused contaminated evidence, the system cannot claim `RANKING_CAPABLE`.

## Multiplicity

- Epoch PBO: 0.70, fail;
- DSR: 0.001700, fail;
- raw global Trials: 2,770;
- promoted candidates: zero.

V11.3 therefore localizes the bottleneck: candidate fitting now works, but frozen selection and cross-mechanism generalization do not. The 2024 winners must not be cherry-picked. Future work should freeze this evidence, improve the ranking objective and industry-relative portfolio mapping, then rely on genuinely new append-only observations or a separately preregistered mechanism question.
