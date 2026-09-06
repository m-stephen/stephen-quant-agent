# V11.15 信号时点与衰减诊断报告

## 结论 / Decision

本轮完成90个固定响应诊断，强响应线索0个，可用Alpha仍未认证。这是时点诊断，不是新账户回测；不可将毛收益、重叠事件或条件均值写成净收益率、年化Sharpe或资金利润。

## 数据范围与分母 / Scope and denominators

共同成熟信号日期463个，从2023-01-03到2024-12-02；2022预热，2023/2024重复暴露开发数据，不读取2025/2026。每个年度按信号年汇总，不是该年的自融资净值收益。相同日期固定分母，每日每格前10名各2.5%，不沿用buffer；格内等权每格25%。

## 本轮实际发现 / What the evidence shows

九个机制在20日区间的正毛收益数量，2023年为1/9，2024年为9/9。低波安静吸筹分别为0.7097%/1.5007%，但2024年低于同档全部三个对照。所有机制和年份中，1日、5日毛均值的最大值分别仅0.1818%、1.0834%，均不到1.64%单次完整往返参考线。这不是净收益测算，也不排除buffer降低实际换手；但不能把缩短持有期本身当成已证实的解法。有些短期信号存在，核心问题是幅度、对照增量和跨年稳定性，不能全部归咎于买入前收益。

## 收益发生时点 / Response timing

before_entry是信号日收盘至次日开盘，入场前已发生；same_day是次日开盘至收盘，A股新买入不可同日卖出。只有open_1/5/20在时间上兼容T+1，但尚未经真实执行验证。五个区间不是可相加的互斥收益分解。

## 缺失、涨跌停与压力情景 / Missingness and stress

未来端点缺失不删除股票、不重分配权重。固定分母贡献缺失记0，并展示可见价格权重；完整价格条件均值可能有选择偏差。压力情景：买不进记现金0，已买但缺失或不可卖退出记损失100%。这不是实际清算模型，不能拿来做净值。

## 后续账户实验条件 / Gate for a separate execution study

两年均需毛收益>1.64%，分别超出同档hash/反转/等权至少0.30个百分点，价格覆盖>=99%，入场权重>=98%，压力均值>0。只是足够强响应的筛选，不是低换手策略存在Alpha的必要条件；本轮没有扣常数费用伪装账户、没有调门槛。

## 方法、验证与统计边界 / Methods,verification and limits

独立SQL逐端点比对冻结原日K，重建风险格、全部排名/权重和41670条日期统计，最大重算差4.13e-14。全部90个原生无拟合Trial已完成，累计下界3456。无独立OOS/Court/DSR/PBO/placebo认证。源时间字段仍非实时首见证明，复权价格仍非分红现金或整手成交证明。

## 后续工作 / Next work

只将强响应另行冻结为真实连续300万元账户实验，测试标准及双倍成本、延迟、容量、市场状态和伪造检验。没有强响应则封存当前三机制的时点/期限诊断，不翻转方向或无限换窗口；下一轮必须说明新的经济机制和有限预算。原观察卡不变。

## 完整结果 / Complete results

