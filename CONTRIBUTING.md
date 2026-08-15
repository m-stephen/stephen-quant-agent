# Contributing

Development follows an issue-first, pull-request workflow.

## Workflow

1. Start from an approved GitHub issue with explicit acceptance criteria.
2. Update local `main`, then create `feature/<issue-number>-<short-name>`.
3. Keep each branch focused on one issue. Do not mix unrelated changes.
4. Record every research attempt in the trial ledger; rejected attempts remain part of the record.
5. Add or update tests for timing, provenance, leakage, and reproducibility rules.
6. Run `pytest -q` before pushing.
7. Open a pull request into `main`, link the issue, and complete the integrity checklist.
8. Merge only after CI passes and review feedback is resolved.

## Branch and commit conventions

- Feature branch: `feature/<issue-number>-<short-name>`
- Fix branch: `fix/<issue-number>-<short-name>`
- Commit: concise imperative summary, such as `feat: add factor registry`

Direct feature development on `main` is not allowed. Emergency fixes still require a pull request.

## Definition of done

- Acceptance criteria in the linked issue are met.
- Tests cover expected behavior and failure modes.
- Point-in-time timing and snapshot lineage are preserved.
- Trial counts include all factor, parameter, model, and reward attempts.
- User-facing or research-facing behavior is documented.
- CI passes.

