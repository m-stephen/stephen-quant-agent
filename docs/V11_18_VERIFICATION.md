# V11.18 verification / 验证记录

Research result: **0/4 full exploratory survivors; no certified usable Alpha**.
44/44 native accounts completed once; 72 native supervised fit records; no market
or auditor restart, no failed or empty reservation. Raw trial lower bound3600.
All44 accounts, including controls and failures, remain in RESULT.summary.json.

Runtime commit: `0a86643d3114a9dfd83a88a190f3d3cc8df35080`.
Preregistered [Issue184 comment5562202690](https://github.com/m-stephen/stephen-quant-agent/issues/184#issuecomment-5562202690).
[PR196](https://github.com/m-stephen/stephen-quant-agent/pull/196) is stacked on
unmerged PR195; no main merge or trading is authorized.

## Engineering / 工程

- Premarket full suite982passed1skipped175.58s;30new synthetic regressions.
- Postmarket full suite982passed1skipped174.56s;Ruff src/tests/new scripts PASS.
- Immutable five-source input snapshot,12protected files unchanged.
- Independent audit126operation evidence file hashes unchanged after reporting.
- Independent SQL726states,19,000proxy components,95labels; separate standard-library
  normal-equation solver verifies4models;all22target sets and72native fits pass.
-44cash/NAV/fees/year/SR/DD/account paths reconcile;largest balance residual
  `4.656612873077393e-10` CNY. Raw-source capacity and current-price mismatches:0.
- Original lowvol full_target accounts at both costs replay parent bytes exactly.
- No2025/26 reads. Old frozen card/targets/ledgers preserved;root23old changes untouched.

## Findings and limits / 结论及边界

Both-year common-state coverage100%. All four primary identities fail total
increment;all fail positive2023 under164bps. This is not an unavailable-input
failure. Standard-cost primary Sharpe ranges0.7823–1.0789,but this is insufficient.
Stable_lowrisk mean_second at82bps earns17.3168% total,20231.0122%,202416.1412%,
compared with32.9486% for the unchanged target_changes stable foundation.
The mean alternative earns16.0817% with Sharpe1.0789;do not silently select it
instead because its Sharpe looks better. Every identity and cost remains visible.

Both forecast rules produce25% exposure on every241predicted2023dates;there is
no changing forecast allocation in that year. In2024they vary,but do not beat
all controls. Training sizes46/94 nonoverlapping intervals are small. Gross
200-name basket labels do not identify net execution returns of the40-name
frozen portfolios. Fixed controls match training mean exposure,not realized
test risk/cash/turnover. These observations identify limitations,not permission
to retune exposure floors,signs or windows after seeing returns.

## Report QA / 报告验收

Bilingual Markdown and full44-account JSON archived. Native report has8primary
rows (4identities×2costs),zero baseline,explicit cost series and six numeric
control-increment columns. Initial artifact validation rejected a nested-cell
object;report-only v2 flattens those fields and passes native schema validation.
Original invalid artifact is retained privately. No economic evidence changed.
Canonical reader artifact is `report-artifact.v2.json` in the ignored operation.
Visible/pixel QA deferred under userquiet;no rendered widget or parallel HTML claim.

Notebook `notebooks/V11_18_AUDIT.ipynb` executes all4plain-Python cells in order,
including independent SQL recomputation of44savedaccount aggregates. Optional
nbformat/nbclient/ipykernel are absent;Jupyter kernel/frontend QA is NOT_RUN.
This notebook binds the raw SQL already executed by the audit;it does not claim
to rerun the full source join or start another market experiment.

## Immutable identities / 不可变证据

| Artifact | SHA-256 |
|---|---|
| Original five-source snapshot | b813a94d5342013488b8192e8ecf940c898ce984e47fbe2fdcb95a3c570c5a51 |
| Runtime source | aaa6c80fc47af01f461adafea05a49653a40aac25591cf85f40d7d7a08bf01b8 |
| Driver | 79785413cb29cb2a994f8ca08aed98ed2021ec592e62dd60a436d2c163a49565 |
| Independent auditor | 0ff1475cb264e78067a13d191ee86311dc34ecd8912b725045d51771e155e58f |
| RESULT | c0451e1b077ee67c8ef99e4dc982fab7c546b433b254d270baa53b3082c9e83f |
| Independent audit | 6b4fd781daf309fb87ccddd10b921f49a91043a120d1fd4b692c9ae113c5c910 |
| Validated report v2 | 16db1a2bacd53b59f07ecccc6a5051618539bf6115c01e7ecbf00d65cfa54c13 |

Runtime CI34060549124SUCCESS. Final evidence-head CI must be checked after push;
do not equate the earlier runtime run with final-head confirmation.
