# V1.8.17 Normalized Multi-source Factors and Family-aware Search

Tracking issue: [#27](https://github.com/m-stephen/stephen-quant-agent/issues/27)

## Objective

V1.8.17 improves candidate information quality without weakening any V1.8.16 gate. It combines price, traded value, fund flow, margin financing, and opening-auction data into comparable intensity, anomaly, and divergence hypotheses, while preventing window variants from exhausting the search budget.

## Frozen design

- Research uses data through 2024-12-31 only. The 2025 validation and 2026 final-test windows remain sealed.
- Every field must be available before execution. A 09:26 same-day auction value is allowed; close, flow, and margin values must be known from the prior session.
- Candidates receive same-time cross-sectional winsorization, market centering, and standardization. Any transform fitted across samples in CPCV must fit training IDs only.
- Families cover price baselines, flow/ADV, large and extra-large order imbalance, flow-price divergence, margin/ADV, margin balance change, auction price-volume interaction, and auction amount/ADV.
- At most one candidate per family may enter CPCV, in addition to the peer-correlation redundancy gate.
- The frozen training objective combines RankIC, positive-year stability, and a rank-turnover cost proxy.
- Official DSR continues to use the raw global Trial count. An effective-independent-trials diagnostic cannot replace it.

## Acceptance targets

1. Multi-source DSL factors build a strict point-in-time observation panel.
2. Future-available or stale inputs make an observation ineligible; they are never backfilled.
3. CPCV-fitted winsorization and standardization learn parameters from training IDs only.
4. Reports expose family, yearly stability, rank turnover, and the multi-objective score.
5. One command runs next-open, 5-day, and 20-day horizons with bilingual reports, frozen configs, snapshots, and Trial lineage.
6. Ruff, the complete test suite, and GitHub Actions pass.

## Non-goals and limitation

- No PPO/GNN, live trading, or sealed-window access.
- The neutralization interface accepts point-in-time stock-industry mappings. Existing industry-index files do not establish historical stock membership, so the real run uses market centering rather than inventing a mapping.
- AlphaPai news and research may support future hypothesis generation and explanations, but cannot replace timestamped and coverage-audited numerical inputs.

## One-command run

Machine paths belong only in the Git-ignored `configs/qd-paths.local.json`:

```powershell
stephen-quant qd-auto-discover-suite `
  --paths-config configs/qd-paths.local.json `
  --suite-manifest configs/v1.8.17-suite.json `
  --ingested-at 2026-08-17T00:00:00+08:00 `
  --output reports/qd-v1.8.17-suite
```

The existing CPCV, cost, placebo, PBO, DSR, and walk-forward gates decide whether any candidate is Alpha. A trustworthy rejection still satisfies the engineering acceptance criteria.
