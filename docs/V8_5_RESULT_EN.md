# V8.5 final test report

## Decision

V8.5 verifies the primary archive-to-DuckDB/Parquet-to-daily-factor path and standardizes minute
bars. The engineering path is operational, but this factor run does not pass the final Alpha Court
and is not a deployable alpha.

## Real minute-bar migration

- Input: the 2026-08-28 minute archive; source remained read-only.
- One new archive, 27,735 members, 1,752,852 valid revisions, five partitions and zero quarantines.
- Row counts at 1/5/15/30/60 minutes: 1,331,280 / 266,256 / 88,752 / 44,376 / 22,188.
- Coverage: 5,547 instruments; snapshot `c6300c29...a0edb3`.
- Verification passed with matching partition hashes, zero duplicate current keys and zero PIT
  timing violations.
- Independent replay wrote zero revisions and returned the same snapshot.
- A timezone double-offset found by the first real run was corrected. The bad derived output was
  moved to a recoverable local quarantine; the source archive was not overwritten.

## Database-native automatic discovery

- Label window: 2022–2024; 2025/2026 labels remained sealed.
- Dynamic universe: top 300 per date, 1,738 unique instruments.
- 32 direction-complete candidates, 39 recorded Trials and seven CPCV entrants.
- Best mean CPCV path RankIC: 0.109194 with 20/20 positive paths.
- Research signal gate: `PASS_SIGNAL_GATE`.
- Selection PBO: 0.15, above the final Alpha Court limit of 0.05.
- Decision: `RESEARCH_CANDIDATE_PENDING_EXECUTION`. Execution, costs, placebo, DSR and forward
  gates were not opened, so the result is not deployable.

## Independent warehouse factor smoke test

- Factor: 20-session return over a 200-name universe selected from a prior liquidity window.
- 61,699 source rows; 242 evaluation sessions and 48,048 observations.
- Mean RankIC -0.015806; RankICIR -1.019630; hit rate 44.63%.
- Mean daily gross top-minus-bottom return -0.078881%.
- Verdict: `DATABASE_FACTOR_PATH_OPERATIONAL`; the tested factor itself is not alpha.

## Remaining boundary

Compressed fund-flow, auction, margin, chip, limit-event and temporary-industry sources do not yet
have canonical database adapters. Daily price research and minute bars are fixed, but a complete
multi-source migration must not be claimed. `--profile multi-source` fails closed instead of
silently using incomplete inputs.
