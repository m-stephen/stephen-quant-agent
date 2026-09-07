# V11.19 initial epoch: numerical abort, not a market verdict

- Runtime2d57e2d6c87624a2ed5d7436d133f8a8df32ad0a; Issue184 preregistration5562552983; PR197.
- 24 native Trials reserved; historical debt3600→3624 permanently. Zero completed accounts, no performance result,9 completed model artifacts.56,320 pair evidence rows; annual supported fit samples25,588/56,301 pairs over40/88dates. Pair counts are not independent observations.
- Failure: quadratic/full2024 Newton line search. Same-objective diagnostic shows max gradient1.6723326669e−9 before the step and1.3660947373e−17 after the full step. Required Armijo decrease3.6920166017e−21; evaluated loss differs by+2.2204460493e−16 due floating reduction.32halvings cannot cure cancellation.
- ABORTED SHA3c254b86990b1bc801e58ace3bd8da30a079c162d9ee7bb718e67cf9409bb034; diagnostic SHA891b2db319065f1b6865b0b539f0d29a20dd497d98248d289a8792f710dd08f5. Registry,pairs,nine models,manifest and diagnostic remain unchanged.
- This does **not** reject or validate the ranking hypothesis. Correct numerical acceptance without changing the1e−9 stationarity threshold or economic design; preregister and charge a distinct corrective epoch. Never silently repeat/overwrite.

中文：这是数值求解中止，不是负收益结果。模型在真实最优点附近被浮点损失比较误拒绝。未生成任何回测收益，不能宣称alpha成功或失败。保留全部24次试验及证据，修正数值终止判据后另行预登记。
