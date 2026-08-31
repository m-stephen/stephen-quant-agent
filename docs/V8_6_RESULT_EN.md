# V8.6 Multi-source warehouse and factor-search result

## Outcome

The engineering objective passed; the alpha objective did not. All 19 directories under the local
QD root have explicit dataset contracts. Seventeen non-bar datasets were fully migrated, while
daily and minute bars continue to use their dedicated canonical stores. Snapshot
`cc4d6ccb871887aa9d1561827e430e52fcd6c0e2fbc63ba617369580e5f07bcd` passed verification and a
zero-change replay reproduced the same hash.

The search produced candidates worth further research, but no deployable alpha. Alpha Court rejected
the strongest execution candidate because its DSR probability was below the frozen threshold.

## Warehouse evidence

The multi-source store contains 216 active partitions and 90,970,639 rows. The largest datasets are
technical factors (18,170,020 rows and 261 vendor fields), auction (14,012,027), fund flow
(13,967,447), fundamentals (10,738,172), chip distribution (9,429,666), and margin data (6,781,110).
Daily bars add 429 partitions and 18,196,199 rows.

V8.5 minute data currently contains the 2026-08-28 archive only: 1,752,852 rows across 1/5/15/30/60
minute intervals. Approximately 73 GB of compressed historical minute archives remains a separate
capacity migration and is not misreported as complete in this release.

No archive or partition hash failed. Duplicate index backup files produced 64,694 duplicate keys and
were deterministically deduplicated while preserving source hashes. One dated `.xlsx` wrapper had no
worksheet and was retained as a provenance document rather than fabricated into observations.

## Research evidence

The continuous pass generated 32 direction-complete candidates and shortlisted ten. The selected
inverse 20-session return signal had training mean RankIC 0.07961, purged-CPCV mean path RankIC
0.06694, 20/20 positive paths and PBO 0.05. This is a signal-gate pass only.

The event/baseline pass generated 18 candidates and shortlisted six. `auction_strength_20_5d`
achieved CPCV mean path RankIC 0.04331 with 20/20 positive paths, demonstrating that auction data
was genuinely used. The strongest overall candidate remained `price_reversal_60_5d`: training mean
RankIC 0.09306, CPCV mean path RankIC 0.08427 and PBO 0.15.

Its execution result was 20.09% net total return, 0.346 annualized net Sharpe, -38.30% maximum
drawdown and 113,338.60 total cost. Both placebo tests returned p=0.005, but DSR probability was only
0.35539 against the frozen 0.95 threshold. The final decision is `REJECT_ALPHA_COURT`.

The next research step should freeze these Trials and test low-correlation combinations of auction
strength and price reversal with training-only cost awareness and industry/size neutralization. The
DSR threshold must not be weakened.

