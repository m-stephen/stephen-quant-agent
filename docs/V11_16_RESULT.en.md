# V11.16 Sparse Event Test Report

## 结论 / Decision

0of8 preregistered event identities pass the complete two-cost exploratory screen. Certified usable Alpha remains zero.Archive the entire family;do not promote it to live signals.

## 范围与机制 / Scope and mechanism

Fifty continuous CNY3m accounts over484 reused2023–2024 sessions,with2022 warmup. Eight identities×event/hash/confirm-only×82/164bps plus two frozen lowvol anchors. Daily/flow as-of eligibility does not require minute/auction/chip coverage. Shock then1/3-session confirmation,first-hit,40-session cooldown,next-open planned entry and20-session planned holding. These are not50 independent evidence sets;2025/26 remain sealed.

- E1: `negative_price_innovation--quiet_positive_flow--lag1`
- E2: `negative_price_innovation--quiet_positive_flow--lag3`
- E3: `negative_price_innovation--recovery_positive_flow--lag1`
- E4: `negative_price_innovation--recovery_positive_flow--lag3`
- E5: `positive_flow_innovation--quiet_positive_flow--lag1`
- E6: `positive_flow_innovation--quiet_positive_flow--lag3`
- E7: `positive_flow_innovation--recovery_positive_flow--lag1`
- E8: `positive_flow_innovation--recovery_positive_flow--lag3`
- L: `anchor`

## 完整候选对照 / Complete candidate comparison

Descriptively,the largest82bps total-return gap to the strongest declared control isE4:total-0.6408%,2023-13.3554%,202414.6744%,Sharpe0.0941,MDD-38.0123%,profit CNY-19,224.82. Its minimum control increment is-20.1014percentage points. The chart includes all eight identities at both costs;zero denotes no advantage versus the strongest comparator. Descriptive ranking does not replace the screen. Comparators are strategies,not CSI300.

