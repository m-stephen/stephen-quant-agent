# V11.18 条件风险配置测试报告 / Conditional Risk Test Report

## 结论 / Conclusion

0 of 4 conditional-risk identities pass the complete exploratory screen. Certified usable Alpha remains zero. Archive this mechanism without sign, exposure-threshold or horizon chasing.

## 范围与基准 / Scope and comparators

44 continuous CNY3m accounts over 484 sessions in 2023–2024, with 2022 training/warmup. Exposure scales original frozen lowvol/stable_lowrisk stock targets; it is not a new stock selector. Comparators are same-base, same-cost fixed, lag20, shuffled, risk-only, unscaled and original-execution anchors, not CSI300. Repeatedly reused 2023/24 are development evidence, not independent samples; 2025/26 were not accessed.

- R1: `lowvol-mean`
- R2: `lowvol-mean_second`
- R3: `stable_lowrisk-mean`
- R4: `stable_lowrisk-mean_second`

## 模型及可知时点 / Model and information clock

Four inputs are common eligible-stock 20-day breadth, mean return, mean volatility and adjacent-session dispersion. Next-year models use past prefixes with five-session embargo and mature labels; scaling and ridge lambda=1 are training-only. Outputs predict five-session mean return and second moment R², not conditional variance. Gamma=10, exposure 25%–100%, quarter-step quantization and five-session refresh. Fit cutoff precedes signal, which precedes execution.

## 训练标签与限制 / Training labels and limitations

Labels are gross equal-weight 200-low-vol-stock basket proxies from next open to the open five sessions later. Missing entry prices remain cash without renormalization; missing endpoints use strictly past marks. Labels are non-overlapping with >=95% support and >=30 training rows. They omit limits, capacity and fees and are not executable portfolio returns; those constraints apply to the 44 final accounts. Common-state coverage: 2023: 100.00%; 2024: 100.00%

```json
{
  "direct-2023": {
    "fit_cutoff": "2022-12-23",
    "maximum_label_end": "2022-12-23",
    "mean_return": -0.0015080497977713813,
    "mean_second": 0.0006392695256693367,
    "rotation": 0,
    "training_mean_exposure": {
      "mean": 0.3423913043478261,
      "mean_second": 0.3423913043478261,
      "risk_only": 0.25
    },
    "training_signal_dates": 46
  },
  "direct-2024": {
    "fit_cutoff": "2023-12-22",
    "maximum_label_end": "2023-12-20",
    "mean_return": 0.00023930176371939285,
    "mean_second": 0.0004702216814528631,
    "rotation": 0,
    "training_mean_exposure": {
      "mean": 0.3271276595744681,
      "mean_second": 0.31648936170212766,
      "risk_only": 0.25
    },
    "training_signal_dates": 94
  },
  "shuffle-2023": {
    "fit_cutoff": "2022-12-23",
    "maximum_label_end": "2022-12-23",
    "mean_return": -0.0015080497977713817,
    "mean_second": 0.0006392695256693367,
    "rotation": 15,
    "training_mean_exposure": {
      "mean": 0.33152173913043476,
      "mean_second": 0.34782608695652173,
      "risk_only": 0.25
    },
    "training_signal_dates": 46
  },
  "shuffle-2024": {
    "fit_cutoff": "2023-12-22",
    "maximum_label_end": "2023-12-20",
    "mean_return": 0.00023930176371939323,
    "mean_second": 0.0004702216814528631,
    "rotation": 31,
    "training_mean_exposure": {
      "mean": 0.3776595744680851,
      "mean_second": 0.3723404255319149,
      "risk_only": 0.25
    },
    "training_signal_dates": 94
  }
}
```

## 全部主身份增量 / Every primary incremental result

The chart shows all four identities at both costs: total return minus the strongest declared control, in fractional rates (0.03=3 percentage points). Negative values mean at least one simple control is better. Fixed controls match training mean exposure, not realized test risk or turnover. Cash, fees and traded notional remain visible; lower exposure or friction is not automatically alpha.

