# V5.6 Test Result: Typed Factor DSL

Decision: `READY_FOR_AUTOMATIC_PROPOSALS`

| Metric | Result |
|---|---:|
| Unique semantic candidates | 164 |
| Accepted by type checking | 164 |
| Existing candidates failed closed | 0 |
| Inferential Trial delta | 0 |

Accepted output units comprise 9 CNY, 119 ratio, 35 return and 1 return-per-CNY expression. All
existing candidates satisfy the typed contract. This does not make the gate permissive: adversarial
tests reject incompatible arithmetic, automatic lookbacks above 252 sessions and stale route
bindings before backtesting.

This run did not test Alpha. It establishes engineering eligibility for the V5.7 automatic proposal
layer.
