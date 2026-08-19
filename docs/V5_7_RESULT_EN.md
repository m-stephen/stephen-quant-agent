# V5.7 Test Result: Automatic Candidate Proposal Generator

Decision: `READY_FOR_STAGED_SCREENING`

| Metric | Result |
|---|---:|
| Symbolically generated candidates | 185 |
| Continuous-ranking candidates | 169 |
| Event-study candidates | 16 |
| External LLM candidates in this run | 0 |
| Label access | false |
| Inferential Trial delta | 0 |

The real run used the deterministic symbolic path. The LLM JSON adapter was validated with synthetic
adversarial tests, not presented as a real model call. It can submit only a constrained economic
hypothesis and DSL formula; extra code or control fields fail closed.

These 185 items are proposals, not 185 Alpha trials. V5.8 will control actual statistical spending
through a staged screening funnel.
