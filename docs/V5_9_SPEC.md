# V5.9 — Budget-aware Search Controller

## Objective

Turn automatic discovery into a controlled sequential decision process rather than repeated blind
enumeration. The controller allocates a frozen research budget across semantic families.

## Inputs and actions

Each family state contains research-only attempts, training/CPCV conversions, mean research score,
expected Trial cost and repeated failure diagnosis. The deterministic controller chooses:

- `EXPLORE` for a promising untried semantic family;
- `MUTATE` for local refinement of a supported family;
- `REPAIR` when the same coverage, turnover or statistical failure repeats;
- `STOP` when the reserve is reached or all families are exhausted.

The default total budget is 256 with 32 Trials held in reserve. A selected batch can never cross that
reserve. Controller decisions add no inferential Trial; only V5.8 evidence stages do.

## Integrity

Validation and final-test metrics are invalid controller inputs. Failure repetition cannot be erased
by renaming a factor because family state is keyed by semantic identity upstream. Configurations with
unordered thresholds, invalid counts or duplicate families fail closed.
