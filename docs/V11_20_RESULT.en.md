# V11.20 Gross-to-Net Diagnosis

## Technical summary

Twelve zero-fee counterfactuals and24 immutable paid accounts are fully reconciled. Both original primary identities remain failed; certified usable Alpha is zero. This diagnoses gross strength and implementation friction, not candidate promotion.


## What this diagnostic establishes

linear: zero-fee total4.5677%, -17.1321pp versus same-basis risk; quadratic: zero-fee total-1.2020%, -14.8577pp versus same-basis risk. Both identities trail their own risk controls in each year before fees. Costs amplify losses but do not explain the whole failure. Prioritize a different information representation/mechanism,not just cheaper execution or higher model degree. This describes this family on reused history;it proves neither absence of market Alpha nor vendor-data uselessness.


## Scope and comparator definitions

Each continuous CNY3m account spans484 sessions in2023–2024 with2022 warmup. History is reused development,not freshOOS;2025/26 are unread. Comparators are same-basis risk/shuffle/regression,hash,matched lowvol and two original portfolios,notCSI300 or market excess return.


## Methods and frozen conditions

Twelve target files are copied byte-for-byte with unchanged members,weights,clocks and open-execution semantics. Only commission,tax and slippage jointly become zero;cash paths are rerun rather than adding fees back to oldNAV. The24 paid82/164bps accounts remain read-only. Ten policies use target_changes,two anchors full_target;capacity remains5% of prior60-observation ADV.


## All account results

The chart shows both full ranking identities at0/82/164bps. The table retains all36 paths rather than selecting the best as a discovery. Zero fees are an untradeable counterfactual.

