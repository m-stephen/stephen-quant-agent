# V2 M1: Hypothesis to Safe Expression

## Objective

Compile structured, falsifiable V2 hypotheses into deterministic, allowlisted and PIT-safe expression families. A model may select only frozen blueprints and bounded parameters; it cannot generate or execute arbitrary Python, SQL or shell.

## Compiler gates

- The hypothesis event and inputs must exactly match the blueprint and expression.
- Fields and functions must belong to the typed DSL allowlist.
- Addition and subtraction are dimension checked; every division needs an explicit positive floor.
- Lookback, AST complexity and field coverage must satisfy the frozen policy.
- Field availability cannot be later than the decision context.
- Every failure occurs before data evaluation and fails closed.

## Search boundary

`EXPLORE` creates a candidate only from the event's single allowlisted blueprint. `MUTATE` changes exactly one existing lookback parameter and retains parent lineage. The queue has a hard budget. Offline replay parses frozen raw responses and exposes no model or network callback.

## Acceptance

Three flow/price, large-order flow and margin-demand hypotheses must compile deterministically. Illegal operators, excessive windows, unsafe division, dimension conflicts, inadequate coverage and PIT violations must be rejected before empirical evaluation.
