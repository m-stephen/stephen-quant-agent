from __future__ import annotations

import json
from pathlib import Path

import pytest

from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_snapshot_manifest
from stephen_quant.research_agent import (
    AgentRunSpec,
    FormulaInput,
    ResearchAgentError,
    ResearchContext,
    ResearchSource,
    analyze_formula,
    evaluate_formula,
    parse_proposal,
    run_factor_research,
    write_research_report,
)


class FakeBackend:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def complete(
        self, prompt: str, *, model_id: str, model_version: str, seed: int
    ) -> str:
        self.calls.append(
            {
                "prompt": prompt,
                "model_id": model_id,
                "model_version": model_version,
                "seed": seed,
            }
        )
        return self.response


def _registry(tmp_path: Path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "prices.csv").write_text("date,close\n2025-01-01,1\n", encoding="utf-8")
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    snapshot_id = registry.register_snapshot(build_snapshot_manifest(data))
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            name="llm_factor_research",
            hypothesis="Generate falsifiable factor candidates.",
            dataset_snapshot_id=snapshot_id,
            code_version="test-sha",
            search_space='{"dsl":"1.0.0"}',
        )
    )
    return registry, snapshot_id, experiment_id


def _trial(experiment_id: str, seed: int = 42) -> TrialSpec:
    return TrialSpec(
        experiment_id=experiment_id,
        model_name="fake-llm@test-v1",
        factor_set="llm_candidate",
        hyperparams='{"prompt":"factor-proposal-json-dsl-1.0.0"}',
        seed=seed,
        train_start="2020-01-01",
        train_end="2022-12-31",
        validation_start="2023-01-01",
        validation_end="2023-12-31",
        test_start="2024-01-01",
        test_end="2024-12-31",
    )


def _context(snapshot_id: str, *, available_at: str = "2025-01-01T12:00:00+00:00"):
    return ResearchContext(
        snapshot_id=snapshot_id,
        knowledge_cutoff_at="2025-01-02T00:00:00+00:00",
        sources=(
            ResearchSource(
                source_id="paper_momentum",
                title="Momentum evidence",
                content="Medium-horizon relative strength may persist but requires falsification.",
                available_at=available_at,
            ),
        ),
    )


def _response(formula: str | None = None) -> str:
    return json.dumps(
        {
            "factor_id": "risk_adjusted_momentum_20",
            "version": "0.1.0",
            "name": "Risk-adjusted momentum",
            "hypothesis": "Positive medium-horizon returns scaled by volatility predict returns.",
            "formula": formula
            or "period_return(close, 20) / (volatility(close, 20) + 0.000001)",
            "required_fields": ["close"],
            "direction": 1,
            "lookback_periods": 20,
            "minimum_observations": 21,
            "prediction_horizon": "5d",
            "evidence_source_ids": ["paper_momentum"],
            "falsification_tests": ["signal_shuffle", "return_permutation", "cpcv"],
            "economic_rationale": "Trend persistence adjusted for unstable price variation.",
            "failure_modes": ["crowding", "trend reversal", "cost sensitivity"],
        },
        sort_keys=True,
    )


def _spec(experiment_id: str, seed: int = 42) -> AgentRunSpec:
    return AgentRunSpec(
        model_id="fake-llm",
        model_version="test-v1",
        seed=seed,
        trial=_trial(experiment_id, seed),
    )


def test_safe_dsl_rejects_code_and_evaluates_point_in_time() -> None:
    with pytest.raises(ResearchAgentError, match="unknown DSL function"):
        analyze_formula("__import__('os')")
    with pytest.raises(ResearchAgentError, match="direct whitelisted"):
        analyze_formula("close[-1]")
    with pytest.raises(ResearchAgentError, match="direct whitelisted"):
        analyze_formula("close.__class__")

    formula = "period_return(close, 2) / (volatility(close, 2) + 0.000001)"
    values = FormulaInput(
        values=(100.0, 110.0, 121.0),
        available_at=(
            "2025-01-01T00:00:00+00:00",
            "2025-01-02T00:00:00+00:00",
            "2025-01-03T00:00:00+00:00",
        ),
    )
    first = evaluate_formula(
        formula, {"close": values}, decision_at="2025-01-04T00:00:00+00:00"
    )
    second = evaluate_formula(
        formula, {"close": values}, decision_at="2025-01-04T00:00:00+00:00"
    )
    assert first == second
    assert first > 0

    future = FormulaInput(
        values=values.values,
        available_at=(*values.available_at[:-1], "2025-12-31T00:00:00+00:00"),
    )
    with pytest.raises(ResearchAgentError, match="future-unavailable"):
        evaluate_formula(
            formula, {"close": future}, decision_at="2025-01-04T00:00:00+00:00"
        )


