# V2.7 M0：正式停止与信息防火墙

## 目标

M0 在任何新收益研究开始前，将 V2.6 的失败转化为不可逆、可重放的治理状态。它不读取
行情、不生成新因子、不调用远程模型，也不增加 inferential trial。

## 合同

- 以 GitHub Issue #67 为权威来源；
- 保留此前 48 次 inferential trials；
- 为 flow-confirmation 经济机制建立 family-level tombstone；
- horizon、threshold、Top-K、残差化、regime 或组合包装不能逃逸 tombstone；
- 真正不同的经济机制不会仅因使用相同字段而被误杀；
- 2025 追加标记为 `CONSUMED_VALIDATION`；
- 2026 保持 `SEALED_FINAL_TEST`；
- 历史配置和 artifact 不回写。

## 信息防火墙

研究文件只能通过显式 allowlist manifest 访问。manifest 截止日期不得晚于
2024-12-31，文件逻辑 ID、路径和哈希必须唯一。接口不提供目录遍历；未列入 manifest
的读取会在打开文件前被拒绝。公开 artifact 只保存脱敏逻辑身份和哈希，不保存本机路径。

## 验收

- 原候选和改变 horizon/wrapper 的后代均返回 `STOP_FAMILY`；
- 独立 mechanism fixture 返回 `EXPLORE`；
- window event 与 tombstone 均 append-only；
- 2025/2026 读取、列举和哈希为零；
- 新 trial、远程模型请求和 live-trading authorization 均为零；
- 中英文产物通过离线 SHA-256 重放。
