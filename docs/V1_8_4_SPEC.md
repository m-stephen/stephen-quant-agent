# V1.8.4 - QMT Corporate Actions and Point-in-Time Adjustment

V1.8.4 removes the unadjusted-price blocker from the direct DAT workflow while remaining on the
long-lived `data-test` branch.

## Data contract

- `DividData` is opened read-only through the optional MIT-licensed `rleveldb` package.
- Every LevelDB table, manifest, and write-ahead log is hashed before and after reading.
- A concurrent database change fails the export instead of producing a mixed snapshot.
- Keys must match `MARKET|SYMBOL|4000|timestamp_ms`.
- Values must satisfy the locked 96-byte schema and contain finite, plausible fields.
- Empty/sentinel keys are ignored; duplicate internal keys keep only the greatest sequence number.
- The manifest records parser/schema versions, file hashes, snapshot hash, record count, and date
  coverage without recording the terminal path.

The observed field layout was checked against the vendor's
[`get_divid_factors`](https://dict.thinktrader.net/nativeApi/xtdata.html) fields and adjustment
[example](https://dict.thinktrader.net/nativeApi/code_examples.html?id=x3GDHP), and independently
against the community [`qmt-parser`](https://github.com/sunnysab/qmt-parser/blob/main/src/dividend.rs)
implementation. No code is copied from the GPL project.

## Adjustment contract

Direct DAT export supports:

- `none`: raw prices;
- `back_ratio`: multiply OHLC by cumulative QMT `dr`, adding each action on its ex-dividend date.

`back_ratio` is the research default because a decision made before an action uses only factors
already effective at that time. Direct `front_ratio` is intentionally rejected. Price fields are
adjusted; raw volume and amount are preserved.

## Validation verdict

A successful adjusted run proves that local DAT bars, corporate actions, immutable source hashes,
Trial-first evaluation, point-in-time signals, and the cost model execute together. It does not by
itself prove Alpha.

`research_claim_eligible` remains false while the universe is supplied from a current constituent
snapshot. The local `sectorChange.txt` format can represent dated additions/removals, but an
operator must verify that its coverage reaches the backtest end date. A stale history must fail the
point-in-time-universe gate rather than be forward-filled.

## Acceptance target

- Locked key/value fixtures decode every established field.
- Timestamp disagreement, short values, invalid factors, and concurrent source changes fail closed.
- Prices before an ex-date are unchanged; prices on and after it use cumulative `dr`.
- A `back_ratio` export hash-links both DAT and corporate-action inputs.
- The one-command validation accepts `--adjustment back_ratio`.
- Full tests and lint pass, followed by a local 30-instrument engineering run.