|Group|Policy|Label|Signal year|Dates|Gross mean|Valid weight|Entry weight|Stress mean|
|---|---|---|---:|---:|---:|---:|---:|---:|
|high|auction_exhaustion|before_entry|2023|242|-0.0936%|99.9070%|99.8347%|N/A|
|high|auction_exhaustion|before_entry|2024|221|-0.1255%|99.8643%|99.6606%|N/A|
|high|auction_exhaustion|open_1|2023|242|0.0872%|99.8244%|99.8347%|-0.1620%|
|high|auction_exhaustion|open_1|2024|221|0.1818%|99.7624%|99.6606%|-0.3427%|
|high|auction_exhaustion|open_20|2023|242|-0.5367%|99.8244%|99.8347%|-0.6920%|
|high|auction_exhaustion|open_20|2024|221|2.6602%|99.8416%|99.6606%|2.4576%|
|high|auction_exhaustion|open_5|2023|242|0.2988%|99.7624%|99.8347%|-0.0456%|
|high|auction_exhaustion|open_5|2024|221|1.0834%|99.7511%|99.6606%|0.7160%|
|high|auction_exhaustion|same_day|2023|242|0.1412%|99.9070%|99.8347%|N/A|
|high|auction_exhaustion|same_day|2024|221|0.2137%|99.8643%|99.6606%|N/A|
|high|cell_equal_weight|before_entry|2023|242|-0.1019%|99.9811%|99.7255%|N/A|
|high|cell_equal_weight|before_entry|2024|221|-0.1117%|99.9746%|99.4123%|N/A|
|high|cell_equal_weight|open_1|2023|242|-0.0055%|99.9627%|99.7255%|-0.1243%|
|high|cell_equal_weight|open_1|2024|221|0.0556%|99.9503%|99.4123%|-0.1538%|
|high|cell_equal_weight|open_20|2023|242|-0.8605%|99.9172%|99.7255%|-1.0193%|
|high|cell_equal_weight|open_20|2024|221|2.0232%|99.8901%|99.4123%|1.7984%|
|high|cell_equal_weight|open_5|2023|242|-0.0810%|99.9365%|99.7255%|-0.2269%|
|high|cell_equal_weight|open_5|2024|221|0.4162%|99.9147%|99.4123%|0.2259%|
|high|cell_equal_weight|same_day|2023|242|0.1031%|99.9811%|99.7255%|N/A|
|high|cell_equal_weight|same_day|2024|221|0.1739%|99.9746%|99.4123%|N/A|
|high|flow_price_absorption|before_entry|2023|242|-0.0233%|99.9587%|99.8967%|N/A|
|high|flow_price_absorption|before_entry|2024|221|-0.0377%|99.9434%|99.6833%|N/A|
|high|flow_price_absorption|open_1|2023|242|0.0539%|99.9174%|99.8967%|-0.1213%|
|high|flow_price_absorption|open_1|2024|221|0.1432%|99.8416%|99.6833%|-0.3175%|
|high|flow_price_absorption|open_20|2023|242|-1.1834%|99.9380%|99.8967%|-1.2822%|
|high|flow_price_absorption|open_20|2024|221|3.0547%|99.9434%|99.6833%|2.8889%|
|high|flow_price_absorption|open_5|2023|242|0.0126%|99.8967%|99.8967%|-0.1721%|
|high|flow_price_absorption|open_5|2024|221|0.7366%|99.8529%|99.6833%|0.3858%|
|high|flow_price_absorption|same_day|2023|242|0.0534%|99.9587%|99.8967%|N/A|
|high|flow_price_absorption|same_day|2024|221|0.0918%|99.9434%|99.6833%|N/A|
|high|hash|before_entry|2023|242|-0.1120%|99.9897%|99.7211%|N/A|
|high|hash|before_entry|2024|221|-0.1047%|99.9661%|99.3213%|N/A|
|high|hash|open_1|2023|242|0.0312%|99.9793%|99.7211%|-0.1065%|
|high|hash|open_1|2024|221|0.0582%|99.9434%|99.3213%|-0.2083%|
|high|hash|open_20|2023|242|-0.5421%|99.9587%|99.7211%|-0.6463%|
|high|hash|open_20|2024|221|1.6521%|99.8303%|99.3213%|1.4693%|
|high|hash|open_5|2023|242|0.0570%|99.9380%|99.7211%|-0.1088%|
|high|hash|open_5|2024|221|0.4525%|99.8982%|99.3213%|0.2510%|
|high|hash|same_day|2023|242|0.1492%|99.9897%|99.7211%|N/A|
|high|hash|same_day|2024|221|0.1900%|99.9661%|99.3213%|N/A|
|high|price_reversal|before_entry|2023|242|-0.0371%|99.9174%|99.8554%|N/A|
|high|price_reversal|before_entry|2024|221|-0.0594%|99.8077%|99.5814%|N/A|
|high|price_reversal|open_1|2023|242|0.0610%|99.8657%|99.8554%|-0.1558%|
|high|price_reversal|open_1|2024|221|0.1769%|99.6606%|99.5814%|-0.2077%|
|high|price_reversal|open_20|2023|242|-0.1710%|99.8554%|99.8554%|-0.4061%|
|high|price_reversal|open_20|2024|221|3.0484%|99.7172%|99.5814%|2.7711%|
|high|price_reversal|open_5|2023|242|0.3732%|99.8140%|99.8554%|0.0988%|
|high|price_reversal|open_5|2024|221|1.0266%|99.6946%|99.5814%|0.6767%|
|high|price_reversal|same_day|2023|242|0.0944%|99.9174%|99.8554%|N/A|
|high|price_reversal|same_day|2024|221|0.1625%|99.8077%|99.5814%|N/A|
|high|quiet_accumulation|before_entry|2023|242|0.0062%|99.9793%|99.6694%|N/A|
|high|quiet_accumulation|before_entry|2024|221|-0.0966%|99.9887%|99.5475%|N/A|
|high|quiet_accumulation|open_1|2023|242|-0.0886%|99.9587%|99.6694%|-0.2008%|
|high|quiet_accumulation|open_1|2024|221|0.0755%|99.9774%|99.5475%|-0.1845%|
|high|quiet_accumulation|open_20|2023|242|-1.2743%|99.9174%|99.6694%|-1.4016%|
|high|quiet_accumulation|open_20|2024|221|2.4884%|99.9208%|99.5475%|2.3100%|
|high|quiet_accumulation|open_5|2023|242|-0.3428%|99.9380%|99.6694%|-0.4643%|
|high|quiet_accumulation|open_5|2024|221|0.5377%|99.9548%|99.5475%|0.3931%|
|high|quiet_accumulation|same_day|2023|242|-0.0558%|99.9793%|99.6694%|N/A|
|high|quiet_accumulation|same_day|2024|221|0.1458%|99.9887%|99.5475%|N/A|
|low|auction_exhaustion|before_entry|2023|242|0.0406%|100.0000%|99.9690%|N/A|
|low|auction_exhaustion|before_entry|2024|221|-0.0530%|99.9887%|99.8529%|N/A|
|low|auction_exhaustion|open_1|2023|242|0.0229%|99.9897%|99.9690%|-0.0008%|
|low|auction_exhaustion|open_1|2024|221|0.1049%|99.9548%|99.8529%|0.0324%|
|low|auction_exhaustion|open_20|2023|242|-0.4784%|99.9070%|99.9690%|-0.6254%|
|low|auction_exhaustion|open_20|2024|221|2.9607%|99.6946%|99.8529%|2.6490%|
|low|auction_exhaustion|open_5|2023|242|0.0926%|99.9690%|99.9690%|0.0292%|
|low|auction_exhaustion|open_5|2024|221|0.7736%|99.9095%|99.8529%|0.6935%|
|low|auction_exhaustion|same_day|2023|242|-0.0066%|100.0000%|99.9690%|N/A|
|low|auction_exhaustion|same_day|2024|221|0.1057%|99.9887%|99.8529%|N/A|
|low|cell_equal_weight|before_entry|2023|242|0.0543%|99.9879%|99.9421%|N/A|
|low|cell_equal_weight|before_entry|2024|221|0.0142%|99.9878%|99.7675%|N/A|
|low|cell_equal_weight|open_1|2023|242|0.0473%|99.9740%|99.9421%|-0.0015%|
|low|cell_equal_weight|open_1|2024|221|0.1022%|99.9731%|99.7675%|0.0603%|
|low|cell_equal_weight|open_20|2023|242|0.1990%|99.9329%|99.9421%|0.0914%|
|low|cell_equal_weight|open_20|2024|221|1.8823%|99.9000%|99.7675%|1.7161%|
|low|cell_equal_weight|open_5|2023|242|0.2038%|99.9450%|99.9421%|0.1216%|
|low|cell_equal_weight|open_5|2024|221|0.4978%|99.9392%|99.7675%|0.4207%|
|low|cell_equal_weight|same_day|2023|242|-0.0060%|99.9879%|99.9421%|N/A|
|low|cell_equal_weight|same_day|2024|221|0.0703%|99.9878%|99.7675%|N/A|
|low|flow_price_absorption|before_entry|2023|242|0.0854%|99.9793%|99.9690%|N/A|
|low|flow_price_absorption|before_entry|2024|221|0.0134%|100.0000%|99.9208%|N/A|
|low|flow_price_absorption|open_1|2023|242|0.0531%|99.9690%|99.9690%|0.0124%|
|low|flow_price_absorption|open_1|2024|221|0.0723%|100.0000%|99.9208%|0.0169%|
|low|flow_price_absorption|open_20|2023|242|-0.0467%|99.9070%|99.9690%|-0.1609%|
|low|flow_price_absorption|open_20|2024|221|1.7210%|99.8643%|99.9208%|1.5104%|
|low|flow_price_absorption|open_5|2023|242|0.1875%|99.9587%|99.9690%|0.1458%|
|low|flow_price_absorption|open_5|2024|221|0.5300%|99.9887%|99.9208%|0.4809%|
|low|flow_price_absorption|same_day|2023|242|-0.0220%|99.9793%|99.9690%|N/A|
|low|flow_price_absorption|same_day|2024|221|0.0399%|100.0000%|99.9208%|N/A|
|low|hash|before_entry|2023|242|0.0483%|99.9897%|99.9483%|N/A|
|low|hash|before_entry|2024|221|0.0036%|99.9887%|99.7398%|N/A|
|low|hash|open_1|2023|242|0.0510%|99.9793%|99.9483%|0.0212%|
|low|hash|open_1|2024|221|0.0881%|99.9887%|99.7398%|0.0491%|
|low|hash|open_20|2023|242|0.2304%|99.9897%|99.9483%|0.1629%|
|low|hash|open_20|2024|221|1.5682%|99.9548%|99.7398%|1.3919%|
|low|hash|open_5|2023|242|0.1863%|99.9793%|99.9483%|0.1268%|
|low|hash|open_5|2024|221|0.4197%|99.9434%|99.7398%|0.3431%|
|low|hash|same_day|2023|242|-0.0040%|99.9897%|99.9483%|N/A|
|low|hash|same_day|2024|221|0.0756%|99.9887%|99.7398%|N/A|
|low|price_reversal|before_entry|2023|242|0.0563%|100.0000%|99.9587%|N/A|
|low|price_reversal|before_entry|2024|221|0.0040%|99.9774%|99.8190%|N/A|
|low|price_reversal|open_1|2023|242|0.0170%|100.0000%|99.9587%|-0.0433%|
|low|price_reversal|open_1|2024|221|0.0727%|99.9321%|99.8190%|-0.0138%|
|low|price_reversal|open_20|2023|242|-0.5742%|99.9277%|99.9587%|-0.7355%|
|low|price_reversal|open_20|2024|221|2.8262%|99.7059%|99.8190%|2.5312%|
|low|price_reversal|open_5|2023|242|0.0770%|99.9897%|99.9587%|-0.0051%|
|low|price_reversal|open_5|2024|221|0.6585%|99.8303%|99.8190%|0.4685%|
|low|price_reversal|same_day|2023|242|-0.0224%|100.0000%|99.9587%|N/A|
|low|price_reversal|same_day|2024|221|0.0367%|99.9774%|99.8190%|N/A|
|low|quiet_accumulation|before_entry|2023|242|0.0649%|100.0000%|99.9277%|N/A|
|low|quiet_accumulation|before_entry|2024|221|0.0056%|99.9434%|99.7851%|N/A|
|low|quiet_accumulation|open_1|2023|242|0.0750%|100.0000%|99.9277%|0.0432%|
|low|quiet_accumulation|open_1|2024|221|0.0966%|99.9095%|99.7851%|0.0512%|
|low|quiet_accumulation|open_20|2023|242|0.7097%|99.9793%|99.9277%|0.6429%|
|low|quiet_accumulation|open_20|2024|221|1.5007%|99.9434%|99.7851%|1.3899%|
|low|quiet_accumulation|open_5|2023|242|0.3591%|100.0000%|99.9277%|0.3164%|
|low|quiet_accumulation|open_5|2024|221|0.3622%|99.9095%|99.7851%|0.3281%|
|low|quiet_accumulation|same_day|2023|242|0.0042%|100.0000%|99.9277%|N/A|
|low|quiet_accumulation|same_day|2024|221|0.0895%|99.9434%|99.7851%|N/A|
|middle|auction_exhaustion|before_entry|2023|242|0.0142%|99.9793%|99.9174%|N/A|
|middle|auction_exhaustion|before_entry|2024|221|-0.0229%|99.9548%|99.7285%|N/A|
|middle|auction_exhaustion|open_1|2023|242|0.0783%|99.9690%|99.9174%|0.0051%|
|middle|auction_exhaustion|open_1|2024|221|0.1788%|99.9208%|99.7285%|0.0885%|
|middle|auction_exhaustion|open_20|2023|242|-0.0649%|99.9174%|99.9174%|-0.2157%|
|middle|auction_exhaustion|open_20|2024|221|2.5659%|99.8303%|99.7285%|2.2643%|
|middle|auction_exhaustion|open_5|2023|242|0.2854%|99.9587%|99.9174%|0.1776%|
|middle|auction_exhaustion|open_5|2024|221|0.8875%|99.8756%|99.7285%|0.7473%|
|middle|auction_exhaustion|same_day|2023|242|0.0679%|99.9793%|99.9174%|N/A|
|middle|auction_exhaustion|same_day|2024|221|0.1374%|99.9548%|99.7285%|N/A|
|middle|cell_equal_weight|before_entry|2023|242|0.0243%|99.9810%|99.9030%|N/A|
|middle|cell_equal_weight|before_entry|2024|221|0.0183%|99.9850%|99.6227%|N/A|
|middle|cell_equal_weight|open_1|2023|242|0.0526%|99.9633%|99.9030%|-0.0160%|
|middle|cell_equal_weight|open_1|2024|221|0.1061%|99.9711%|99.6227%|0.0324%|
|middle|cell_equal_weight|open_20|2023|242|-0.1376%|99.9216%|99.9030%|-0.2676%|
|middle|cell_equal_weight|open_20|2024|221|2.2935%|99.9031%|99.6227%|2.0793%|
|middle|cell_equal_weight|open_5|2023|242|0.1646%|99.9307%|99.9030%|0.0575%|
|middle|cell_equal_weight|open_5|2024|221|0.5632%|99.9486%|99.6227%|0.4553%|
|middle|cell_equal_weight|same_day|2023|242|0.0247%|99.9810%|99.9030%|N/A|
|middle|cell_equal_weight|same_day|2024|221|0.0704%|99.9850%|99.6227%|N/A|
|middle|flow_price_absorption|before_entry|2023|242|0.0623%|99.9897%|99.9174%|N/A|
|middle|flow_price_absorption|before_entry|2024|221|0.0608%|99.9661%|99.7172%|N/A|
|middle|flow_price_absorption|open_1|2023|242|0.0467%|99.9793%|99.9174%|-0.0337%|
|middle|flow_price_absorption|open_1|2024|221|0.0891%|99.9321%|99.7172%|-0.0166%|
|middle|flow_price_absorption|open_20|2023|242|-0.7516%|99.9380%|99.9174%|-0.8603%|
|middle|flow_price_absorption|open_20|2024|221|2.8837%|99.9321%|99.7172%|2.7125%|
|middle|flow_price_absorption|open_5|2023|242|0.1618%|99.9897%|99.9174%|0.0776%|
|middle|flow_price_absorption|open_5|2024|221|0.6800%|99.9208%|99.7172%|0.5319%|
|middle|flow_price_absorption|same_day|2023|242|0.0010%|99.9897%|99.9174%|N/A|
|middle|flow_price_absorption|same_day|2024|221|-0.0204%|99.9661%|99.7172%|N/A|
|middle|hash|before_entry|2023|242|0.0254%|99.9793%|99.8760%|N/A|
|middle|hash|before_entry|2024|221|0.0268%|99.9887%|99.6154%|N/A|
|middle|hash|open_1|2023|242|0.0453%|99.9690%|99.8760%|-0.0756%|
|middle|hash|open_1|2024|221|0.1258%|99.9548%|99.6154%|0.0319%|
|middle|hash|open_20|2023|242|0.3621%|99.9587%|99.8760%|0.2359%|
|middle|hash|open_20|2024|221|2.3678%|99.8643%|99.6154%|2.0754%|
|middle|hash|open_5|2023|242|0.1855%|99.9587%|99.8760%|0.1074%|
|middle|hash|open_5|2024|221|0.5845%|99.8756%|99.6154%|0.3016%|
|middle|hash|same_day|2023|242|0.0154%|99.9793%|99.8760%|N/A|
|middle|hash|same_day|2024|221|0.0603%|99.9887%|99.6154%|N/A|
|middle|price_reversal|before_entry|2023|242|0.0462%|99.9793%|99.8864%|N/A|
|middle|price_reversal|before_entry|2024|221|0.0210%|99.9434%|99.6719%|N/A|
|middle|price_reversal|open_1|2023|242|0.0828%|99.9380%|99.8864%|-0.0314%|
|middle|price_reversal|open_1|2024|221|0.1228%|99.8982%|99.6719%|0.0408%|
|middle|price_reversal|open_20|2023|242|-0.3032%|99.9380%|99.8864%|-0.4071%|
|middle|price_reversal|open_20|2024|221|2.5435%|99.8529%|99.6719%|2.3150%|
|middle|price_reversal|open_5|2023|242|0.2426%|99.9793%|99.8864%|0.1738%|
|middle|price_reversal|open_5|2024|221|0.7793%|99.8869%|99.6719%|0.6891%|
|middle|price_reversal|same_day|2023|242|0.0385%|99.9793%|99.8864%|N/A|
|middle|price_reversal|same_day|2024|221|0.0638%|99.9434%|99.6719%|N/A|
|middle|quiet_accumulation|before_entry|2023|242|0.0562%|99.9897%|99.8864%|N/A|
|middle|quiet_accumulation|before_entry|2024|221|-0.0015%|99.9887%|99.6267%|N/A|
|middle|quiet_accumulation|open_1|2023|242|0.0438%|99.9793%|99.8864%|-0.0460%|
|middle|quiet_accumulation|open_1|2024|221|0.1324%|99.9887%|99.6267%|0.0592%|
|middle|quiet_accumulation|open_20|2023|242|-0.5053%|99.9277%|99.8864%|-0.6200%|
|middle|quiet_accumulation|open_20|2024|221|1.7755%|99.9208%|99.6267%|1.6345%|
|middle|quiet_accumulation|open_5|2023|242|0.0772%|99.9277%|99.8864%|-0.0596%|
|middle|quiet_accumulation|open_5|2024|221|0.3502%|99.9548%|99.6267%|0.2647%|
|middle|quiet_accumulation|same_day|2023|242|-0.0082%|99.9897%|99.8864%|N/A|
|middle|quiet_accumulation|same_day|2024|221|0.1187%|99.9887%|99.6267%|N/A|

Source: docs/V11_15_RESULT.summary.json; scripts/audit_signal_timing.py.
Trading rule: https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml