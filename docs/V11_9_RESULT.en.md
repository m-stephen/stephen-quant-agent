# V11.9 Calendar Robustness Results

## Technical summary

Completed72 continuous accounts;1 robust staggered leads;zero validated Alpha.

Exposed2023–2024 research, CNY3m once, coverage-matched low-vol/hash controls. Increment is a difference in total returns (pp), not information ratio or CSI300 excess.

## Doubled costs: all predeclared calendars

|Candidate / 候选|Calendar / 日历|2023|2024|Total / 总收益|Profit / 盈利元|Low-vol / 对照|Increment / 增量pp|MDD|Sharpe|
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
|blend_concentration_+1_h20|annual_calendar|0.90%|34.60%|35.82%|1,074,487.25|27.22%|+8.60|-16.82%|1.090|
|blend_late_30_return_-1_h20|annual_calendar|3.53%|28.88%|33.42%|1,002,607.94|27.22%|+6.20|-14.45%|0.966|
|blend_concentration_+1_h20|phase_0|0.90%|30.36%|31.54%|946,102.24|26.21%|+5.32|-16.72%|0.964|
|blend_late_30_return_-1_h20|phase_0|3.53%|9.86%|13.73%|411,873.56|29.54%|-15.81|-25.95%|0.470|
|blend_concentration_+1_h20|phase_10|1.29%|17.53%|19.05%|571,501.25|15.91%|+3.14|-14.41%|0.635|
|blend_late_30_return_-1_h20|phase_10|1.03%|-6.14%|-5.17%|-155,012.60|15.80%|-20.97|-27.78%|-0.069|
|blend_concentration_+1_h20|phase_15|1.78%|19.90%|22.04%|661,161.07|24.76%|-2.72|-13.98%|0.720|
|blend_late_30_return_-1_h20|phase_15|-5.20%|8.91%|3.25%|97,430.95|24.51%|-21.26|-27.90%|0.182|
|blend_concentration_+1_h20|phase_5|1.53%|26.10%|28.03%|840,913.08|17.13%|+10.90|-16.40%|0.890|
|blend_late_30_return_-1_h20|phase_5|1.47%|5.82%|7.38%|221,294.41|16.87%|-9.50|-27.68%|0.294|
|blend_concentration_+1_h20|staggered_four|1.29%|23.92%|25.51%|765,386.29|20.09%|+5.42|-15.31%|0.825|
|blend_late_30_return_-1_h20|staggered_four|0.06%|3.98%|4.05%|121,432.55|20.68%|-16.63|-27.50%|0.206|

## Descriptive reset decomposition

|Candidate|Annual reset linked|Continuous annual calendar|Continuous phase0|Account reset pp|Calendar pp|
|---|---:|---:|---:|---:|---:|
|blend_concentration_+1_h20|34.88%|35.82%|31.54%|-0.94|+4.28|
|blend_late_30_return_-1_h20|32.85%|33.42%|13.73%|-0.57|+19.69|

Differences reconcile in the prespecified order but are not identified causal effects. The staggered policy combines desired weights in ONE account, not ex-post returns.

## Gates and limitations

- blend_concentration_+1_h20: failed checks=none
- blend_late_30_return_-1_h20: failed checks=annual_increment, continuous_drawdown, hash_increment, lowvol_increment, sharpe, three_of_four_phases, worst_phase_floor

PBO diagnostic=0.65; DSR and all details in the adjacent machine-readable summary. Family placebo={'block_sessions': 20, 'exchangeability': 'assumption_not_independent_confirmation', 'null': 'common_block_sign_symmetry_of_active_returns', 'p_value': 0.655, 'repetitions': 199, 'winner': 'blend_concentration_+1_h20:phase_5'}. These are current-family diagnostics, NOT full-history calibrated confidence.

Adjusted fractional shares, linear fees and ADV capacity remain approximations. Raw-share/lots/minimum-fee/actions/opening-liquidity and full-style independent validation remain necessary. No thresholds reduced or2025/2026 unsealed.

## Verification and next step

Independent SQL, daily cash/positions/NAV, annual compounding, gate decisions and72 SQLite trials passed. Maximum residual9.31e-10 CNY. Raw trial lower bound3256; restricted rows read=0.

A surviving fixed staggered policy is frozen for execution/style audit. Otherwise record timing/turnover/signal failures and preregister a genuinely distinct mechanism; never select this epoch's best phase. The open question is incremental information, not merely positive returns. Reused history never becomes independent validation.
