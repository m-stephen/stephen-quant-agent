# V11.2 final test result

Implementation issue: [#175](https://github.com/m-stephen/stephen-quant-agent/issues/175)  
Frozen implementation commit: `1c16f476a925e45ab48e60a7be346ad9ff676c3b`  
Spec version: `11.2.0`  
Spec hash: `09d5e702580c534c425581a24e06592df908d5fb1cb6610d85e4cef40517dd68`

## Engineering acceptance

- Full suite: `671 passed, 1 skipped`;
- Ruff: passed;
- `git diff --check`: passed;
- V11.2 focused suite: `21 passed`;
- Frozen protocol semantic hash: `71ba4f198f2f3dcbc4877d684f5a5fd8023d806a469e2d2a482ead4174a77106`;
- Frozen protocol byte hash: `bd05436613e94f4333383f66f68c1c6fa22f0703041fabbe23d5b3282deb546c`;
- Real-run content hash: `405a2f688c5e63bd43b98b2cdceec74c4f1fd742c7333abc8c4220545409bc33`;
- Real-run envelope hash: `84160012ea26cfe837857f2cf542f9e04a17ee8a7a437ecc493e9c97ea773d7c`.

Adversarial coverage includes backward state transitions, protocol/evidence tampering, pre-genesis and backfilled records, late arrivals, revision chains, duplicates, overwrites, unequal source watermarks, two-level calendars, day 25/126/252 boundaries, label-interface rejection, orthogonal-domain hard gates, interrupted atomic writes, duplicate operations and deterministic replay.

## Real-run outcome

| Item | Result |
|---|---|
| Candidate Nursery | `CANDIDATE_NURSERY_READY` |
| Trusted observation clock | `ESTABLISHED` |
| Family actionable dates | `0` |
| Forward stage | `ACTIONABLE_DATES_INSUFFICIENT` |
| Orthogonal domain | `ORTHOGONAL_DATA_NOT_READY` |
| Raw global Trials | `770` |
| New inferential Trials | `0` |
| Unauthorized sealed-label reads | `0` |

The Nursery migrates exactly the two existing forward candidates, one specification-dependent V11 clue, and all fifteen V11.1 rejection records. It creates no sign reversal, adjacent mutation or third protocol.

The trusted clock starts with this controlled run. Older local files remain useful for coverage and QA but cannot be retroactively presented as decision-time first-seen evidence. No complete daily/minute/chip family date was first observed after the freeze boundary and before the frozen T+1 cutoff, so zero actionable dates is the correct result.

## Orthogonal-data audit

1. Announcement/expectation surprise has publication and revision metadata but lacks point-in-time consensus expectations and actual values; `actual_value` and `expected_value` fail the hard gate.
2. Share-supply/corporate-action sources do not yet provide the complete stable-ID, deduplication, PIT/revision and deterministic full-replay contract.
3. Historical Shenwan L2 membership is replayable and broad, but remains `PIT_LITE` with `formal_research_eligible=false`; V11.2 does not misrepresent it as formal PIT.

## Research conclusion

V11.2 delivers a trusted research runtime, not an Alpha discovery. It finds no new Alpha and authorizes no trading. Valid progress now requires genuinely new observations after the trusted-clock genesis, or a separately preregistered study after one orthogonal domain satisfies every hard gate. Old files cannot be backfilled and open-ended historical search remains frozen.
