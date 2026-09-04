# V10.1 Regime-robust search result / 跨状态稳健搜索结果

## Decision / 结论

`NO_RELIABLE_ALPHA`

V10.1 corrected hash-order budget bias, cross-experiment candidate replay, an
incorrectly equivalent universe placebo, and selection by peak discovery Sharpe.
It also rejects predictor fields that are not cross-sectionally variable on at
least 80% of discovery dates without reading outcome labels.

V10.1 修复了按哈希截断导致的预算偏差、跨实验重复候选、与信号置乱近似等价的
股票池 placebo，以及只按发现期峰值 Sharpe 选优。系统还会在不读取收益标签的
前提下，拒绝至少 80% 发现日缺乏横截面变化的字段。

## Real run / 真实运行

- Capital / 资金：CNY 3,000,000
- Window / 窗口：2022 discovery；2023-2024 development validation
- Sealed reads / 封存数据读取：none / 无
- Newly evaluated candidates / 最终有界轮新增候选：18
- Cumulative trial count / 累计 Trial：647
- Rejected degenerate field / 拒绝退化字段：`multiscale_divergence`
- Selected expression / 入选表达式：`rank(amihud_intraday)-rank(amount_rank_20)`

| Metric / 指标 | Discovery / 发现期 | Validation / 验证期 |
|---|---:|---:|
| Net excess return / 净超额收益 | 6.42% | 16.78% |
| Annualized net excess Sharpe / 年化净超额夏普 | 0.783 | 0.672 |
| Double-cost return / 双倍成本收益 | — | 7.41% |
| Maximum drawdown / 最大回撤 | — | -11.43% |

| Court gate / 门禁 | Required / 要求 | Actual / 实际 | Result |
|---|---:|---:|---|
| DSR | >= 0.95 | 0.00118 | FAIL |
| PBO | <= 0.05 | 0.45 | FAIL |
| Signal placebo p | <= 0.05 | 0.01 | PASS |
| Return placebo p | <= 0.05 | 0.01 | PASS |
| Universe placebo p | <= 0.05 | 0.41 | FAIL |
| Double cost | positive | 7.41% | PASS |
| Sealed forward | required for final PASS | not run | NOT ELIGIBLE |

The candidate is economically interesting but depends too heavily on exact
liquid-universe membership and has weak multiplicity-adjusted evidence. It is
retained as a tombstoned research result, not promoted as alpha.

该候选在经济表现上值得记录，但对精确流动性股票池依赖过强，且多重检验调整后的
证据很弱。因此它只作为研究结果和墓碑保留，不提升为可用 Alpha。

## Remaining integration work / 剩余集成工作

The warehouse's verified schema-aware adapter successfully resolves the original
Chinese fund-flow, auction and chip columns. Mojibake seen in an interactive
PowerShell listing was a console-rendering artifact, not persisted schema damage.
V10.1 did not yet join those sources into its empirical panel; V10.2 will use the
existing verified adapter and explicit canonical mappings rather than ordinal
column positions.

仓库现有的已验证 schema-aware adapter 可以正确解析资金流、竞价和筹码的中文原始
列。交互式 PowerShell 列举中看到的乱码来自控制台渲染，并非持久化 schema 损坏。
V10.1 尚未将这些来源接入实证面板；V10.2 将复用现有已验证适配器和显式规范字段
映射，仍不会按列序号猜测含义。
