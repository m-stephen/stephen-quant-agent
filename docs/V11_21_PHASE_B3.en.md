# V11.21 B3: synthetic historical-feature-to-account integration

## Conclusion

The frozen two-source reader, per-historical-day response fits, training matrix, supervised predictor and continuous account are connected. This establishes engineering operation and selected independent calculation checks, **not an Alpha discovery**. No V11.21 market epoch has run. Historical debt remains3660, additional empirical Trials0; real backtest and Alpha Court are NOT_RUN.

## Implemented connections

- `qmt/flow_response_panel.py` derives sample volatility over20 log returns,20-session return and up-to60-session mean CNY turnover. Daily turnover converts thousands to CNY. Risk needs21 consecutive global-session prices; gaps are not compressed. ADV must reachCNY10m and the current name must be present/non-ST. Valid visible bars remain available for held-position marks even when ineligible for entry.
- A missing immediately preceding global-session ADV gives zero opening capacity. Current/future turnover cannot repair that value. Daily records unavailable by their own EOD are excluded before numerical inspection, without retrospective backfill. Source-adjusted prices, inferred open limits,5% past ADV, suspension and20-session writeoff conventions are retained.
- `flow_response_history.py` checks predeclared calendar/source manifest/experiment snapshot/provider-consumer contracts and unfitted state before source reads, then claims an exclusive output directory disjoint from the frozen source tree.
- Each historical signal's response bundle is fit from its own preceding60sessions, persisted exclusively and registered natively. After all native fits exist, each runtime file/time is checked before current response/risk intersection and ranks are computed. No annual model is back-applied to earlier history.
- The actual `history.json` byte digest is bound in the immutable provider result together with source and native fit evidence. The integrated supervised entry point accepts no arbitrary feature matrix; it derives mature prefix labels from that bound file and records history/prefix evidence in the predictor. Cache loading also checks actual bundle bytes against native records.
- `flow_response_accounts.py` connects seven predictor forms and same-support hash/lowvol controls to one netted four-phase account. Two stocks per cell,top3 retention buffer,2.5% each,phases0/5/10/15. Empty support leaves cash rather than renormalizing survivors. CNY3m,82/164bps,target_changes. Original lowvol/stable anchors remain pending and are not replaced by the new matched-support controls.

## Independent checks and adversarial tests

The fixture contains80synthetic stocks and300weekdays, not an exchange-holiday calendar. Only daily and fund-flow Parquet files exist. Its1provider/9consumers are10temporary synthetic Trials, not empirical reservations.

1. A separate NumPy calculation reconstructs60-day standardized flow, response slope/residual, risk and final cell ranks from raw synthetic data at historical indices61,140,255. Statistical calculation does not call production bridge/response-fit/feature functions. Ranking still shares the production function; this is not a wholly independent implementation of every algorithm.
2. Seven supervised forms share the same mature training-row digest and actual historical file. Each has at least30mature training dates; labels end before2023.
3. All9policies execute under both costs. Current eligibility is deliberately empty on the first2023signal viaST flags: the first sleeve stays cash, the next three reach75% desired exposure, and the first sleeve's next refresh reaches100%. Each order cost is recomputed as18buy/23sell bps times2/4. Daily NAV=cash+marked positions and return identities reconcile.
4. Tests cover changed matrix/bundle/model files, missing source relationships, wrong year/policy/manifest/calendar/snapshot, replay, overlapping/existing output, global gaps, unavailable poison values, adjustments, zero trading, ST/illiquidity and future-append prefix invariance.

Initial integration exposed mixed Decimal/float Parquet constants; the reader now explicitly projects numeric columns as DOUBLE while retaining original source-byte hashes. Bad conversions fail and timezones are not guessed. The fixture name`Test` triggered inherited ST filtering and was replaced by an ordinary synthetic name. Account tests use the real`end_nav`field. Initial failed JUnit artifacts are retained, not counted as passed; see VERIFICATION for final results.

## Limitations and next stage

- Noncompressed risk gaps,zero capacity without adjacent prior ADV,and no2021numeric warmup are conservative differences from the inherited bridge. Declare them before the market run; do not claim exact old-strategy replay.
- Source-adjusted fractional-share accounts, vendor historical availability and daily-bar trading proxies are not live first-seen evidence, broker lot/minimum-fee compliance or corporate-action cash certification.
- This stage tests synthetic2023accounts only, not real2023/2024profitability. Complete independent source/model/label/target/NAV audit, original anchor targets, canonical finite packet, full cost/control/failure Trial budget and exclusive epoch runner are pending.
- Complete those items, synthetic cross-year/failure-recovery tests and the full Issue184 preregistration before one real2022–2024epoch. No2025/2026reads; reused2023/2024is not fresh OOS. All economic/Court/independent-evidence thresholds stay unchanged.

Assessment: engineering results may be shared with these caveats; usable-Alpha evidence is unavailable. The validation workflow separates component tests, independent spot checks and investment conclusions.