|Identity|bps|Failed gates|Minimum control increment pp|
|---|---:|---|---:|
|lowvol-mean|164|annual_increment, both_years_positive, sharpe, total_increment|0.8085|
|lowvol-mean|82|annual_increment, total_increment|-7.9040|
|lowvol-mean_second|164|both_years_positive, sharpe, total_increment|2.1626|
|lowvol-mean_second|82|annual_increment, total_increment|-6.8913|
|stable_lowrisk-mean|164|annual_increment, both_years_positive, total_increment|-11.5847|
|stable_lowrisk-mean|82|annual_increment, total_increment|-16.8669|
|stable_lowrisk-mean_second|164|annual_increment, both_years_positive, total_increment|-10.0892|
|stable_lowrisk-mean_second|82|annual_increment, total_increment|-15.6318|

|Account|bps|2023|2024|Total|Sharpe|MDD|Profit CNY|Fees CNY|Traded CNY|Mean cash|
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
|lowvol-mean-fixed-164|164|-2.3984%|4.3392%|1.8367%|0.2144|-8.1960%|55,100.43|281,973.86|34,469,095.06|66.93%|
|lowvol-mean-fixed-82|82|-0.0059%|6.7736%|6.7673%|0.7149|-5.2750%|203,019.40|144,183.85|35,253,388.80|66.96%|
|lowvol-mean-lag20-164|164|-1.6695%|1.3142%|-0.3772%|-0.0024|-9.2149%|-11,316.32|382,947.10|47,020,019.23|62.22%|
|lowvol-mean-lag20-82|82|0.1528%|6.1341%|6.2963%|0.5678|-5.9459%|188,889.15|197,553.29|48,525,492.10|62.24%|
|lowvol-mean-model-164|164|-1.7465%|6.6252%|4.7630%|0.3543|-8.0172%|142,890.56|412,809.84|50,372,011.14|60.90%|
|lowvol-mean-model-82|82|0.0056%|12.2596%|12.2660%|0.8336|-6.4966%|367,978.52|213,536.10|52,114,967.78|60.93%|
|lowvol-mean-shuffle-164|164|-12.4874%|3.3760%|-9.5330%|-0.6592|-22.1817%|-285,989.02|638,885.97|77,953,518.98|44.57%|
|lowvol-mean-shuffle-82|82|-5.1807%|6.8687%|1.3321%|0.1314|-15.0882%|39,963.92|337,250.68|82,303,842.47|44.62%|
|lowvol-mean_second-fixed-164|164|-2.3984%|4.2065%|1.7071%|0.2051|-8.0819%|51,214.20|277,756.56|33,951,627.48|67.45%|
|lowvol-mean_second-fixed-82|82|-0.0059%|6.5623%|6.5560%|0.7107|-5.2023%|196,680.08|141,978.52|34,712,114.83|67.49%|
|lowvol-mean_second-lag20-164|164|-1.6695%|3.5506%|1.8219%|0.1896|-8.1040%|54,657.02|360,070.38|44,143,125.54|63.14%|
|lowvol-mean_second-lag20-82|82|0.1528%|7.9970%|8.1620%|0.7386|-5.7334%|244,860.07|185,313.40|45,445,552.71|63.17%|
|lowvol-mean_second-model-164|164|-1.7465%|8.0034%|6.1171%|0.3924|-8.2100%|183,513.60|393,882.93|48,062,460.00|62.18%|
|lowvol-mean_second-model-82|82|0.0056%|13.2723%|13.2787%|0.7823|-8.0375%|398,361.94|203,356.26|49,630,555.38|62.22%|
|lowvol-mean_second-shuffle-164|164|-13.0521%|3.4954%|-10.0129%|-0.6806|-22.7148%|-300,386.55|662,561.37|80,839,188.60|42.77%|
|lowvol-mean_second-shuffle-82|82|-5.4340%|7.0921%|1.2727%|0.1262|-15.0562%|38,180.27|350,195.35|85,459,663.73|42.82%|
|lowvol-original-164|164|-7.2293%|11.5747%|3.5086%|0.1954|-23.1604%|105,258.20|836,499.11|102,275,928.13|1.75%|
|lowvol-original-82|82|-0.3318%|19.8583%|19.4606%|0.7112|-15.4078%|583,816.76|449,182.39|109,867,754.97|1.75%|
|lowvol-risk_only-164|164|-1.7465%|3.3270%|1.5224%|0.2259|-6.1533%|45,672.03|210,767.65|25,765,951.22|75.29%|
|lowvol-risk_only-82|82|0.0056%|5.1621%|5.1680%|0.7171|-3.9408%|155,039.41|107,162.90|26,202,440.86|75.31%|
|lowvol-unscaled-164|164|-7.1871%|12.0044%|3.9545%|0.2107|-23.0736%|118,636.05|830,401.68|101,533,082.69|1.76%|
|lowvol-unscaled-82|82|-0.3130%|20.5473%|20.1700%|0.7330|-15.3351%|605,099.56|442,402.02|108,214,833.34|1.89%|
|stable_lowrisk-mean-fixed-164|164|-0.2681%|7.6100%|7.3215%|0.7729|-5.1904%|219,645.18|175,224.74|21,450,912.11|66.84%|
|stable_lowrisk-mean-fixed-82|82|1.3715%|8.9316%|10.4256%|1.0823|-4.4066%|312,768.78|88,779.50|21,738,341.79|66.88%|
|stable_lowrisk-mean-lag20-164|164|-0.1045%|5.6793%|5.5688%|0.5059|-6.1408%|167,064.15|275,160.97|33,888,513.46|62.21%|
|stable_lowrisk-mean-lag20-82|82|1.1633%|9.1701%|10.4401%|0.9181|-5.2054%|313,201.51|140,529.13|34,622,854.27|62.25%|
|stable_lowrisk-mean-model-164|164|-0.1836%|10.6432%|10.4401%|0.7255|-6.1936%|313,201.83|307,349.84|37,508,408.76|60.94%|
|stable_lowrisk-mean-model-82|82|1.0122%|14.9185%|16.0817%|1.0789|-6.0078%|482,452.34|157,545.61|38,455,188.24|60.97%|
|stable_lowrisk-mean-shuffle-164|164|-9.4291%|7.1320%|-2.9696%|-0.1758|-17.5602%|-89,087.21|524,154.13|63,958,277.11|44.52%|
|stable_lowrisk-mean-shuffle-82|82|-3.3175%|9.8418%|6.1978%|0.4727|-12.9459%|185,935.31|273,602.55|66,774,789.38|44.57%|
|stable_lowrisk-mean_second-fixed-164|164|-0.2681%|7.3659%|7.0781%|0.7668|-5.1402%|212,342.13|172,952.92|21,170,533.25|67.37%|
|stable_lowrisk-mean_second-fixed-82|82|1.3715%|8.6464%|10.1365%|1.0802|-4.3544%|304,094.94|87,611.61|21,450,033.53|67.41%|
|stable_lowrisk-mean_second-lag20-164|164|-0.1045%|7.5107%|7.3983%|0.6789|-5.5500%|221,948.15|257,144.73|31,598,781.23|63.13%|
|stable_lowrisk-mean_second-lag20-82|82|1.1633%|10.6983%|11.9860%|1.0735|-4.9279%|359,580.44|131,009.29|32,203,905.75|63.17%|
|stable_lowrisk-mean_second-model-164|164|-0.1836%|12.1415%|11.9356%|0.7200|-7.6061%|358,067.26|293,232.44|35,784,410.55|62.22%|
|stable_lowrisk-mean_second-model-82|82|1.0122%|16.1412%|17.3168%|1.0080|-7.4525%|519,505.35|149,922.65|36,593,484.29|62.26%|
|stable_lowrisk-mean_second-shuffle-164|164|-9.8209%|7.2817%|-3.2543%|-0.1910|-17.9247%|-97,629.29|542,238.93|66,162,312.63|42.72%|
|stable_lowrisk-mean_second-shuffle-82|82|-3.4983%|10.1074%|6.2555%|0.4697|-12.9021%|187,664.48|283,416.71|69,167,132.82|42.80%|
|stable_lowrisk-original-164|164|-1.4452%|22.7071%|20.9337%|0.7560|-14.8276%|628,011.00|556,656.33|68,182,887.51|1.75%|
|stable_lowrisk-original-82|82|3.5000%|27.5945%|32.0603%|1.0786|-12.6927%|961,809.35|291,282.73|71,374,898.89|1.75%|
|stable_lowrisk-risk_only-164|164|-0.1836%|5.7913%|5.5971%|0.7787|-3.8600%|167,912.10|129,669.92|15,875,157.00|75.21%|
|stable_lowrisk-risk_only-82|82|1.0122%|6.7800%|7.8608%|1.0817|-3.2837%|235,824.18|65,474.38|16,032,654.73|75.24%|
|stable_lowrisk-unscaled-164|164|-1.2170%|23.5281%|22.0248%|0.7910|-14.6943%|660,743.00|538,702.60|65,994,341.83|2.29%|
|stable_lowrisk-unscaled-82|82|3.6284%|28.2936%|32.9486%|1.1098|-12.5879%|988,458.00|279,863.15|68,587,566.00|2.57%|

