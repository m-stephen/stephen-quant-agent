# V11.10.1 Native fit lineage and synthetic execution calibration

## Outcome

Engineering repair only: no new market backtest and no new or certified Alpha.
V11.10's actual training was year-local, but its scalar ledger columns always said
2022 and did not describe the 2024 fit on 2022–2023. Historical evidence and its
clarification appendix remain unchanged. New trials can use native staged contracts.
Raw historical market Trial lower bound remains3289; this patch adds zero market
attempts. No2025/2026 data were read or unsealed.

## Implementation

1. Optional `TrialSpec.fit_stages` is registered atomically with each Trial.
   `None` means legacy/unverified; an empty tuple explicitly declares an unfitted control.
2. Append-only SQLite contracts and model bindings store actual accepted training
   signal sessions, fit cutoff, maximum label maturity, prediction interval,
   raw model-artifact SHA-256, canonical model digest, and experiment-derived
   snapshot/code identity. Multi-year models have distinct bindings.
3. Reject out-of-bounds or immature fits, unordered/duplicate sessions, wrong years,
   overlapping stages, changed identity contents and missing stages at completion.
   Identical binding retries do not add Trials.
4. `guarded_targets` verifies the complete lineage, actual runtime model and
   fit cutoff < signal date < trade date before feature/target calculation.
5. `fit_year` records only signal sessions contributing accepted training samples.
6. Fixed synthetic controls traverse the real stateful account with CNY3m,
   nominal82bps round-trip costs, four netted cohorts and blocked-buy scenarios;
   cash/position/return reconciliations pass.

## Verification

Final counts are in `V11_10_1_VERIFICATION.json`; Ruff covers src and tests.

| Test | Fixed acceptance |
|---|---|
| Planted signal | Replacements clear the original122bps hurdle; positive costed return and >3pp increment over matched hash |
| Null signal | No discretionary replacements; identical complete control account; flat prices lose transaction fees |
| All buys blocked | CNY3m final cash, zero fees, blocked orders, no fabricated position profits |
| Native lineage | Two-year scopes, hashes, chronology, append-only identity, retries and completion gate |
| Legacy migration | New tables on a temporary synthetic old database preserve all old Trial fields/results |
| Future mutation | Existing model/earlier targets unchanged; no-sample dates excluded from training coverage |

```text
python -m pytest -q tests/test_fit_lineage.py tests/test_residual_execution.py tests/test_residual_mechanisms.py tests/test_residual_epoch.py
python -m pytest -q --tb=short
python -m ruff check src tests
```

## Limits and next step

Synthetic dates are artificial ordered sessions, including non-market days. A fixed
seed and intentionally strong signal demonstrate this execution path, not calibrated
false-positive rates or statistical power for weak real signals. Adjusted fractional
shares, linear fees and proxy capacity remain non-brokerage execution assumptions.

The closed V11.10 runner/results are preserved, not replayed or retroactively
certified. The new entry point is end-to-end tested for subsequent experiments;
legacy CLI paths do not automatically gain native certification. The next market
epoch must preregister and directly use the new entry, carrying3289 rather than
copying the old3268 debt. Bindings establish recorded input/model/timing consistency,
not vendor truthfulness.

Resume bounded mechanism research with a fixed low-risk allocation control and
genuinely different temporal persistence/change features from existing inputs.
Do not repeat the failed three static interactions or lower the cost hurdle.
Complete multiplicity, placebos, fold-local refitting where needed and independent
evidence remain necessary before any usable-Alpha claim.
