# V11.18 conditional risk allocation / 条件风险配置

## Frozen question and budget / 冻结问题和预算

Test whether a small train-only conditional return/second-moment model adds net
value by scaling the ORIGINAL frozen lowvol and stable_lowrisk target portfolios.
This is portfolio exposure research, not a new stock-ranking factor or a claim
that volatility timing transfers from another market.

Exactly 44 native accounts: 2 bases x2 mean rules x4 policies x2 costs=32;
2 bases x1 second-moment-only control x2 costs=4;2 bases x2 unscaled execution
anchors x2 costs=8. Debt3556->3600. Four primary identities, not44 independent
hypotheses. All training, controls and costs count; no adaptive search or retry.

## Information contract / 信息契约

Same frozen V11.4 daily/flow/chip/auction/minute snapshot; only daily information
enters this new model. 2022 is training/warmup,2023/24 reused development;
no2025/26 access. Keep original V11.11card and both target artifacts unchanged.
No additional source purchase or industry backfill.

Daily state uses the common currently eligible set with an adjacent global-session
adjusted close return: non-ST,ADV60>=10m,history>=20,finite ret20/vol20/ADV and
valid current and immediately prior eligible bars. At least200 names required.
Four features: breadth(ret20>0),mean(ret20),mean(vol20),population std(return1).
No cross-sectional filter uses later survival, open or return information.

The SUPERVISED TARGET is an unconstrained gross five-session low-risk basket
proxy, NOT executable portfolio P&L: at each fifth global signal session from
the beginning of2022, select the200 lowest-vol names (tie by instrument), freeze
equal weights, use next-session adjusted open to the open six sessions after the
signal. Missing entry remains cash; missing endpoint is marked at the last
available earlier close, or entry open. Never renormalize missing names or select
future survivors. Require>=95% entry bars and>=95% fresh endpoints among entered
names for a training row; preserve all rejected rows and component evidence.
Limits, capacity and costs apply to actual backtests, not this gross forecast
proxy. Label cash earns0; proxy returns cannot be advertised as tradable returns.

Fit2023 on2022 and fit2024 on2022-23. Remove final5 global training sessions;
all label endpoints must mature before that cutoff. Use nonoverlapping five-
session target intervals, at least30 supported training samples. Every transform
is fitted only on those samples. A linear ridge with standardized four inputs,
unpenalized intercept and mean-squared-loss penalty lambda=1 predicts R and R².
No model/penalty/sign search. R² is a second moment, not conditional variance.
The matching shuffled model rotates complete training target pairs by floor(N/3)
rows, preserving their distribution, entirely inside the training prefix.
One rotation is a falsification CONTROL, not a placebo p-value.

For mu and q predictions, denominator floor=max(1e-8,0.1*training_mean_R²).
Two policies use mu/(10*mean_R²) and mu/(10*predicted_R²), respectively.
Risk-only control uses training_mean_R/(10*predicted_R²). Clip to[.25,1] and
round to nearest.25 (ties upward). No leverage; uninvested cash earns0.
Risk aversion10, horizon5 and quantization are fixed before numerical use.

## Controls and execution / 对照与交易

Each primary has: (a) fixed exposure equal to its training-sample mean allocation,
(b) the same model's exposure delayed20 GLOBAL sessions, using the training mean
until such a prior prediction exists, (c) shuffled-label model, (d) risk-only
model, (e) unscaled original targets under target_changes and (f) byte-original
full_target execution. Training-mean matching is NOT exact OOS exposure or
turnover matching. Report those differences and do not causally attribute them.

Exposures refresh at execution indices1,6,11,... across the continuous2023-24
calendar, using the preceding session's state. No annual schedule reset. At a
refresh with unavailable state use.25 for dynamic models; fixed control stays at
its training value. Daily model predictions are ledger-bound before feature use.
On a base refresh or exposure refresh, multiply its last-known live desired
weights; preserve forced exits. Targets never use realized future NAV.
Actual continuous CNY3m accounts use frozen82/164bps,laggedADV capacity,limits,
suspension/stale accounting and target_changes mode; original replay anchors
alone use full_target. Adjusted fractional units are not physical-lot evidence.

Both costs must pass BOTH years positive,Sharpe>=.7,MDD>=-.25,total return
increment>=3pp versus EVERY control and annual difference>=-5pp;all account,
provenance and model audits pass;state support>=95% dates in EACH year.
Report all four identities and realized cash,turnover,exposure and baseline
differences. Reduced risk or costs alone are not evidence of a new Alpha.
Any survivor is frozen before deeper predeclared falsification/Court challenges.
No DSR/PBO/placebo certification from repeatedly reused development history.

## Engineering acceptance / 工程验收

Synthetic tests: future poisoning;missing days/labels;nonoverlap/maturity/purge;
train-only centering/scaling/ridge and shifted target pairs;finite bounded
exposure;exact20-session lag;annual boundary;cash/forced-exit propagation;
original targets unchanged;native supervised fit before every prediction.
Independent raw-source SQL reconstructs states and proxy components; independent
normal equations verify all fits, then exposures/targets and all44 account paths.
Preregister before first new market numerical read; retain failures and44ledger
reservations. Publish bilingual summaries and machine-readable aggregate evidence.

Static search found existing regime proposal labels and diagnostics but no
implemented train-only cash overlay in discovery/scripts/V11docs. This is bounded
repository evidence, not a claim of novel finance methodology.

Motivation only (publisher abstracts checked, not full-paper replication):
[Moreira & Muir2017](https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12513)
and [Chi et al.2021](https://onlinelibrary.wiley.com/doi/10.1111/irfi.12336).
Their differing volatility/return findings caution against prespecifying an
inverse-volatility sign as universally valid in A-shares.

中文摘要：在两份原样冻结的基础股票组合上，只调整风险仓位，不重新挑股。
模型只在过去成熟标签内拟合，固定44账户和两成本，配备固定仓位、滞后预测、
打乱训练标签、纯风险和双执行基线。所有不足、现金和换手差异如实报告；
低仓位降低回撤或少交易改善成本，不自动等于发现了可用Alpha。
