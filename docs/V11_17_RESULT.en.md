# V11.17 Statistical Peer Test Report

## 结果 / Result

0of6 statistical-peer identities survive the complete two-cost exploratory screen. Certified usable Alpha remains zero.Archive this family;the best-looking curve is not a usable Alpha.

## 实验范围 / Experiment scope

Fifty continuous CNY3m accounts over484 sessions in2023–2024,with2022 training/warmup. Two signals×three risk groups×four policies×two costs plus two original lowvol anchors. All years are reused development evidence,not new independent samples;2025/26 were not accessed.

- P1: `flow-high`
- P2: `flow-low`
- P3: `flow-middle`
- P4: `price-high`
- P5: `price-low`
- P6: `price-middle`
- L: `anchor`

## 净收益增量 / Net incremental evidence

Descriptively,the highest82bps increment over the strongest declared control isP2(flow-low):total2.4119%,2023-5.7413%,20248.6497%,Sharpe0.1612,MDD-29.2091%,profit CNY72,355.82. Minimum control increment is-17.0487percentage points. All six identities and both costs are shown;zero means no advantage over the strongest comparator,and+3pp is only one screening condition. Controls are same-group own signal,shuffled graph,hash and original lowvol—not CSI300.

|ID|Policy|bps|2023|2024|Total|Sharpe|MDD|Profit CNY|Mean cash|
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
|L|lowvol|164|-7.2293%|11.5747%|3.5086%|0.1954|-23.1604%|105,258.20|1.75%|
|L|lowvol|82|-0.3318%|19.8583%|19.4606%|0.7112|-15.4078%|583,816.76|1.75%|
|P1|hash|164|-12.3913%|-17.2219%|-27.4792%|-0.3811|-48.1775%|-824,376.80|4.00%|
|P1|hash|82|-8.2151%|-12.8005%|-19.9640%|-0.2189|-43.8521%|-598,920.52|4.25%|
|P1|own|164|-33.9382%|-38.4235%|-59.3215%|-1.5023|-69.0025%|-1,779,643.59|2.58%|
|P1|own|82|-27.3252%|-31.8471%|-50.4700%|-1.1530|-63.6963%|-1,514,099.84|2.79%|
|P1|peer|164|-32.7963%|-39.3391%|-59.2336%|-1.5416|-68.6622%|-1,777,007.76|2.57%|
|P1|peer|82|-26.1298%|-33.0615%|-50.5524%|-1.1912|-63.3313%|-1,516,570.57|2.79%|
|P1|shuffle|164|-30.4553%|-36.8211%|-56.0624%|-1.3392|-66.9684%|-1,681,872.73|2.58%|
|P1|shuffle|82|-23.2649%|-30.4192%|-46.6071%|-0.9988|-61.0478%|-1,398,212.53|2.77%|
|P2|hash|164|1.7646%|6.8848%|8.7709%|0.3147|-26.9769%|263,126.73|3.01%|
|P2|hash|82|5.9389%|11.9055%|18.5514%|0.5325|-24.3400%|556,543.28|3.29%|
|P2|own|164|-15.3280%|-2.8726%|-17.7602%|-0.3707|-41.2277%|-532,806.58|1.75%|
|P2|own|82|-7.3500%|6.6138%|-1.2224%|0.0750|-32.9766%|-36,671.33|1.75%|
|P2|peer|164|-13.8354%|-0.8556%|-14.5726%|-0.3120|-38.9526%|-437,178.21|1.75%|
|P2|peer|82|-5.7413%|8.6497%|2.4119%|0.1612|-29.2091%|72,355.82|1.77%|
|P2|shuffle|164|-14.8495%|-4.4898%|-18.6726%|-0.4018|-40.5893%|-560,178.14|1.75%|
|P2|shuffle|82|-6.7224%|5.0643%|-1.9986%|0.0547|-32.4196%|-59,957.63|1.76%|
|P3|hash|164|-4.1159%|-11.7996%|-15.4299%|-0.1837|-41.1631%|-462,896.48|1.91%|
|P3|hash|82|1.8783%|-6.2635%|-4.5029%|0.0473|-36.1828%|-135,086.31|2.03%|
|P3|own|164|-15.9356%|-12.2920%|-26.2688%|-0.4875|-48.3048%|-788,065.29|1.89%|
|P3|own|82|-7.5209%|-3.1125%|-10.3994%|-0.0959|-39.9695%|-311,981.13|1.95%|
|P3|peer|164|-18.2035%|-15.3448%|-30.7550%|-0.6408|-49.9248%|-922,650.34|1.87%|
|P3|peer|82|-9.7424%|-6.1801%|-15.3204%|-0.2256|-40.8031%|-459,612.42|1.94%|
|P3|shuffle|164|-17.5034%|-16.5050%|-31.1194%|-0.6149|-49.4378%|-933,582.61|1.89%|
|P3|shuffle|82|-9.2711%|-8.0013%|-16.5306%|-0.2343|-40.9265%|-495,917.15|1.94%|
|P4|hash|164|-12.3913%|-17.2219%|-27.4792%|-0.3811|-48.1775%|-824,376.80|4.00%|
|P4|hash|82|-8.2151%|-12.8005%|-19.9640%|-0.2189|-43.8521%|-598,920.52|4.25%|
|P4|own|164|-33.0828%|-31.0052%|-53.8306%|-1.0746|-68.4306%|-1,614,917.00|1.81%|
|P4|own|82|-26.2480%|-23.6246%|-43.6716%|-0.7607|-62.8145%|-1,310,148.23|1.87%|
|P4|peer|164|-28.7303%|-32.0174%|-51.5490%|-0.9930|-66.6684%|-1,546,468.56|1.79%|
|P4|peer|82|-21.4412%|-25.3144%|-41.3279%|-0.6922|-60.8773%|-1,239,836.46|1.86%|
|P4|shuffle|164|-31.5661%|-29.4602%|-51.7268%|-0.9876|-67.0036%|-1,551,804.99|1.80%|
|P4|shuffle|82|-24.4693%|-21.7839%|-40.9228%|-0.6731|-60.9604%|-1,227,682.83|1.84%|
|P5|hash|164|1.7646%|6.8848%|8.7709%|0.3147|-26.9769%|263,126.73|3.01%|
|P5|hash|82|5.9389%|11.9055%|18.5514%|0.5325|-24.3400%|556,543.28|3.29%|
|P5|own|164|-15.5948%|-8.9946%|-23.1868%|-0.4914|-44.3878%|-695,602.52|1.74%|
|P5|own|82|-7.1532%|0.9935%|-6.2308%|-0.0363|-36.0239%|-186,922.79|1.77%|
|P5|peer|164|-16.0112%|-12.9666%|-26.9017%|-0.6113|-48.9844%|-807,052.13|1.74%|
|P5|peer|82|-7.5117%|-3.8136%|-11.0388%|-0.1611|-40.2097%|-331,165.35|1.75%|
|P5|shuffle|164|-12.6064%|-12.9310%|-23.9073%|-0.5114|-44.4678%|-717,218.54|1.74%|
|P5|shuffle|82|-3.8535%|-3.7456%|-7.4548%|-0.0662|-35.0676%|-223,643.01|1.76%|
|P6|hash|164|-4.1159%|-11.7996%|-15.4299%|-0.1837|-41.1631%|-462,896.48|1.91%|
|P6|hash|82|1.8783%|-6.2635%|-4.5029%|0.0473|-36.1828%|-135,086.31|2.03%|
|P6|own|164|-16.2623%|-10.5899%|-25.1300%|-0.4028|-50.5698%|-753,899.60|1.74%|
|P6|own|82|-7.8669%|-1.0299%|-8.8157%|-0.0358|-42.3394%|-264,472.36|1.76%|
|P6|peer|164|-12.1306%|-13.7760%|-24.2355%|-0.3780|-51.3264%|-727,064.99|1.74%|
|P6|peer|82|-3.0427%|-4.5459%|-7.4503%|-0.0067|-42.6862%|-223,509.42|1.77%|
|P6|shuffle|164|-15.1295%|-11.4644%|-24.8595%|-0.3925|-49.9511%|-745,783.74|1.74%|
|P6|shuffle|82|-6.5433%|-2.2310%|-8.6284%|-0.0304|-41.2120%|-258,851.70|1.77%|

