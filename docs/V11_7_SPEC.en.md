# V11.7–V11.8 Incremental Alpha Lab

Implementation contract: [Issue182](https://github.com/m-stephen/stephen-quant-agent/issues/182).
The goal is a historical research lead, never trading authorization or Alpha Court certification.

## Frozen plan

- Reuse the V11.6 five-source SHA-256 snapshot. Only2023/2024 development returns; no2025/2026 reads.
- Batch1:16 formulas,70% low-volatility rank +30% mechanism rank,8 fields/two signs,20-session rebalancing.
- If none qualifies, Batch2:16 conditional ranks within the bottom30% volatility population,60-session rebalancing.
- Matched field coverage, horizon, Top40/10-rank buffer, annual independent CNY3m accounts. Both a hashed no-signal Top40 and a low-vol Top40 control.
- Zero/standard41bps/double82bps cost models.32 candidates and32 controls produce192 reserved attempts, all registered before price reads. Unused reservations remain conservatively charged.
- Historical raw trial lower bound2866 becomes3058. Aborted attempts persist; successors must carry predecessor operations.

## Descriptive lead rule

At double costs: positive net returns in both years, pooled daily Sharpe>=0.7, each annual drawdown>=-25%; compounded annual-reset wealth must exceed matched low-vol by at least3 percentage points, with no single year lagging by more than5 points; positive compound increment over hashed control; accounting, timing and hashes pass.

Compounded annual-reset returns are a synthetic normalized chain, not continuous account P&L. Both years are contaminated historical development. Selecting on both is explicitly post-selection, not out-of-sample confirmation.

## Limits and reproducibility

Adjusted fractional shares, fixed fees and lagged ADV capacity remain approximations. Hashed Top40 is an internal size-matched control, not a market index or verified investable product. Buffer uses previous desired targets, not actual fills. The20-session stale write-down policy is unchanged. Minute/auction availability is not backdated.

DSR/PBO/placebo retain diagnostic/unidentifiable labels.60-session holdings require60-session purging; old Court thresholds are unchanged.

Copy`configs/incremental-alpha.example.json`to a gitignored`*.local.json`and set frozen-input, prior-ledger and output paths.

`python -m stephen_quant.workflows.v117_incremental_epoch --config configs/incremental-alpha.local.json`

Exact lead replay:`python -m stephen_quant.workflows.v117_incremental_epoch --replay <operation>`. Same runtime required; zero trial delta.

Delivery:unit/adversarial tests, bounded real-data batches, frozen lead, independent replay and daily reconciliation, bilingual results and PR. Negative findings remain visible; no threshold relaxation.
