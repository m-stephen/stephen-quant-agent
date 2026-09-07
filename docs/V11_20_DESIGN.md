# V11.20 — Frozen-policy gross-to-net diagnosis / 冻结策略毛净收益诊断

## Decision and scope / 决策与范围

Answer why the completed V11.19.1 ranking policies fail: is gross incremental strength absent, or is implementation friction the main obstacle? This is a bounded diagnostic, not a new Alpha competition. Implement the previously published V11_20_PLAN without altering the two failed primary identities or their 82/164bps gates.

对全部12份原目标各重放一个零费用路径，再与24个不可修改的原付费账户比较。只将佣金、卖税、滑点同时置零；不重新训练、不重新选股、不搜索期限或符号。零费用收益不代表可实现收益。不得用本轮最好曲线晋升旧失败候选。

## Frozen evidence / 冻结证据

- Parent V11.19.1 RESULT SHA-256: `319dcb2dd2e85aa208424c70f4e8e2c2160657f44ab1fae480f3c0a1355c7337`.
- Parent audit SHA-256: `d35a0c906b28e0704c9c7d43df55e9139f0445ace309a1605a78cef3ec2626f7`.
- Original aborted operation remains immutable: `3c254b86990b1bc801e58ace3bd8da30a079c162d9ee7bb718e67cf9409bb034`.
- Five-file frozen snapshot: `b813a94d5342013488b8192e8ecf940c898ce984e47fbe2fdcb95a3c570c5a51`.
- Original V11.11 stability card: `c854fad704e08902051a3c4f2f25fdaeb8c9e7d32cda6b69bb76bf3fc6302134`.
- 2022 warmup; 484 continuous sessions in repeatedly reused 2023–2024 development history. No 2025/2026 access, no new external sources. Dates cannot be relabeled as independent OOS.

## Exact twelve replays / 精确12次重放

Two bases (linear, quadratic) × four policies (full, risk, shuffle, regression), plus hash, lowvol, original_lowvol, original_stable. Twelve new native Trials have an explicit no-new-fit contract. Their receipt binds all original 16 models and 32 native fits. No model optimizer or prediction code is called. Charge 12 before numerical source, target, model or return decoding: **3648 → 3660**, including failure. The 24 inherited cost accounts are not rerun or charged twice.

Each copied target file must match its parent's raw bytes and canonical SHA. Decision times, dates, member weights, forced exits, rebalance flags and all 484 sessions are unchanged. Ten policies use target_changes; the two original anchors retain full_target. Initial capital CNY3m; max target weight 2.5%; past-only 60-observation ADV ×5% capacity; stale writeoff 20 sessions. Existing exchange/suspension execution semantics remain unchanged. Accounts use source-adjusted fractional units, not broker raw lots or separate dividend cashflows.

## Runtime and independent checks / 运行与独立核验

`run_gross_net_attribution.py --config <ignored local config>` requires a clean frozen commit and positive Issue184 preregistration ID. Config contains parent_dir, original_tree, input_dir, output_dir, runtime_commit and preregistration_comment; real paths stay outside Git. Input/output overlap and existing operations are rejected. Parent claim and all outputs use exclusive creation. The original two parent operations, snapshot and old card/targets are hashed before and after. Partial failures retain ABORTED and native reservations; no silent rerun.

`audit_gross_net_attribution.py --output <operation> --inputs <frozen inputs>` independently enumerates all 12 plans, checks original 24 paid results and 16/32 inherited lineage, source-adjusted opening-fill shares, closing marks and lagged ADV capacity. Independent saved-account SQL checks 36 NAV/fee/drawdown paths, annual compounding, cash/share continuity, target clocks and native identities. Independent formulae verify 24 gross-to-net drags and 42 full-minus-control comparisons. This verifies saved paths and frozen engine use, not a second complete exchange simulator.

Cost-path drag = zero-cost return − paid return. Direct fees / initial capital is separately shown. Their difference includes cash scaling, compounding and changed fills; it is not causal fee impact or achievable savings. Gross/net increments compare the same predeclared controls at each cost. No CSI300 market benchmark claim.

## Acceptance and limitations / 验收和局限

- Synthetic planted compounding example rejects simple fee addback; altered targets, missing source opens, changed shares, lineage tampering, budget/scope expansion, promotion and preexisting outputs fail closed.
- Full tests + Ruff; one exclusive actual run; independent audit; all 36 aggregate records and all 42 comparisons in Chinese/English reports and reproducible companion notebook.
- Native report schema QA; visible/pixel rendering remains deferred under quiet-until-usable instruction. No fabricated frontend QA. Notebook fallback clearly labels ordinary-Python execution if optional Jupyter dependencies are absent.
- Validated Alpha remains false, original screen_survived remains false/false, DSR/PBO/placebo remain null/NOT_RUN. Engineering PASS is not Alpha Court PASS. No main merge or trading.

## Next bounded decision / 下一阶段决策

Gross weakness against controls across years calls for a genuinely different information mechanism after static catalog de-duplication, not higher polynomial degree. Gross strength destroyed by costs calls for a newly registered, train-prefix-only turnover-aware decision objective. Mixed yearly direction calls for explicit instability acknowledgement, not selective year deletion. Any new finite family needs separate preregistration and Trial debt; any eventual survivor must be frozen, challenged and independently validated without lowering Court thresholds.
