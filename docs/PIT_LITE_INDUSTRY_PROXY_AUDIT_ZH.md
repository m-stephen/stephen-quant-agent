# PIT-Lite 日 K 行业代理审计

## 结论

2022–2024 日 K 行业字段判定为 **`B_CURRENT_LABEL_BACKFILL`**，仅允许用于行业暴露、
集中度和敏感性诊断，不得用于行业内排序、行业轮动或代理行业中性化。

## 证据

- 726 个显式允许的日分区，3,731,699 行，5,523 只股票，110 个行业；
- 同日股票重复键和行业冲突均为 0；
- 行业缺失率 1.8753%；
- 5,343 只股票拥有至少 20 个有效观测，但历史行业标签变化股票为 0；
- 审计不读取候选收益，`inferential_trial_delta=0`；
- 输入 Manifest SHA-256：`7bf9f460aaed611dcfdb3977ebed456a2ab2f1243d64e832d748a02e10e8681b`；
- 结果 SHA-256：`0c7de0e6d93cc1de11565321d90519a0a3c691803bc5314c9106e9b3fa7fec21`。

该结论不表示供应商数据错误，只表示该字段没有提供股票级历史行业变更证据。Issue #92
仍负责未来的权威历史行业成员数据；当前因子研究继续走行业无关通道。

## 重放

本机路径由 gitignored 配置提供：

```powershell
stephen-quant qd-industry-proxy-audit `
  --paths-config configs/qd-paths.local.json `
  --output artifacts/issue-98-industry-proxy-audit
```

命令只选择文件名符合 2022、2023、2024 日期分区的 CSV，生成 Manifest、JSON 和中英文
Markdown。真实绝对路径和生成产物不提交 Git。
