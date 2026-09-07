# V11.16 — Sparse ordered events / 稀疏次序事件

## 中文设计契约

预注册：[Issue184 comment5561319318](https://github.com/m-stephen/stephen-quant-agent/issues/184#issuecomment-5561319318)。
本轮不把旧因子改名：检验“个股过去分布下的冲击，随后确认”是否比只看当日确认有增量。
有限生成器组合2种冲击、2种确认、1/3日间隔，共8种身份。不是自由生成的LLM，也不是训练预测网络。
净流入字段为供应商代理，不冒充订单簿不平衡或已证实的机构交易。

| 部分 | 冻结约束 |
|---|---|
| 冲击 | flow_z>=2且flow>0；或price_z<=-2 |
| 确认 | abs(price_z)<=0.5且flow>0；或0<=price_z<=1且flow>0 |
| 标准化 | 当日flow减过去20日均值，除过去20日样本SD；当日复权简单收益除过去20日收益样本SD |
| 时间 | 必须连续全局交易日；缺失重新预热；SD为0则无事件；全部EOD可见，次日开盘入场 |
| 股票支持 | 原asof ADV>=1000万、非ST、history>=20；日K/资金流及risk字段有效；不要求分钟/竞价/筹码覆盖 |
| 事件 | start[t-lag]且confirm[t]的false-to-true；40日冷却，满仓未入选也消费触发；持有中不延长 |
| 目标 | 最多40名，各2.5%；entry=t+1，计划exit=t+21；无事件现金，不放大剩余目标 |
| 对照 | 同入场日、同12个vol/ADV格、同计划退出日；hash与confirm-only两套；剔除自身目标和全部当日合格事件 |
| 控制冷却 | 控制股票从被选入对应控制目标的信号日计40日；不足不跨格填补 |
| 选择同值 | 固定SHA256(v11.16:184:identity:policy:instrument)，升序，代码再次破同值 |
| 年份 | 2022仅预热；2023–2024连续300万账户；2025/2026不读；不跨年重置 |
| 交易 | 新政策target_changes；冻结lowvol锚点保持full_target；82/164bps，原5%滞后ADV容量/受限重试 |

首个2023交易日现金，2023信号才允许新增事件；预热命中参与边缘识别但不消费冷却。
缺少当前基础准入或前一全局交易日有效复权价格，也会重置创新历史。
每年新增次数按计划**入场年**计，避免跨年信号日混淆。
目标到期即删除；真实受阻退出仍由状态执行器重试，因此实际持仓可能超过40。
未变目标持仓漂移，但仍受既有最大单名权重裁剪；这不是保证无微小交易。
期末不强平，未满20日的持仓以期末净值计入并显式披露。
匹配的是目标机会与粗风险档，不是精确行业、beta、成交率、现金或成本。

全部50项原生NOFIT登记后才读取数值：8身份×3政策×2成本+2冻结lowvol锚点。
历史Trial下界3456→3506，失败/未运行预留不删除。原卡片、账本和5源快照hash前后保护。
探索晋级需两成本均满足：两年净收益>0、日频SR>=0.7、MDD>=-25%；对两匹配对照和lowvol总收益增量均>=3pp，逐年不落后超过5pp；每年主目标新增>=50、两匹配覆盖均>=98%；账户审计通过。
不通过时完整封存8个身份；不按结果改方向、阈值、股票支持或年份。
通过仅冻结为待深挖候选，仍需独立前向/跨期、成本容量延迟及完整统计挑战。
本轮DSR/PBO/placebo不适用正式认证，不伪造数值，不声称Alpha Court PASS。

## English contract

Eight typed sequence identities combine two stock-specific shocks, two confirmations
and one/three global-session lags. Previous20 consecutive observations provide
sample standard deviations; current observations do not enter their normalizers.
Zero variance and missing coverage produce no event. All source fields are EOD
only. This is a bounded, label-free generator, not unconstrained LLM discovery.

First-hit events have a40-session cooldown including rejected full-portfolio
triggers, next-open entry,20-session planned holding and40 desired2.5% slots.
Two controls share admission dates, risk cells and expiry clocks; confirm-only
ablates the earlier shock. Missing matches remain cash. Hash order is constant
within identity/policy/instrument. Admissions are counted by planned entry year.
No warmup trades, annual capital resets, end liquidation or future eligibility.

Fifty native no-fit trials reserve all eight identities, controls and both costs,
plus two immutable low-volatility anchor replays before numerical reads. The raw
trial lower bound becomes3506. Continuous CNY3m accounts use the existing engine,
costs, lagged capacity and missing-position accounting. New policies use
target_changes, anchors retain full_target. Adjusted fractional shares are not
physical-lot/dividend certification. Blocked exits can exceed40 actual positions.

Both cost levels must meet the preregistered positive-year, Sharpe, drawdown,
three-control increment, annual admission and98%matching conditions. A survivor
is exploratory only, never an Alpha Court certificate. Reused2023/24 history,
multiple testing and incomplete full-history statistical identifiability remain
explicit limitations. Existing candidate cards and sealed2025/26 remain intact.

## Reproduction / 复现

Use the locally ignored config with `python scripts/run_sparse_events.py --config
artifacts/sparse-events/run.local.json`. An existing operation or parent claim is
rejected. Run unit tests before numerical reads; independently reconstruct raw
support/normalization, events/targets, and all saved account/ledger metrics after.
Local source paths and machine-generated market evidence never enter git.
