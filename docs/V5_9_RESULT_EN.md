# V5.9 Test Result: Budget-aware Search Controller

Status: `READY_FOR_PORTFOLIO_AWARE_SEARCH`

The baseline plan injects no fabricated historical performance; all seven mechanism families start
untried. The controller selects:

- Action: `EXPLORE`
- Family: `price`
- Batch: 16
- Maximum incremental Trials: 20
- Reserved Trials: 32/256
- Controller Trial delta: 0

Price is selected first because its expected evaluation cost is lowest, not because price factors are
already effective. Adversarial tests reject validation/final-test feedback, trigger REPAIR after
repeated failures, and STOP at the reserve or when all mechanisms are exhausted.
