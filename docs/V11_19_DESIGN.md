# V11.19 — Date-balanced within-cell pairwise ranking

## 中文：问题、范围与停止条件

上一轮条件风险配置没有产生超越冻结组合的完整增量。本轮只改变学习目标：在当时风险/流动性相近的股票之间学习相对排序，并检验非线性跨源交互。不是扩大参数遍历，不把旧因子换名当新机制。

固定使用原 V11.4 epoch-002 五文件快照，SHA-256 `b813a94d5342013488b8192e8ecf940c898ce984e47fbe2fdcb95a3c570c5a51`。2022训练；2023/2024是已重复使用的开发史，不是独立样本外证明。2025/2026不读取。仍是候选研发，不交易、不购买、不自动合并main。

### 完整预声明预算

线性/二次基函数 × 完整排序/风险排序/训练标签打乱排序/收益差回归 × 82/164bps = 16账户。固定hash、同格低波、原低波组合、原稳定组合四对照 × 两成本 = 8账户。共24个连续300万元账户、16个独立模型、32份原生年度fit证据；仅线性完整排序和二次完整排序是两个主要身份。

继承历史Trial下界3600；本轮一次性原生预留24项，变成3624，包括所有对照、成本场景与失败。不能把股票对数、账户数或重复历史当独立证据。未获预登记评论及代码冻结之前，不读取新实验的市场数值；失败操作保留，禁止覆盖重试。

### 输入与排序股票池

复用现有ADV≥1000万元、非ST、已观察历史≥20、当日源字段可见的股票池；不使用未来成交/终点决定入池。资金流、竞价、筹码三源连续20个**全局**交易日，缺失重置且不填充，当前三风险字段有限。

六输入依次为20日波动、20日收益、60观察日ADV、资金一致性、竞价尾部方向、筹码成本宽度路径效率。后三项完整公式沿用 `temporal_increments.path_values`，筹码宽度是(85分位成本−15分位成本)/加权成本，不冒称集中度上升。

按当前波动及代码排序，floor(5*i/N)分5格，每格再按ADV及代码分4格，共20格。每个输入在当日同格中取平均并列秩，映射为2*rank/(Ncell+1)−1。这是当时可见的无拟合横截面变换；不使用全样本标准化。

### 标签与训练时钟

每第五个全局信号日，在每格按固定SHA256(`v11.19:184:`+代码)取前64只，两两相邻配对，股票不重复，奇数末只舍弃；**先确定配对再读结局**。标签为下一交易日开盘到第21个后续交易日开盘的20日复权毛收益差。

缺少有效入场开盘的腿保留拒绝证据，该对不参与拟合。缺终点时取入场至终点前的最后有效收盘，仍保留；不得按未来幸存者删去亏损者。该标签不计成本、限价和成交，是相对排序代理，不是可交易P&L。详细入场/终点/陈旧标记全部留档。

2023模型只用2022；2024模型用2022–23。构建标签前截断2024之后，并剔除训练末尾5个全局交易日，年度模型再按自身成熟截止过滤；至少30个实际信号日。stride5与horizon20有重叠，日期等权并不能消除时间相关，不能用配对数计算独立样本量。

### 两个小模型及对照

线性基为六输入，二次基为六输入加全部i≤j的乘积，共27维；风险对照仅前三输入，分别3/9维。无截距。设计矩阵为phi(left)−phi(right)，不是phi(left−right)。完整/风险/打乱模型用pair-logistic交叉熵，目标为收益差正/负/零对应1/0/0.5。收益差回归采用平方损失，无分类符号标签。

每日期总损失权重相等；日内各有效股票对等权。L2固定0.01，零初值Newton最多40步、梯度上界1e−9，Armijo最多32次二分。不搜索正则化、方向、期限或初值。独立审计验证源配对、矩阵、梯度驻点、正定Hessian和训练损失；不依赖再次调用生产优化器自证。

打乱仅在每个训练日期/风险格内把接受腿收益循环平移floor(Nlegs/3)。这是一个固定机制对照，**不产生placebo p值**。RankNet仅借鉴排序损失，不引入深网，也不声称金融收益来自论文结论。原文已核对Section3目标函数：[Burges et al. 2005](https://www.microsoft.com/en-us/research/wp-content/uploads/2005/08/icml_ranking.pdf)。

### 持仓与成本

每格2只，每个分仓目标2.5%；旧名单仍在前三名则保留，不足格保留现金，不跨格补足、不重归一。0/5/10/15四个固定20日分仓在一个连续净额账户内运行，前日信号、次日开盘，跨年不重置。排序分数不解释为bps收益，不套用已校准交易门槛。

新政策均target_changes；原低波和原稳定锚点保持原始目标字节与full_target，并与V11.18账户哈希逐字节匹配。标准成本每边佣金6bps、每边滑点30bps、卖税10bps，总往返82bps；双倍164bps。每日成交容量上限为前期60观察日ADV的5%。现金利息为0，无杠杆/卖空；复权碎股模型不是券商级撮合。实际漂移权重、现金、换手和持仓数全部报告，不能把风险格匹配称精确beta/行业/换手匹配。

### 探索筛选与后续挑战

每主要身份必须在两成本下均满足：两年净收益正、年化日收益Sharpe≥0.7、最大回撤≥−25%、对**每一个**同基风险/打乱/回归对照及四固定对照总增量≥3百分点、每年差≥−5百分点、每年平均选中格配额≥95%，且源、fit、目标、价格、容量、持仓、现金审计全部通过。

该筛选不是Alpha Court，DSR/PBO/placebo未运行则必须null，不写PASS。只有完整幸存者才原样冻结进入独立预声明的有限深度挑战，保留3600+累计试验和时间相关；不在揭示结果后修改本轮门槛。若无幸存者，保留全部负结果后根据可解释失败设计下一预算，不承诺一定存在可用alpha。

## English contract

This experiment tests date-balanced within-risk/liquidity-cell pairwise logistic ranking against relative-return regression and seven economic comparators. Two fixed bases, two execution costs and four anchors form24 accounted trials,16 models and32 native annual fits. Research debt moves3600→3624;2023/2024 are reused development history, with no2025/2026 access.

Stock pairs are selected by fixed hashes before outcomes. Gross20-session next-open labels preserve unsupported-entry and missing-endpoint evidence. Current cross-sectional ranks are stateless, while supervised fits remain in mature annual prefixes with five-session embargo. Overlapping labels and correlated pairs do not create independent observations. The nonlinear basis applies before pair differencing; date weights, regularization and optimizer settings are fixed.

The two primary identities must exceed every registered comparator under standard and doubled costs, annual positivity, drawdown, Sharpe and coverage screens. A single shuffled control is not a placebo p-value. Scores are rankings, not calibrated return forecasts. Passing engineering or exploratory screening is not an Alpha Court certificate. All source, model, allocation, native registry, account and failure evidence is retained. No automatic main merge, live trade or purchase is authorized.
