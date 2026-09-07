# V11.10 Training-only residual mechanisms with a replacement hurdle

## Research question

Keep the existing chip staggered observation frozen. Test three fixed interaction mechanisms for predictive information beyond simple risk exposures. All2022–2024 history has been encountered;2023/2024 are reused development, not pristine OOS. No2025/2026 reads.

## Methods and full budget

- Three centered as-of rank interactions: inflow×20-session reversal; chip-cost distribution width×20-session reversal; auction return×late-session reversal. Training determines a single residual slope, without a separate sign sweep.
- Common complete coverage across volatility,20-session return,ADV,inflow,chip,auction,late fields; no zero imputation or new data sources.
- Train2023 models on2022,2024 models on2022–2023. Slice the prefix before building labels from next open to the open20sessions later; all labels must mature inside the cutoff, with five additional embargo sessions. Fixed five-session sample stride.
- Separate training OLS residualization of signal and return on intercept and volatility/momentum/ADV ranks. Fixed0.01 residual-slope ridge and1e-10 numerical diagonal stabilization; no parameter search.
- Missing entry prices are excluded and counted. Missing maturity prices receive a conservative-100% target, not silent exclusion or proof of actual delisting losses.
- Five volatility×four liquidity rank cells, up to two names each,2.5% per name; unavailable slots stay cash. Retain prior desired names still in their cell and fill via stable hash. Discretionary replacements require predicted return difference>1.22% (82bps+40bps margin). Coverage/cell migration and netted drift rebalancing can still incur costs.
- One fixed four-cohort0/5/10/15 netted continuous account; no phase selection or annual capital reset. Common-coverage low-vol Top40/buffer10 and cell-matched stable-hash controls.
- Six yearly fits plus five policies×three costs41/82/102bps=21 reserved attempts before data reads. Raw historical lower bound3268→3289; failed/aborted/unused reservations never refunded.

## Frozen screen and limitations

A historical lead must pass at BOTH82and102bps: positive in both years,Sharpe>=0.7,full-path drawdown>=-25%,total-return difference>=3pp against each control,annual difference vs low-vol>=-5pp,and verified accounting. This is not Alpha Court or selection-adjusted significance.

Existing CPCV diagnoses selection on adaptive walk-forward account returns, not fully nested fold-wise model refits. DSR remains current-family dispersion extrapolated to raw historical trial debt, not calibrated full-history confidence. Reused history, incomplete industry/size/market-beta controls, up-to-seven-day minute alignment,vendor-time provenance,and adjusted fractional shares/linear fees/ADV capacity remain explicit limitations.

## Verification and execution

Planted residual signal,pure-style null,fixed-noise null,future mutation,label maturity,missing exits,common coverage,cell limits,cost hurdle,pre-read reservations and no-reentry tests precede real execution. Independently reconcile every account and retain bilingual JSON/Markdown evidence. DSR0.95,PBO0.05,placebo0.05 and path thresholds remain unchanged.

Run `python -m stephen_quant.workflows.v1110_residual_epoch --config configs/residual-mechanisms.local.json`. Local paths are gitignored; the example uses relative paths. Never restart existing operations; inspect RESULT/ABORTED and ledgers first.
