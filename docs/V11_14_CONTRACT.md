# V11.14 风险分组机制研究 / Risk-stratified mechanism study

## 决策与假设 / Decision and hypotheses

不继续修补V11.11低波稳定配置的弱年。保留原卡和目标不变。检查此前仅选最低200波动股票、线性预期收益替换门槛是否压制了机制活动。本轮使用全量当时合格股票分组，固定三个联合排序假设；不是保证这些假设成立，也不声称发明了全新基础信号。

Preserve the old frozen card and targets. Test whether the lowest200 volatility pool and fitted linear swap hurdle suppressed mechanism activity. New identities combine existing temporal primitives with full-support risk strata and nonlinear joint ranks; they are hypotheses, not established causal effects or novel primitives.

## 读取前冻结 / Freeze before numerical reads

- 输入快照 / snapshot: `b813a94d5342013488b8192e8ecf940c898ce984e47fbe2fdcb95a3c570c5a51`.
- 父RESULT / parent: `5f66f5d5c1b77dff2763df7d69f14c45e3273474a809329b49c9193d8daf3093`.
- 2022仅特征预热，2023–2024为重复暴露开发历史；不读取2025/2026。/ 2022 warmup, reused2023–2024 development; no2025/2026.
- 延用当时ADV>=1000万元、非ST、至少20日历史、可见时间门禁；三种源均需连续20个全局交易日观测，缺失重置，无填充。/ Inherited as-of eligibility and availability;20 consecutive common source sessions, gaps reset, no filling.
- 波动率排序后三等分；每组再按波动率两等分、每半按ADV两等分，得到四格，均按代码确定性破同值。/ Three vol strata;two vol halves × two ADV halves per stratum; stable instrument ties.
- 每格10股、保留前13名中的原目标、缺额按排名补齐；不足不跨格填充、不扩大权重。每组40股、每股2.5%、四个0/5/10/15日相位、20日持有、次日开盘。/ Ten per cell,top13 retention;no cross-cell fill/rescaling;40names,four fixed cohorts,next open.
- 同日格内平均秩/(N+1)，无标签拟合；三个固定向上分数如下。/ Unfitted contemporaneous cell ranks;fixed high-score direction:
  1. 资金承接 / flow_price_absorption = rank(flow_consistency) × (1−rank(ret20)).
  2. 安静吸筹 / quiet_accumulation = rank(flow_consistency) × (1−rank(chip_path_efficiency)).
  3. 竞价衰竭 / auction_exhaustion = (1−rank(auction_tail_balance)) × (1−rank(ret20)).
- `concentration`仍是筹码宽度(cost85−cost15)/weightedcost，并非越高越集中。路径方向越负代表宽度收缩。/ Negative chip path means shrinking width,not a claim of better source quality.
- 每组配固定hash对照和价格反转对照，同格配额及保留规则；另重放原严格低波锚点。只能说粗风险/流动性匹配，不能说行业、beta、规模、现金和换手完全匹配。/ Same-cell hash and reversal controls,plus original lowvol anchor;matching is coarse only.
- 连续300万元复权碎股模型账户，默认full_target执行；82bps和164bps（佣金/税/滑点逐项翻倍），不修改成本/容量规则。/ Continuous CNY3m,legacy execution,base/doubled full cost path.
- 3组×(3机制+2对照)×2成本+2锚点=32个native无拟合账户Trial，全部先登记；历史下界3334→3366，失败和未用保留。/ Reserve all32 before data;no debt reset.

## 验收 / Acceptance

工程：合成前缀不变、缺失重置、格子/配额/时间/账本失败关闭；完整pytest/Ruff；独立SQL和逐日现金/持仓核对；原锚点字节重放一致。

Engineering: synthetic prefix invariance,gap resets,partition/quota/timing/ledger rejection;full pytest/Ruff;independent SQL,cash,marks,fees and original anchor byte replay.

经济线索：两种成本都需2023和2024分别正收益，年化日收益Sharpe>=0.7，最大回撤>=−25%；相对同组hash、同组反转和旧低波锚点各自总收益增量>=3个百分点、年度增量>=−5个百分点。全九个机制-风险组一起展示，不挑最优组冒充全家族通过。

Economic lead: both costs must pass positive years,Sharpe>=.7,MDD>=−.25,total increment>=.03 and annual increment>=−.05 against all three controls. Show all nine policy-stratum identities,not just the winner.

通过只允许冻结深入挑战，不是Court。全家族purged CPCV/PBO、经验矩DSR、多重检验、三类placebo、可信真实成交和独立证据仍必需；不降低DSR .95/PBO .05/placebo .05及路径门槛。全部失败则保留失败族、继续另一有限机制批次，不能在已暴露弱年上调方向或门槛。

Passing means freeze for further challenge,not Court certification. Full-family purged CPCV/PBO,empirical-moment DSR,multiplicity,three placebos,credible physical execution and independent evidence remain required. No threshold relaxation or post-hoc repair of a weak year.

方法依据 / Method reference: [Bailey and López de Prado, Deflated Sharpe Ratio](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf) distinguishes selection bias/non-normality correction from an unadjusted best Sharpe. This epoch does not supply a fresh inferential certificate.

## 报告约定 / Report contract

中英文Markdown、机器JSON与native report从独立审计生成。图表用32行账户粒度、16种配置×两种成本的分组柱图，零基线、收益小数比率，保留年收益/成本/回撤/成交/对照信息便于核查。SQL为原始账户汇总，不用最终结果重选替代原始查询。普通未认证结果遵守仅可用Alpha通知约定，native可见与像素检查延后并显式记录；不声称已完成可视验收。不并行生成HTML，不发布到Sites。

Bilingual Markdown,JSON and native artifact from independently audited evidence. Grouped bars:32accounts,16allocations,two costs,zero baseline,fractional returns,rich adjacent metrics;provenance retains original account SQL. Ordinary noncertified findings remain quiet;visible/pixel QA explicitly deferred,not claimed complete. No parallel HTML or Sites publication.