def test_valid_proposal_is_counted_persisted_and_not_promoted(tmp_path: Path) -> None:
    registry, snapshot_id, experiment_id = _registry(tmp_path)
    backend = FakeBackend(_response())
    report = run_factor_research(
        registry, backend, _context(snapshot_id), _spec(experiment_id)
    )

    assert report.status == "proposed"
    assert report.candidate_id is not None
    assert registry.trial_count(experiment_id) == 1
    assert registry.candidate_count() == 1
    assert len(backend.calls) == 1
    assert report.response_sha256
    with registry.connect() as conn:
        trial_result = conn.execute(
            "SELECT result_json FROM trials WHERE trial_id = ?", (report.trial_id,)
        ).fetchone()[0]
        candidate_status = conn.execute(
            "SELECT status FROM factor_candidates WHERE candidate_id = ?",
            (report.candidate_id,),
        ).fetchone()[0]
    assert json.loads(trial_result)["status"] == "proposed"
    assert candidate_status == "proposed"


def test_duplicate_formula_creates_another_rejected_trial(tmp_path: Path) -> None:
    registry, snapshot_id, experiment_id = _registry(tmp_path)
    backend = FakeBackend(_response())
    first = run_factor_research(
        registry, backend, _context(snapshot_id), _spec(experiment_id, seed=1)
    )
    second = run_factor_research(
        registry, backend, _context(snapshot_id), _spec(experiment_id, seed=2)
    )

    assert first.status == "proposed"
    assert second.status == "rejected"
    assert second.duplicate_of_candidate_id == first.candidate_id
    assert registry.trial_count(experiment_id) == 2
    assert registry.candidate_count() == 1
    assert len(backend.calls) == 2


def test_future_context_is_rejected_after_trial_registration(tmp_path: Path) -> None:
    registry, snapshot_id, experiment_id = _registry(tmp_path)
    backend = FakeBackend(_response())
    context = _context(snapshot_id, available_at="2026-01-01T00:00:00+00:00")
    report = run_factor_research(registry, backend, context, _spec(experiment_id))

    assert report.status == "rejected"
    assert "future-unavailable" in (report.rejection_reason or "")
    assert registry.trial_count(experiment_id) == 1
    assert registry.candidate_count() == 0
    assert backend.calls == []


def test_malformed_unsafe_and_uncited_responses_remain_counted(tmp_path: Path) -> None:
    registry, snapshot_id, experiment_id = _registry(tmp_path)
    responses = (
        "not-json",
        _response("__import__('os')"),
        _response().replace("paper_momentum", "future_secret_source"),
    )
    for seed, response in enumerate(responses):
        report = run_factor_research(
            registry,
            FakeBackend(response),
            _context(snapshot_id),
            _spec(experiment_id, seed=seed),
        )
        assert report.status == "rejected"
        assert report.rejection_reason
    assert registry.trial_count(experiment_id) == 3
    assert registry.candidate_count() == 0


def test_formula_fingerprint_ignores_whitespace() -> None:
    _, _, first = parse_proposal(_response("period_return(close, 20)"))
    _, _, second = parse_proposal(_response(" period_return( close , 20 ) "))
    assert first == second


def test_strict_json_rejects_duplicate_keys_and_non_standard_numbers() -> None:
    duplicate = _response().replace(
        '"factor_id": "risk_adjusted_momentum_20",',
        '"factor_id": "one", "factor_id": "two",',
    )
    with pytest.raises(ResearchAgentError, match="duplicate JSON key"):
        parse_proposal(duplicate)

    non_standard = _response().replace('"direction": 1', '"direction": NaN')
    with pytest.raises(ResearchAgentError, match="non-standard JSON number"):
        parse_proposal(non_standard)


def test_agent_artifacts_are_deterministic_and_complete(tmp_path: Path) -> None:
    registry, snapshot_id, experiment_id = _registry(tmp_path)
    report = run_factor_research(
        registry, FakeBackend(_response()), _context(snapshot_id), _spec(experiment_id)
    )
    first = write_research_report(report, tmp_path / "first")
    second = write_research_report(report, tmp_path / "second")
    payload = json.loads(first.json_path.read_text(encoding="utf-8"))

    assert first.json_sha256 == second.json_sha256
    assert first.markdown_sha256 == second.markdown_sha256
    assert payload["snapshot_id"] == snapshot_id
    assert payload["model_id"] == "fake-llm"
    assert payload["prompt_sha256"]
    assert "not promoted" in first.markdown_path.read_text(encoding="utf-8")
