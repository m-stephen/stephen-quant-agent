# V1.7 — Integrity-first LLM Factor Research Agent

V1.7 allows an LLM to propose hypotheses without allowing it to execute arbitrary code, hide failed
attempts, use future knowledge, or promote its own result.

## Agent boundary

1. The experiment Trial is registered before any model request.
2. One call produces at most one proposal; repair or retry is another Trial.
3. The model receives deterministic JSON containing a snapshot, cutoff, untrusted sources, schema,
   and DSL instructions.
4. The response must be exactly one JSON object with the exact proposal fields.
5. Model and prompt versions, seed, cutoff, sources, prompt hash, and response hash are recorded.

The backend is provider-neutral. V1.7 defines a protocol but does not embed credentials, network
calls, provider SDKs, or a preferred commercial model.

## Point-in-time knowledge contract

- Every research source has an `available_at` timestamp.
- A source available after the declared knowledge cutoff rejects the entire attempt before the model
  is called.
- The context snapshot must equal the experiment's frozen dataset snapshot.
- Evidence citations may reference only source IDs supplied to that model call.

## Safe factor DSL

The DSL permits numeric constants, `+`, `-`, `*`, `/`, unary signs, whitelisted market fields, and:

- `period_return(field, lookback)`
- `mean(field, lookback)`
- `volatility(field, lookback)`
- `sma_ratio(field, short, long)`
- `relative_strength(field, benchmark_field, lookback)`
- `max_drawdown(field, lookback)`
- `amihud(close_field, amount_field, lookback)`

Imports, attributes, indexing, comprehensions, lambdas, keyword arguments, arbitrary names, and
unknown calls are rejected by AST validation. Evaluation independently checks missing values,
history, point-in-time availability, division by zero, and finite output.

## Candidate lifecycle

- A canonical AST, direction, horizon, and fields form the immutable candidate fingerprint.
- Duplicate fingerprints create rejected Trials but not duplicate candidate rows.
- Accepted candidates are persisted only with status `proposed`.
- The agent cannot register the candidate as validated or approved.
- Promotion requires V1.2 metrics, V1.3 CPCV, V1.4 falsification/DSR/PBO, and V1.5/V1.6 cost-aware
  comparison under separate registered Trials.

## Deliberate limitations

- LLM output quality is not established by schema compliance.
- Prompt injection risk is reduced by treating sources as untrusted data and by strict output/DSL
  gates, but model calls should still run without secrets or write credentials.
- V1.7 proposes scalar cross-sectional factors; portfolio construction remains downstream.
- Fingerprints normalize syntax and whitespace, not every algebraically equivalent expression.