|Account|bps|2023|2024|Total|Sharpe|MDD|Profit CNY|Fees CNY|Traded CNY|Mean cash|
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
|control-hash-0|0|5.4428%|6.4098%|12.2014%|0.3620|-29.4424%|366,042.26|0.00|44,232,053.67|6.47%|
|control-hash-164|164|-0.9613%|0.6520%|-0.3157%|0.1216|-32.9016%|-9,469.51|341,538.95|41,953,140.46|5.74%|
|control-hash-82|82|2.1823%|3.5115%|5.7705%|0.2414|-30.8545%|173,115.22|175,471.18|43,116,979.01|6.07%|
|control-lowvol-0|0|6.3380%|9.2056%|16.1271%|0.4419|-28.0803%|483,812.23|0.00|141,331,320.52|1.90%|
|control-lowvol-164|164|-11.7318%|-9.9846%|-20.5450%|-0.3610|-43.9850%|-616,350.69|982,269.55|120,035,034.29|1.74%|
|control-lowvol-82|82|-3.1008%|-0.6029%|-3.6850%|0.0426|-34.3869%|-110,549.21|533,798.02|130,495,394.48|1.77%|
|control-original_lowvol-0|0|7.0781%|28.7596%|37.8733%|1.2348|-10.4206%|1,136,198.87|0.00|118,266,290.54|1.75%|
|control-original_lowvol-164|164|-7.2293%|11.5747%|3.5086%|0.1954|-23.1604%|105,258.20|836,499.11|102,275,928.13|1.75%|
|control-original_lowvol-82|82|-0.3318%|19.8583%|19.4606%|0.7112|-15.4078%|583,816.76|449,182.39|109,867,754.97|1.75%|
|control-original_stable-0|0|8.6974%|32.6854%|44.2256%|1.4034|-10.5645%|1,326,768.47|0.00|74,797,785.19|1.75%|
|control-original_stable-164|164|-1.4452%|22.7071%|20.9337%|0.7560|-14.8276%|628,011.00|556,656.33|68,182,887.51|1.75%|
|control-original_stable-82|82|3.5000%|27.5945%|32.0603%|1.0786|-12.6927%|961,809.35|291,282.73|71,374,898.89|1.75%|
|linear-full-0|0|2.2496%|2.2671%|4.5677%|0.2274|-39.3834%|137,031.67|0.00|134,535,560.32|1.82%|
|linear-full-164|164|-15.4137%|-16.0530%|-28.9923%|-0.4343|-50.8939%|-869,768.20|927,686.15|113,385,178.73|1.74%|
|linear-full-82|82|-6.9007%|-7.3221%|-13.7175%|-0.1028|-45.1502%|-411,526.32|505,487.27|123,593,786.95|1.76%|
|linear-regression-0|0|3.4032%|4.8966%|8.4665%|0.2903|-37.9036%|253,993.72|0.00|135,512,611.48|1.84%|
|linear-regression-164|164|-14.2607%|-13.7513%|-26.0510%|-0.3748|-50.2065%|-781,529.20|935,806.22|114,374,440.56|1.75%|
|linear-regression-82|82|-5.7894%|-4.7413%|-10.2562%|-0.0404|-43.4761%|-307,686.61|509,554.26|124,585,240.63|1.77%|
|linear-risk-0|0|8.6045%|12.0578%|21.6998%|0.4979|-34.3217%|650,994.62|0.00|146,755,576.57|1.82%|
|linear-risk-164|164|-10.2711%|-8.1121%|-17.5500%|-0.1982|-44.7003%|-526,500.56|1,007,678.05|123,130,533.26|1.74%|
|linear-risk-82|82|-1.1780%|1.2210%|0.0286%|0.1453|-38.8155%|857.60|550,121.81|134,474,816.35|1.76%|
|linear-shuffle-0|0|1.6537%|-13.2939%|-11.8601%|-0.1098|-40.0934%|-355,801.93|0.00|130,294,612.92|1.96%|
|linear-shuffle-164|164|-15.8874%|-29.1048%|-40.3682%|-0.8524|-55.8824%|-1,211,046.91|911,225.41|111,379,778.43|1.77%|
|linear-shuffle-82|82|-7.3860%|-21.3749%|-27.1822%|-0.4749|-48.0594%|-815,464.55|493,617.92|120,700,271.84|1.82%|
|quadratic-full-0|0|1.4615%|-2.6251%|-1.2020%|0.1169|-35.6982%|-36,059.89|0.00|135,301,312.02|1.83%|
|quadratic-full-164|164|-16.1001%|-20.0116%|-32.8899%|-0.5936|-49.5912%|-986,695.89|936,510.04|114,460,186.93|1.73%|
|quadratic-full-82|82|-7.5861%|-11.5143%|-18.2270%|-0.2328|-41.7075%|-546,808.96|510,867.81|124,905,458.45|1.76%|
|quadratic-regression-0|0|5.7483%|5.2399%|11.2894%|0.3394|-34.8017%|338,682.39|0.00|143,010,024.49|1.87%|
|quadratic-regression-164|164|-12.5669%|-13.8719%|-24.6956%|-0.3861|-45.1807%|-740,867.56|986,343.39|120,531,347.69|1.75%|
|quadratic-regression-82|82|-3.7747%|-4.8308%|-8.4232%|-0.0252|-39.0160%|-252,694.86|537,197.26|131,324,062.92|1.78%|
|quadratic-risk-0|0|5.7010%|7.5256%|13.6557%|0.3727|-35.3161%|409,669.82|0.00|141,746,423.40|1.80%|
|quadratic-risk-164|164|-12.6273%|-11.7565%|-22.8993%|-0.3033|-46.6821%|-686,980.19|974,839.03|119,129,745.56|1.74%|
|quadratic-risk-82|82|-3.7830%|-2.3708%|-6.0641%|0.0389|-40.9927%|-181,924.29|532,461.72|130,169,236.58|1.76%|
|quadratic-shuffle-0|0|1.9159%|6.1401%|8.1736%|0.2867|-30.6710%|245,209.17|0.00|137,975,160.45|1.99%|
|quadratic-shuffle-164|164|-15.6667%|-12.6013%|-26.2939%|-0.4747|-45.6069%|-788,815.91|955,711.48|116,799,484.48|1.77%|
|quadratic-shuffle-82|82|-7.3178%|-3.6844%|-10.7326%|-0.0974|-36.9961%|-321,978.48|519,174.60|126,930,491.53|1.83%|

