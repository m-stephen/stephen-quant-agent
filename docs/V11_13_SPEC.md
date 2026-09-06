# V11.13 持仓稳定性与权重维护 / Membership and weight maintenance

## 目标 / Objective

将稳定成员与减少权重维护分别测试，不将实现优化冒充预测 Alpha。
Separate membership retention from weight maintenance;implementation benefit is
not automatically predictive Alpha. Preregistration:Issue184 comment5560589655.
The frozenV11.11 card,targets and original worktree runtime remain unchanged.

## 冻结实验 / Frozen experiment

- Two existing target schedules:stable_lowrisk and lowvol_top40_buffer10.
- Two maintenance modes:legacy full_target and newly named target_changes.
- Three cost levels:0/82/164bps;12 native no-fit Trials,3322→3334 including failures.
- 82bps is6bps commission each way,10bps sell tax,30bps slippage each way.
  164bps doubles every term;zero fees only identify model-path counterfactuals.
- Same300万元 continuous adjusted-fractional account,four fixed cohorts,
  2023–2024 reused development history,source snapshotb813a94d…5a51.
- No fitting,alternate phases,threshold sweep or2025/2026 read.

## 新维护规则 / New maintenance rule

Only on existing refresh dates,changed declared weights and pending constrained
requests reset toward target weight × current opening NAV. Already completed,
unchanged targets retain actual shares. Capacity/tradability/funding-limited
requests retry on the next refresh;the1e-8CNY tolerance is numerical,not a tuned
economic band. A target change supersedes pending intent. Every refresh also
requests trimming current weights above theexisting2.5% cap. Forced exits take
priority. Close-time drift and blocked sells can leave realized exposure above
the cap;report this,never claim an enforceable hard daily cap. No close price is
used to size that same day's opening order. Original engine defaults unchanged.

仅改变预先声明的维护规则；受限订单后续重试，卖出后按可用现金缩放买单。
不补仓已完成且目标未变的持仓，但超限减仓仍申请执行。当前收盘价不参与开盘决策。
新规则不是四个独立资金账户，也不是真实整手或公司行为现金账本。

## 判断与测试 / Decisions and tests

Require positive2023 and2024,Sharpe≥.7,drawdown≥−25%,total matched-control
increment≥3pp and each-year increment≥−5pp,at both82and164bps. This is a historical
economic screen only;no relaxation of the separate Court thresholdsDSR≥.95,
PBO≤.05,eachplacebo≤.05 and path/cost/capacity requirements.

Exact82bps parent-account byte replay;frozen source/card/target hashes;single-use
claim and12native reservations before target decoding/source values;failed slots
retained. Test unchanged/changed targets,forced exits,capacity/missing/blocked
retries,positive cash,cap drift,timing,completebudget and repeated-operation refusal.
Independently reconcile saved accounts via SQL and Python,SQLite no-fit bindings,
full cost formula,cash changes,mark balances,annual compounding and matched screens.

反事实成本拖累=零费完整账户收益减收费完整账户收益，包含路径与复利影响，
不能等同于票据费用加回。成员增量和维护增量是本模型条件下的历史对比，
尚未控制全部行业/规模暴露或搜索后选择偏差。

## 可复现与边界 / Reproduction and limits

Copy configs/v11.13-stability-attribution.example.json to an ignored *.local.json;
configure original operation/tree and frozen input paths. Run
`python scripts/run_stability_attribution.py --config YOUR.local.json` once after
preregistration,then `python scripts/audit_stability_attribution.py`.
The audit default is the recordedepoch-001;review its path before another operation.
Completed claims are intentionally not replayed;independent verification reads
saved evidence without rerunning the market. Generated artifacts remain ignored.

No source purchase,credentials/raw data/localpaths inGit,main merge or live trading.
Reference:[Bailey and López de Prado,DSR](https://doi.org/10.2139/ssrn.2460551)
explains why repeated search requires selection-aware validation;this experiment
does not manufacture a DSR value from the twelve related control accounts.
