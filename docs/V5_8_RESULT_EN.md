# V5.8 Test Result: Staged Candidate Screening Funnel

Decision: `READY_FOR_DATA_EVIDENCE`

| Stage | Frozen budget |
|---|---:|
| proposal | 256 |
| data quality | 192 |
| training screen | 96 |
| CPCV/PBO | 16 |
| execution and cost | 4 |

V5.7 currently supplies 185 typed proposals. This run executed only funnel planning and adversarial
synthetic tests; it did not fabricate coverage, RankIC, PBO or Sharpe evidence. Trial delta is zero.
Tests confirm that data-quality failures cost no Trial, while training, CPCV and execution entrants
carry cumulative counts of one, two and three. Budget deferral never erases spent trials.

V5.9 will choose search actions from failure reasons and remaining budget. The later one-command Agent
will inject real-data evidence.