## Cost-path drag and fee-addback error

Path drag=zero-fee minus paid return. Addback error=path drag minus direct fees/CNY3m. These rate/percentage-point differences include cash scaling,compounding and changed fills;they are neither causal fee estimates nor achievable savings.

|Target|bps|Path drag pp|Direct fees / capital pp|Addback error pp|2023 drag pp|2024 drag pp|
|---|---:|---:|---:|---:|---:|---:|
|linear-full|82|18.2853|16.8496|1.4357|9.1503|9.5892|
|linear-full|164|33.5600|30.9229|2.6371|17.6633|18.3201|
|linear-risk|82|21.6712|18.3374|3.3338|9.7825|10.8368|
|linear-risk|164|39.2498|33.5893|5.6606|18.8756|20.1699|
|linear-shuffle|82|15.3221|16.4539|-1.1318|9.0397|8.0810|
|linear-shuffle|164|28.5082|30.3742|-1.8660|17.5411|15.8109|
|linear-regression|82|18.7227|16.9851|1.7375|9.1926|9.6379|
|linear-regression|164|34.5174|31.1935|3.3239|17.6639|18.6479|
|quadratic-full|82|17.0250|17.0289|-0.0040|9.0476|8.8892|
|quadratic-full|164|31.6879|31.2170|0.4709|17.5616|17.3865|
|quadratic-risk|82|19.7198|17.7487|1.9711|9.4840|9.8964|
|quadratic-risk|164|36.5550|32.4946|4.0604|18.3283|19.2822|
|quadratic-shuffle|82|18.9063|17.3058|1.6004|9.2338|9.8245|
|quadratic-shuffle|164|34.4675|31.8570|2.6105|17.5827|18.7414|
|quadratic-regression|82|19.7126|17.9066|1.8060|9.5230|10.0707|
|quadratic-regression|164|35.9850|32.8781|3.1069|18.3152|19.1118|
|control-hash|82|6.4309|5.8490|0.5819|3.2604|2.8982|
|control-hash|164|12.5171|11.3846|1.1324|6.4041|5.7578|
|control-lowvol|82|19.8120|17.7933|2.0188|9.4388|9.8085|
|control-lowvol|164|36.6721|32.7423|3.9298|18.0698|19.1903|
|control-original_lowvol|82|18.4127|14.9727|3.4400|7.4099|8.9013|
|control-original_lowvol|164|34.3647|27.8833|6.4814|14.3074|17.1849|
|control-original_stable|82|12.1653|9.7094|2.4559|5.1974|5.0909|
|control-original_stable|164|23.2919|18.5552|4.7367|10.1426|9.9784|

## Increment versus every declared control

All42 comparisons cover two identities,seven controls and three costs. Total and both annual increments remain visible. Gross increment minus same-cost net increment is descriptive,not an Alpha statistic.

