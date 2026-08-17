# V2 M1 测试结果（中文）

## 结论

- **工程验收：通过。** 三个结构化假设均可确定性编译为 executable、PIT-safe 表达式族。
- **安全验收：通过。** 非法算子、超长窗口、不安全除法、量纲冲突、coverage 不足和决策时点越权均在数据求值前 fail closed。
- **搜索约束：通过。** Explore 只能选择事件对应的白名单蓝图；Mutate 每次只能修改一个已有 lookback，并保留 parent lineage 与硬预算。
- **重放约束：通过。** frozen selection 只解析已经保存并校验哈希的原始响应，没有模型或网络回调。
- **研究结论：未产生 Alpha。** 本阶段只验证编译和治理能力，没有读取收益、标签、IC 或封存窗口。

## 三个可执行族

1. 资金流—价格背离；
2. 大单资金流短长周期 surprise；
3. 融资买入强度。

这些表达式均使用现有 safe DSL 和已登记数据字段，保留 V1 provenance，同时生成 V2 分层 ID。

## 验证记录

- M0–M1 定向测试：20 项通过。
- 全量测试：199 项通过。
- 静态检查：通过。
- Python 编译检查：通过。
- 新增实证 Trial：0。
- 2025 validation / 2026 final test：未打开。

## 下一步

进入 M2：建立 bounded novelty gate、typed cheap diagnostics、冻结 benchmark 和 workload-reduction 验收，避免重复候选进入昂贵 CPCV。