## 输出行为诊断 / Prediction behavior diagnosis

The complete prediction-exposure counts show whether the model actually changes decisions. These count already audited predictions, not a new threshold search or realized exposure after five-session execution. {"2023": {"mean": {"0.25": 241}, "mean_second": {"0.25": 241}, "risk_only": {"0.25": 241}}, "2024": {"mean": {"0.25": 121, "1.0": 72, "0.75": 28, "0.5": 21}, "mean_second": {"0.25": 123, "0.5": 37, "0.75": 21, "1.0": 61}, "risk_only": {"0.25": 242}}}

## 交易与门槛 / Execution and gates

82bps means 6 commission each side, 10 sell tax and 30 slippage each side; 164bps doubles each component. Cash earns zero, no leverage, desired name cap 2.5%. Both costs require positive returns in both years, Sharpe>=.7, MDD>=-.25, >=3pp total and >=-5pp annual increment against every control, >=95% annual state coverage and complete audit. All use target_changes except original full_target anchors. Adjusted fractional units do not certify live lots, minimum commission or corporate-action cash.

## 复核与试验账本 / Audit and trial ledger

Full suite: 982 passed, 1 skipped; Ruff passes. Independent source SQL checks 726 states, 19,000 label components and 95 labels; independent normal equations reconstruct four models, 22 target sets, 44 accounts and 72 native fits. Raw trial lower bound rises 3556 to 3600; all 44 attempts are retained. One structural shuffle is not a statistical placebo p-value.

## 解释与下一步 / Interpretation and next steps

This asks whether conditional exposure supplies a historical increment worth deeper testing, not whether usable alpha is certified. Freeze full survivors before finite registered delay, capacity, regime and falsification challenges; otherwise change to a genuinely different mechanism, not lower gates. Certification still needs identifiable trial history, multiplicity, purged CPCV/PBO, empirical-moment DSR, placebo and independent forward evidence. DSR .95, PBO .05 and placebo .05 gates remain unchanged. No main merge or trading.

## Evidence / 证据

[Preregistration](https://github.com/m-stephen/stephen-quant-agent/issues/184#issuecomment-5562202690)

Source: V11_18_RESULT.summary.json; independent audit and immutable operation hashes. Native report schema validation is recorded separately; visible/pixel QA is deferred under the quiet-until-usable instruction.
