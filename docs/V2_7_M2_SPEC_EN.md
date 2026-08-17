# V2.7 M2 — Fold-Local Price Risk Controls

## Authorization

M1 permits only market beta, realized volatility, ADV liquidity, short-term reversal, and medium-term momentum. PIT stock-industry membership and revision-safe size remain unavailable.

## Design

- Every feature at decision time uses history strictly before that timestamp.
- Every median, robust scale, winsor bound, and residualization coefficient is fit on the training fold only.
- Held-out transforms reuse an immutable, SHA-256-addressed fit state.
- Schema changes, non-finite values, duplicate observations, training rows in held-out transforms, and state tampering fail closed.
- The partial model is never Alpha Court eligible.

No real candidate returns, IC, backtest, placebo, raw directory, remote model, or 2025/2026 data are used by the engineering audit.

