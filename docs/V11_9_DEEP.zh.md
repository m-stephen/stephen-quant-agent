# V11.9 筹码四批候选深挖

## 结论

Decision: COST_FRAGILE_OBSERVATION_ONLY_CONTINUE_MECHANISMS; stress survivors=0; validated Alpha=0.

先冻结候选后预记12新政策试验，再执行完整的102/132bps、容量1/4和延迟一日挑战。所有比较都是2023–2024连续300万元研究账户及其匹配对照；非独立OOS。

|Scenario|Roundtrip bps|2023|2024|Total net|Profit CNY|Low-vol|Increment pp|MDD|Sharpe|
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
|cost_102|102|-0.25%|22.20%|21.89%|656,613.11|15.95%|+5.94|-15.97%|0.728|
|cost_132|132|-2.52%|19.66%|16.65%|499,381.64|10.01%|+6.63|-16.94%|0.583|
|delay_one|82|1.37%|23.43%|25.12%|753,520.30|17.93%|+7.18|-15.49%|0.819|
|quarter_capacity|82|1.29%|23.92%|25.51%|765,386.29|20.09%|+5.42|-15.31%|0.825|

## 描述性风格与盈利日依赖

- cost_102: {"annualized_intercept": 0.024107559882331417, "beta_to_lowvol": 1.0447561009749358, "causal_alpha": false, "hac95_annualized_intercept_interval": [-0.04751969492552301, 0.09573481469018584], "hac_lag": 20, "market_industry_size_controls": "NOT_TESTED", "r_squared": 0.9136628224374744, "status": "DESCRIPTIVE_NOT_SELECTION_ADJUSTED"}
  Tail counterfactual: {"increment_if_top_active_days_equal_control": -0.019071873535446926, "net_return_if_top_active_days_equal_control": 0.14044642205143032, "observations_retained": 484, "positive_active_sum_share": 0.12428199718095963, "status": "NONTRADABLE_POSTHOC_DIAGNOSTIC", "top_positive_active_days": [286, 267, 259, 285, 268]}
- cost_132: {"annualized_intercept": 0.029896166429865957, "beta_to_lowvol": 1.0431649148355775, "causal_alpha": false, "hac95_annualized_intercept_interval": [-0.041341657550941366, 0.10113399041067328], "hac_lag": 20, "market_industry_size_controls": "NOT_TESTED", "r_squared": 0.9137144035229345, "status": "DESCRIPTIVE_NOT_SELECTION_ADJUSTED"}
  Tail counterfactual: {"increment_if_top_active_days_equal_control": -0.008872100756221135, "net_return_if_top_active_days_equal_control": 0.09124954069849012, "observations_retained": 484, "positive_active_sum_share": 0.12332341567434395, "status": "NONTRADABLE_POSTHOC_DIAGNOSTIC", "top_positive_active_days": [286, 267, 259, 285, 268]}
- delay_one: {"annualized_intercept": 0.02828957396210066, "beta_to_lowvol": 1.0474255550796916, "causal_alpha": false, "hac95_annualized_intercept_interval": [-0.04423722627740395, 0.10081637420160527], "hac_lag": 20, "market_industry_size_controls": "NOT_TESTED", "r_squared": 0.9130575261363543, "status": "DESCRIPTIVE_NOT_SELECTION_ADJUSTED"}
  Tail counterfactual: {"increment_if_top_active_days_equal_control": -0.009832078124903276, "net_return_if_top_active_days_equal_control": 0.169516976556759, "observations_retained": 484, "positive_active_sum_share": 0.12585144137549759, "status": "NONTRADABLE_POSTHOC_DIAGNOSTIC", "top_positive_active_days": [286, 267, 259, 285, 268]}
- quarter_capacity: {"annualized_intercept": 0.020212222294713922, "beta_to_lowvol": 1.04569346625676, "causal_alpha": false, "hac95_annualized_intercept_interval": [-0.05169172325635968, 0.09211616784578752], "hac_lag": 20, "market_industry_size_controls": "NOT_TESTED", "r_squared": 0.9136270730157157, "status": "DESCRIPTIVE_NOT_SELECTION_ADJUSTED"}
  Tail counterfactual: {"increment_if_top_active_days_equal_control": -0.026412496676140318, "net_return_if_top_active_days_equal_control": 0.17448499895470815, "observations_retained": 484, "positive_active_sum_share": 0.12489355551889401, "status": "NONTRADABLE_POSTHOC_DIAGNOSTIC", "top_positive_active_days": [286, 267, 259, 285, 268]}

## 判断边界与下一步

HAC和替换最高5个正超额日只用于描述，不用于生成删日交易规则，也不是经过选择校正的置信度。上轮PBO0.65、DSR敏感性0.005495、family placebo0.655属于3256次债务时的12个日历family，未冒充加入本轮后的完整统计认证。

Independent daily account/SQL/gate checks passed for12 accounts;maximum residual=4.66e-10 CNY. New trials12;full raw debt3268. No2025/2026 reads;frozen parent unchanged.

## 真实执行就绪程度

现有冻结日K提供原始open/close、amount/volume、adjustment_factor和available_at，但冻结分钟表只有日内特征，没有真实开盘逐笔成交。adjustment_factor不等于可审计的现金分红/送转/配股事件；不能据此完成原始手数及最低佣金的全账户认证。未运行真实券商账户、未下单。

如额外压力失败，保留该候选作观察，不再优化相位；继续预注册与低波动重复暴露不同的机制。若所有压力通过，也只进入执行来源审计，不宣称可用Alpha。完整正式门槛与独立证据要求不改变。
