# V11.6 最终测试报告

工程修复完成；本轮没有验证通过的新Alpha。

## 工程验收

- 完整测试：702 passed、1 skipped；Ruff通过。
- 修复门控方向、未来退出价入池、无关字段过滤、分钟可见时间连接、逐日会计与统计口径。
- 96 account-window reconciliations passed; maximum balance residual CNY0.0000000005.
- 合成校准：真实1/8 worker一致，24/24恢复第一名，0/100噪声误报（95% Wilson上界3.70%）。
- 上述经济检测不等于Court校准：全局次数DSR敏感性令24个强植入信号也全部未通过，必须保留这一限制。

## 冻结赢家的账户表现

2023 selector: `low_volatility`. Identity: `4807b4173348b9b430a61e041d649a2fbe1be670de2bb39a61a7e749109edde9`.

每个年度独立投入300万元，以下均为扣费后结果。基准为相同字段覆盖股票的理论等权组合，不是沪深300，也不是已验证可整手交易的产品。

| 年份 | 往返成本 | 账户收益率 | 净利润/元 | 基准收益率 | 超额/百分点 | 最大回撤 |
|---|---:|---:|---:|---:|---:|---:|
| 2023 | 41 | 4.79% | 143,819.97 | 5.24% | -0.44 | -10.31% |
| 2023 | 82 | 1.02% | 30,660.83 | 4.85% | -3.82 | -11.70% |
| 2024 | 41 | 29.61% | 888,449.58 | 2.58% | 27.04 | -9.67% |
| 2024 | 82 | 25.10% | 752,859.43 | 2.16% | 22.94 | -10.67% |

## 统计结论与限制

- DSR sensitivity=0.00000562; PBO diagnostic=0.55; family placebo p=1.0.
- Daily observations=242; effective=153; minimum CPCV training fold=17.
- 2023 positive mean active return: 0/24. 2024 positive total excess: 6/24 (post-hoc diagnostic count, not winner replacement).
- 2022训练、2023选择、2024受污染诊断；不是独立样本外证据。2025–2026本轮返回行数为0，历史暴露事实未被抹掉。
- 历史同频候选收益矩阵缺失，DSR只是以本轮离散度外推全局次数的敏感性。CPCV折最少样本数较低，PBO只能作诊断。
- 当前仍是24个受控机制/基准的生成比较（含线性收缩和浅树），外部LLM调用为0；没有声称自由自主因子发现已经成熟。
- 采用复权价格、分数股、固定费率、日均量容量近似，尚非整手/最低佣金/开盘真实可成交量的实盘模拟。

## 证据与后续

- Completed48 trials; aborted48 retained; historical raw trial lower bound=2866.
- Protected files=3; unchanged=True.
- Snapshot SHA-256: `b813a94d5342013488b8192e8ecf940c898ce984e47fbe2fdcb95a3c570c5a51`.
- Result SHA-256: `e2a4bb5344c7f17e1033b9dba6ed9069e749fbad4c9e32a0296e353a95958bc9`.
- Runtime SHA-256: `9c4312c345ed46c0b4785a59e89a374003e1f0e11036d56715ff6f8548e25ee8`.
- 下一步优先做可交易基准和成本/风格归因，并重建可识别的历史统计合同；不通过扩大随机模板或放宽阈值来制造PASS。冻结该轮结果，只在新方案预声明后继续。
