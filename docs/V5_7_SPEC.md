# V5.7 — Automatic Candidate Proposal Generation

## Objective

Move candidate creation from a fixed human catalog toward bounded automatic discovery, while
keeping statistical labels and executable code outside the proposal layer.

## Two proposal paths

1. The deterministic symbolic generator enumerates field levels, trends, event conditions and
   same-unit normalized imbalances from the semantic catalog.
2. An optional LLM provider may return a strict JSON list containing only formula, economic
   hypothesis, research form, horizon and direction. Extra fields fail closed.

Every proposal is compiled to a `FactorSchema`, routed by V5.5, type-checked by V5.6, assigned a
canonical proposal ID and deduplicated across origins. The LLM cannot execute Python, select a test
window, read labels, override gates or create trial-ledger entries.

## Acceptance

- deterministic bounded generation;
- both continuous-ranking and event-study coverage;
- typed economic hypothesis required for every proposal;
- cross-origin canonical deduplication;
- adversarial rejection of extra LLM control fields;
- label access false and inferential trial delta zero;
- bilingual machine-readable reports and full regression pass.
