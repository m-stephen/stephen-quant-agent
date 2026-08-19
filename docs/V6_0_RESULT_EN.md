# V6.0 Test Result: Portfolio-aware Factor Objective

Decision: `READY_FOR_PORTFOLIO_EVIDENCE`

This run fabricated no marginal IR, dependence or capacity evidence, so it completed protocol
planning only and added zero Trials. Frozen settings are a CNY 3 million capacity floor, 0.70 maximum
pair correlation, five factors at most, and doubled-cost Sharpe no lower than -0.25.

Synthetic adversarial tests show that a higher standalone-Sharpe candidate correlated 0.95 with an
existing selection is rejected, while a 0.10-correlated candidate with lower standalone Sharpe but
positive marginal value is selected. Capacity below CNY 3 million, incomplete dependence matrices
and final-test evidence also fail closed.
