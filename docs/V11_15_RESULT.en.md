# V11.15 Signal Timing and Decay Report

## 结论 / Decision

All90 fixed response diagnostics completed;0 strong responses merit a separately frozen execution study. No usable Alpha is certified. Gross overlapping event labels are not net account returns,annualized Sharpe or capital profits.

## 数据范围与分母 / Scope and denominators

463 common mature signal dates,2023-01-03 through 2024-12-02.2022warmup,reused2023/24,no2025/26. Years refer to signal dates,not accounting years.Daily top10 per cell,2.5% each,no retention buffer;cell-equal-weight assigns25% per nonempty cell.

## 本轮实际发现 / What the evidence shows

Positive20-session gross responses: 1/9 in2023 versus 9/9 in2024.Low-risk quiet accumulation averages 0.7097%/1.5007%,but trails all three same-stratum controls in2024.The largest1/5-session gross means across mechanisms and years are only0.1818%/1.0834%,both below the1.64% full-roundtrip reference. This is not net-return arithmetic and does not rule out turnover reduction via buffers.Simply shortening holding time is not an established remedy. Some short-lived response exists;amplitude,increment over controls and year stability matter,not only inaccessible pre-entry gains.

## 收益发生时点 / Response timing

before_entry occurs before next-open entry;same_day is next-open to same-close and is not a same-day roundtrip for newly bought A-shares.Only open_1/5/20 are T+1-compatible in timing,not execution-certified. The five intervals overlap and must not be added.

## 缺失、涨跌停与压力情景 / Missingness and stress

Missing future endpoints never alter selection or weights. Missing contribution is0 with missing weight exposed;complete-price conditional means may be selection-biased. Stress assignscash0 to unavailable entry and loss100% to unavailable/unsellable exit after entry.It is a diagnostic stress convention,not actual liquidation or NAV.

## 后续账户实验条件 / Gate for a separate execution study

Both years require gross mean>1.64%,at least0.30pp above EACH same-stratum hash/reversal/EW,price coverage>=99%,entry>=98%,stress>0.This is a strong-response screen,not a necessary condition for every low-turnover alpha. No flat-cost pseudo-account or threshold adjustment.

## 方法、验证与统计边界 / Methods,verification and limits

Independent SQL checks every endpoint against frozen daily data,rebuilds all risk cells/ranks/weights and41670 date readouts;maximum difference4.13e-14.90 native no-fit Trials complete;raw historical lower bound3456. No independent OOS/Court/DSR/PBO/placebo certification.Vendor timing is not live-first-seen proof;adjusted prices do not certify dividend cash,raw lots or opening liquidity.

## 后续工作 / Next work

Freeze any strong response separately before continuous CNY3m execution,standard/double costs,delay,capacity,regimes and falsification.Otherwise close this diagnostic without sign flips or endless horizon sweeps;the next epoch needs a distinct economic mechanism and finite budget. Preserve the original observation card.

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