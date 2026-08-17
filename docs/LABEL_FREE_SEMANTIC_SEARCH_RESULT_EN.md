# Label-Free Semantic Search Controller — Result

## Decision

`EFFICIENCY_GAIN`

The frozen synthetic benchmark contains nine proposals across train, validation and sealed-test
partitions and runs under seeds 7, 19 and 41.

## Evidence

| Metric | Bounded baseline | Semantic controller |
|---|---:|---:|
| Worst-seed duplicate recall | 0.20 | 1.00 |
| Semantic decision correctness | — | 9 / 9 per seed |
| Expensive evaluations avoided | baseline-dependent | 6 / 9 per seed |
| Correct mechanism coverage | — | 3 / 9 proposals |

All three seeds produced the same aggregate metrics. The controller correctly rejected semantic
variants, exact descendants, a tombstoned family and a PIT-blocked industry plan while retaining
three distinct mechanisms.

## Integrity audit

- new inferential trials: 0;
- real market matrix reads: 0;
- restricted-window access: 0;
- remote model requests: 0;
- replay: deterministic and content-linked;
- output: JSON plus English and Chinese Markdown.

This result validates search-control engineering only. It is not evidence of a profitable factor
and does not authorize empirical research before the missing PIT sources and Gate 5 are resolved.