|ID|Policy|bps|2023|2024|Total|SR|MDD|Profit CNY|Cash mean|
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
|L|lowvol|164|-7.2293%|11.5747%|3.5086%|0.1954|-23.1604%|105,258.20|1.75%|
|L|lowvol|82|-0.3318%|19.8583%|19.4606%|0.7112|-15.4078%|583,816.76|1.75%|
|E1|confirm_only|164|-10.0130%|0.4170%|-9.6378%|-0.1217|-37.8327%|-289,133.52|10.66%|
|E1|confirm_only|82|-1.0264%|9.8151%|8.6880%|0.3053|-30.7722%|260,639.51|10.83%|
|E1|event|164|-3.8904%|-16.9214%|-20.1535%|-0.4375|-39.7934%|-604,605.51|10.68%|
|E1|event|82|5.6984%|-9.1324%|-3.9544%|0.0083|-31.0833%|-118,632.90|10.86%|
|E1|risk_hash|164|-15.9835%|-8.7598%|-23.3432%|-0.4439|-49.0657%|-700,296.73|10.76%|
|E1|risk_hash|82|-7.5561%|-0.2037%|-7.7444%|-0.0516|-40.5691%|-232,333.05|10.94%|
|E2|confirm_only|164|-18.8397%|-19.0226%|-34.2785%|-0.8493|-51.8619%|-1,028,354.97|10.11%|
|E2|confirm_only|82|-10.7188%|-11.2496%|-20.7626%|-0.4244|-43.8637%|-622,877.85|10.30%|
|E2|event|164|-20.4272%|-7.8204%|-26.6501%|-0.6220|-48.8625%|-799,503.08|10.16%|
|E2|event|82|-12.4595%|1.0230%|-11.5640%|-0.1832|-40.2646%|-346,918.92|10.35%|
|E2|risk_hash|164|-19.5296%|-12.4846%|-29.5760%|-0.6458|-51.2850%|-887,279.57|10.29%|
|E2|risk_hash|82|-11.4765%|-4.1137%|-15.1181%|-0.2410|-43.0982%|-453,541.92|10.47%|
|E3|confirm_only|164|-18.7668%|-13.5148%|-29.7453%|-0.7629|-45.4696%|-892,358.76|8.68%|
|E3|confirm_only|82|-10.5879%|-5.0809%|-15.1308%|-0.3020|-36.1472%|-453,924.99|8.87%|
|E3|event|164|-11.1105%|-13.4602%|-23.0753%|-0.5366|-42.2583%|-692,257.52|8.72%|
|E3|event|82|-2.2143%|-4.9858%|-7.0897%|-0.0759|-32.5225%|-212,690.97|8.91%|
|E3|risk_hash|164|-20.6719%|-22.3927%|-38.4356%|-0.9831|-50.9954%|-1,153,068.03|8.47%|
|E3|risk_hash|82|-12.7045%|-14.8169%|-25.6390%|-0.5607|-42.7119%|-769,170.74|8.66%|
|E4|confirm_only|164|-10.0620%|-3.4124%|-13.1310%|-0.1895|-38.5101%|-393,930.37|9.04%|
|E4|confirm_only|82|-1.0460%|6.0041%|4.8953%|0.2228|-28.5647%|146,857.55|9.21%|
|E4|event|164|-21.2306%|4.4379%|-17.7349%|-0.3499|-43.7287%|-532,047.31|8.76%|
|E4|event|82|-13.3554%|14.6744%|-0.6408%|0.0941|-38.0123%|-19,224.82|8.93%|
|E4|risk_hash|164|-20.2740%|-18.7008%|-35.1834%|-0.7681|-55.0193%|-1,055,503.15|8.93%|
|E4|risk_hash|82|-12.2763%|-10.6937%|-21.6572%|-0.3797|-47.1376%|-649,717.36|9.11%|
|E5|confirm_only|164|-7.1857%|-7.0799%|-13.7569%|-0.2099|-41.3801%|-412,707.39|5.81%|
|E5|confirm_only|82|2.1896%|2.5582%|4.8039%|0.2203|-33.5056%|144,117.06|5.98%|
|E5|event|164|-15.5290%|-19.1674%|-31.7199%|-0.6785|-52.3606%|-951,596.02|5.64%|
|E5|event|82|-7.0130%|-10.6947%|-16.9577%|-0.2694|-44.1680%|-508,730.81|5.80%|
|E5|risk_hash|164|-18.5843%|-6.3444%|-23.7496%|-0.4235|-47.9982%|-712,488.74|5.65%|
|E5|risk_hash|82|-10.3492%|3.4265%|-7.2773%|-0.0272|-39.0182%|-218,318.83|5.82%|
|E6|confirm_only|164|-9.9476%|-16.9441%|-25.2062%|-0.5451|-43.4539%|-756,186.40|5.69%|
|E6|confirm_only|82|-0.8493%|-8.2085%|-8.9881%|-0.1010|-33.1571%|-269,641.89|5.88%|
|E6|event|164|-18.5025%|-12.9592%|-29.0639%|-0.6316|-48.5593%|-871,917.19|5.62%|
|E6|event|82|-10.2831%|-3.8046%|-13.6964%|-0.2046|-39.6952%|-410,892.19|5.80%|
|E6|risk_hash|164|-12.6281%|-15.4341%|-26.1132%|-0.5024|-46.0754%|-783,395.43|5.66%|
|E6|risk_hash|82|-3.7969%|-6.5304%|-10.0793%|-0.0965|-36.7341%|-302,378.65|5.84%|
|E7|confirm_only|164|-12.0953%|-12.1830%|-22.8048%|-0.4234|-46.1125%|-684,142.54|5.58%|
|E7|confirm_only|82|-3.2655%|-2.8846%|-6.0559%|-0.0102|-36.8026%|-181,676.04|5.75%|
|E7|event|164|-20.3746%|-16.6276%|-33.6144%|-0.7285|-52.6829%|-1,008,431.00|5.60%|
|E7|event|82|-12.3555%|-7.8172%|-19.2069%|-0.3218|-44.5247%|-576,205.89|5.76%|
|E7|risk_hash|164|-7.6615%|-9.7684%|-16.6815%|-0.2438|-39.2760%|-500,444.74|5.54%|
|E7|risk_hash|82|1.6382%|-0.2495%|1.3846%|0.1553|-34.4679%|41,538.16|5.70%|
|E8|confirm_only|164|-21.3044%|-16.5638%|-34.3394%|-0.8024|-51.2544%|-1,030,182.81|5.80%|
|E8|confirm_only|82|-13.3992%|-7.6627%|-20.0351%|-0.3741|-42.8297%|-601,054.19|5.98%|
|E8|event|164|-17.6857%|-17.9308%|-32.4453%|-0.7395|-49.2570%|-973,359.76|5.74%|
|E8|event|82|-9.4033%|-9.1991%|-17.7374%|-0.3112|-40.2920%|-532,122.02|5.92%|
|E8|risk_hash|164|-20.1037%|-11.6043%|-29.3752%|-0.5941|-50.9587%|-881,255.37|5.60%|
|E8|risk_hash|82|-12.0949%|-2.2387%|-14.0629%|-0.1901|-42.2958%|-421,886.73|5.78%|