|Identity|Control|bps|Increment pp|2023 pp|2024 pp|Gross minus paid increment pp|
|---|---|---:|---:|---:|---:|---:|
|linear|linear-risk|0|-17.1321|-6.3549|-9.7907|0.0000|
|linear|linear-risk|82|-13.7461|-5.7227|-8.5431|-3.3860|
|linear|linear-risk|164|-11.4423|-5.1425|-7.9409|-5.6898|
|linear|linear-shuffle|0|16.4278|0.5959|15.5610|0.0000|
|linear|linear-shuffle|82|13.4646|0.4853|14.0528|2.9632|
|linear|linear-shuffle|164|11.3760|0.4737|13.0519|5.0518|
|linear|linear-regression|0|-3.8987|-1.1536|-2.6295|0.0000|
|linear|linear-regression|82|-3.4613|-1.1113|-2.5808|-0.4374|
|linear|linear-regression|164|-2.9413|-1.1530|-2.3016|-0.9574|
|linear|control-hash|0|-7.6337|-3.1932|-4.1427|0.0000|
|linear|control-hash|82|-19.4881|-9.0831|-10.8336|11.8544|
|linear|control-hash|164|-28.6766|-14.4523|-16.7049|21.0429|
|linear|control-lowvol|0|-11.5594|-4.0884|-6.9385|0.0000|
|linear|control-lowvol|82|-10.0326|-3.7999|-6.7192|-1.5268|
|linear|control-lowvol|164|-8.4473|-3.6819|-6.0683|-3.1121|
|linear|control-original_lowvol|0|-33.3056|-4.8284|-26.4925|0.0000|
|linear|control-original_lowvol|82|-33.1781|-6.5689|-27.1804|-0.1275|
|linear|control-original_lowvol|164|-32.5009|-8.1843|-27.6277|-0.8047|
|linear|control-original_stable|0|-39.6579|-6.4478|-30.4183|0.0000|
|linear|control-original_stable|82|-45.7779|-10.4007|-34.9166|6.1200|
|linear|control-original_stable|164|-49.9260|-13.9685|-38.7600|10.2681|
|quadratic|quadratic-risk|0|-14.8577|-4.2395|-10.1508|0.0000|
|quadratic|quadratic-risk|82|-12.1628|-3.8031|-9.1435|-2.6948|
|quadratic|quadratic-risk|164|-9.9905|-3.4728|-8.2551|-4.8671|
|quadratic|quadratic-shuffle|0|-9.3756|-0.4544|-8.7652|-0.0000|
|quadratic|quadratic-shuffle|82|-7.4943|-0.2683|-7.8299|-1.8813|
|quadratic|quadratic-shuffle|164|-6.5960|-0.4334|-7.4103|-2.7796|
|quadratic|quadratic-regression|0|-12.4914|-4.2868|-7.8651|0.0000|
|quadratic|quadratic-regression|82|-9.8038|-3.8114|-6.6835|-2.6876|
|quadratic|quadratic-regression|164|-8.1943|-3.5332|-6.1397|-4.2971|
|quadratic|control-hash|0|-13.4034|-3.9813|-9.0349|-0.0000|
|quadratic|control-hash|82|-23.9975|-9.7685|-15.0259|10.5941|
|quadratic|control-hash|164|-32.5742|-15.1388|-20.6636|19.1708|
|quadratic|control-lowvol|0|-17.3291|-4.8765|-11.8308|0.0000|
|quadratic|control-lowvol|82|-14.5420|-4.4853|-10.9114|-2.7871|
|quadratic|control-lowvol|164|-12.3448|-4.3684|-10.0270|-4.9842|
|quadratic|control-original_lowvol|0|-39.0753|-5.6165|-31.3848|0.0000|
|quadratic|control-original_lowvol|82|-37.6875|-7.2543|-31.3726|-1.3878|
|quadratic|control-original_lowvol|164|-36.3985|-8.8708|-31.5863|-2.6768|
|quadratic|control-original_stable|0|-45.4276|-7.2359|-35.3106|0.0000|
|quadratic|control-original_stable|82|-50.2873|-11.0861|-39.1089|4.8597|
|quadratic|control-original_stable|164|-53.8236|-14.6549|-42.7187|8.3960|

## Validation and trial ledger

Full suite:1057 passed,1 skipped;Ruff passes. Twelve new native replayTrials,zero new fits,explicitly inherit16models/32fits. Trial lower bound3648→3660 retains prior failures. Independent source-open units,closing marks,ADV capacity and36 saved accounts reconcile.


## Limitations and next decision

Adjusted fractional units are not raw lots,minimum-commission,dividend-cash or live-capacity certification. Zero fees cannot rescue failed registered gates. DSR/PBO/placebo are NOT_RUN/null,notCourtPASS. Weak gross increments call for a different mechanism;gross strength lost after costs calls for a separately registered train-prefix turnover objective. Unstable years cannot be discarded. Register every new attempt,keep thresholds,no automatic main merge or trading.


[Preregistration / 预登记](https://github.com/m-stephen/stephen-quant-agent/issues/184#issuecomment-5562959810)

Evidence: V11_20_RESULT.summary.json; runtime 7fc9ff06762cca5c107229c45a9362c4732c540e

Visible/pixel QA: DEFERRED_USER_QUIET_INSTRUCTION.