## 图和信号定义 / Graph and signal definitions

Graphs for2023 and2024 use2022 and2022–2023 respectively,excluding the final five training sessions. Daily returns are cross-sectionally demeaned;Pearson edges require120 overlapping observations,with ten positive neighbors>=.15. Price gap is weighted peer five-day return minus own return;flow gap uses five-day mean net-flow/turnover ratios. Both graphs require eight currently available peers. Native unsupervised lineage records observation dates,not fabricated return labels.

## 对照与覆盖 / Controls and coverage

A fixed training-risk-cell node permutation preserves topology,weights and broad risk structure. True and shuffled graphs share receiver support;mean annual coverage:2023: 92.71%, 2024: 95.28%. Common cell value minus own value has exactly the own-negative within-cell ordering,so it intentionally shares that account rather than pretending to be independent evidence. A single structural shuffle is not a statistical placebo test.

## 交易和筛选定义 / Execution and screening

Each risk group selects ten stocks in each of four cells,retaining incumbents in top13;four fixed20-session phases0/5/10/15 form one continuous account,with2.5% per name per sleeve.82bps=6commission each side+10sell tax+30slippage each side;164doubles all components. Both costs must pass positive returns in both years,Sharpe>=.7,MDD>=-.25,total increment>=3pp and annual increment>=-5pp against every control,plus coverage and audits.

## 独立验证 / Independent verification

Full suite:952passed,1skipped;Ruff passes. Independent SQL checks3,440,702source rows,all92,060selected correlations,top10 selection for40fixed receiver samples,permutations and coverage. All24new target sets,50cash/NAV/cost/capacity accounts and96native fit records reconcile. Raw Trial lower bound3556.All failures remain in evidence.

## 不能据此宣称的内容 / What this cannot establish

Return-correlation graphs are not actual supply chains or historical industry memberships. Cohen and Frazzini use customer–supplier economic links;this tests a related cross-stock information question,not their causal mechanism or returns. Adjusted fractional units and lagged-ADV capacity are not live lots,minimum-commission or corporate-action cash certification. Independent exhaustive top10 candidate ranking covers a fixed receiver sample;all selected edge statistics are checked. Reused development history,multiplicity and correlation limit inference. No certified DSR/PBO/placebo output is claimed.

[Cohen and Frazzini: Economic Links and Predictable Returns](https://pages.stern.nyu.edu/~afrazzin/pdf/Economic%20Links%20and%20Predictable%20Returns%20-%20Cohen%20and%20Frazzini.pdf)

## 后续与未决问题 / Next steps and open questions

Freeze complete survivors before registered delay,capacity,regime and falsification challenges. Otherwise change to a genuinely distinct finite mechanism,not threshold/sign/horizon chasing within this batch. Every change adds Trial debt;costs,capital and comparators are not silently replaced. Remaining questions are whether incremental information pays for execution,stays stable across years,and earns independent forward support—not which single curve is highest.

Evidence: V11_17_RESULT.summary.json;independent audit;Issue184 preregistration5561787787.

Native artifact schema validation recorded separately. Visible/pixel QA deferred under the quiet-until-usable instruction.