## 匹配和交易解释 / Matching and execution

Control targets match admission dates,risk cells and expiry clocks;confirm-only removes the earlier shock. Coverage is assigned control slots divided by new primary slots,by planned entry year—not fill rate. Up to40 desired2.5% slots;empty slots remain cash. Full-portfolio rejections consume cooldown. Blocked exits are retried and can exceed40 actual names;immature end holdings are marked,not forcibly liquidated. Existing cap trimming still applies under target_changes.

|ID|Year|Admissions|Hash matched|Confirm matched|
|---|---|---:|---:|---:|
|E1|2023|481|481|481|
|E1|2024|430|430|430|
|E2|2023|480|480|480|
|E2|2024|440|440|440|
|E3|2023|481|481|481|
|E3|2024|446|446|446|
|E4|2023|480|480|480|
|E4|2024|452|452|452|
|E5|2023|484|484|484|
|E5|2024|478|478|476|
|E6|2023|483|483|483|
|E6|2024|479|479|479|
|E7|2023|482|482|482|
|E7|2024|483|483|483|
|E8|2023|481|481|481|
|E8|2024|482|482|482|

## 本轮回答了什么 / What this epoch establishes

All16 event/cost accounts have negative full-period net returns. Admission and matching gates pass;failure is not missing controls or too few events,but annual returns,drawdown,risk-adjusted performance and incremental value. Mean cash at82bps is only5.76%–10.86%:sparse instrument events did not produce low portfolio exposure. Pooling events across the market kept targets near capacity;this is not successful low-turnover timing. A different information structure or tradable effect is needed,not renamed events.

## 验证与统计限制 / Verification and inference

Full suite:924passed,1skipped;Ruff passes. Independent raw-source SQL checks eligibility,previous20 normalizers and risk cells. Separate event/control/target reconstruction and all50 cash/NAV/fee/capacity/year/SR/drawdown/native-NOFIT audits pass. Raw Trial lower bound3506. Reused history and multiple search attempts are not independent validation;DSR/PBO/placebo are not certified here. Both original lowvol accounts replay byte-identically.

## 数据和执行边界 / Source and execution limits

82bps=6commission each side+10sell tax+30slippage each side;164doubles components. Capacity remains the prior lagged-ADV proxy. Adjusted fractional units are not physical lots,minimum commissions or corporate-action cash certification. Vendor net-flow ratio is not order-book OFI:Cont et al.study book events and short-horizon impact,not evidence that this daily proxy predicts tradable returns. The paper motivates a question,not this factor's validity.

[Cont,Kukanov and Stoikov: The Price Impact of Order Book Events](https://arxiv.org/abs/1011.6402)

## 后续处理 / Next action

Freeze any complete exploratory survivor unchanged before capacity,delay,regime and placebo challenges. Otherwise preserve negative evidence and preregister a genuinely different bounded mechanism. Do not chase a passing curve by changing signs,thresholds or years on the same results. Formal DSR/PBO/placebo gates remain unchanged;Alpha is not guaranteed. Existing candidates and sealed windows remain untouched.

Evidence: V11_16_RESULT.summary.json; independent audit; Issue184 preregistration5561319318.

Native artifact validation recorded separately. Visible/pixel QA deferred under quiet-until-usable instruction.
