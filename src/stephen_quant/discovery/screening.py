from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime

from stephen_quant.baseline import BaselineObservation
from stephen_quant.evaluation import EvaluationObservation
from stephen_quant.evaluation.metrics import peer_rank_correlation, summarize_horizon
from stephen_quant.integrity.models import TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry

from .campaign import SearchCampaign
from .generator import GeneratedCandidate


@dataclass(frozen=True)
class ScreeningWindow:
    research_start: str
    research_end: str
    validation_start: str
    validation_end: str
    test_start: str
    test_end: str

    def validate(self) -> None:
        if not (
            self.research_start <= self.research_end
            < self.validation_start <= self.validation_end
            < self.test_start <= self.test_end
        ):
            raise ValueError("screening windows must be strictly ordered and sealed")


@dataclass(frozen=True)
class ScreeningConfig:
    minimum_coverage: float = 0.90
    minimum_mean_rank_ic: float = 0.0
    maximum_peer_rank_correlation: float = 0.80
    minimum_cross_section: int = 3

    def validate(self) -> None:
        if not 0 < self.minimum_coverage <= 1:
            raise ValueError("minimum_coverage must be in (0, 1]")
        if not 0 <= self.maximum_peer_rank_correlation <= 1:
            raise ValueError("maximum_peer_rank_correlation must be in [0, 1]")
        if self.minimum_cross_section < 3:
            raise ValueError("minimum_cross_section must be at least three")


@dataclass(frozen=True)
class CandidateScreenScore:
    schema_id: str
    fingerprint: str
    proposal_id: str
    trial_id: str
    trial_number: int
    coverage: float
    dates: int
    observations: int
    mean_rank_ic: float | None
    maximum_selected_correlation: float | None
    decision: str
    reason: str


@dataclass(frozen=True)
class ScreeningReport:
    campaign_id: str
    expected_dates: int
    scores: tuple[CandidateScreenScore, ...]
    shortlisted_fingerprints: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)


def _timestamp_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError as exc:
        raise ValueError(f"invalid observation timestamp: {value}") from exc


def _evaluation(
    rows: tuple[BaselineObservation, ...], horizon: str
) -> tuple[EvaluationObservation, ...]:
    return tuple(
        EvaluationObservation(
            instrument=row.instrument,
            timestamp=row.execution_at,
            factor_value=row.signal,
            factor_available_at=row.signal_available_at,
            label_start_at=row.execution_at,
            label_end_at=row.return_end_at,
            forward_return=row.forward_return,
            horizon=horizon,
            subperiod="research",
            regime="unspecified",
        )
        for row in rows
    )


def _peer_values(
    rows: tuple[EvaluationObservation, ...], direction: int
) -> dict[tuple[str, str], float]:
    return {
        (row.timestamp, row.instrument): direction * row.factor_value for row in rows
    }


def run_training_screen(
    registry: ExperimentRegistry,
    campaign: SearchCampaign,
    candidates: tuple[GeneratedCandidate, ...],
    observations: dict[str, tuple[BaselineObservation, ...]],
    *,
    window: ScreeningWindow,
    config: ScreeningConfig,
    seed: int = 42,
) -> ScreeningReport:
    """Count, measure and shortlist generated factors using research-only observations."""

    window.validate()
    config.validate()
    unique = [item for item in candidates if item.unique]
    if not unique:
        raise ValueError("training screen requires at least one unique candidate")
    if set(observations) != {item.schema.fingerprint for item in unique}:
        raise ValueError("screen observations must exactly match unique candidate fingerprints")

    dates: set[str] = set()
    for rows in observations.values():
        for row in rows:
            execution_date = _timestamp_date(row.execution_at)
            return_end_date = _timestamp_date(row.return_end_at)
            if execution_date < window.research_start or return_end_date > window.research_end:
                raise ValueError("screen observations touch a sealed or out-of-research window")
            dates.add(execution_date)
    if len(dates) < 2:
        raise ValueError("training screen requires at least two research dates")

    registered: dict[str, tuple[str, int]] = {}
    for item in unique:
        schema = item.schema
        registered[schema.fingerprint] = registry.create_trial(
            TrialSpec(
                experiment_id=campaign.spec.experiment_id,
                model_name="v1.8.16_training_screen",
                factor_set=schema.schema_id,
                hyperparams=schema.to_json(),
                seed=seed,
                train_start=window.research_start,
                train_end=window.research_end,
                validation_start=window.validation_start,
                validation_end=window.validation_end,
                test_start=window.test_start,
                test_end=window.test_end,
            )
        )

    raw: list[tuple[GeneratedCandidate, tuple[EvaluationObservation, ...], float, float | None]] = []
    for item in unique:
        rows = observations[item.schema.fingerprint]
        evaluation = _evaluation(rows, item.schema.horizon)
        candidate_dates = {row.timestamp for row in evaluation}
        coverage = len(candidate_dates) / len(dates)
        rank_ic: float | None = None
        if coverage >= config.minimum_coverage:
            rank_ic = summarize_horizon(
                item.schema.horizon,
                evaluation,
                direction=item.schema.direction,
                min_cross_section=config.minimum_cross_section,
            ).mean_rank_ic
        raw.append((item, evaluation, coverage, rank_ic))

    raw.sort(
        key=lambda row: (
            -(row[3] if row[3] is not None else float("-inf")),
            row[0].schema.fingerprint,
        )
    )
    selected: list[tuple[GeneratedCandidate, tuple[EvaluationObservation, ...]]] = []
    scores: list[CandidateScreenScore] = []
    for item, evaluation, coverage, rank_ic in raw:
        correlations: list[float] = []
        for peer_item, peer_rows in selected:
            correlation, _ = peer_rank_correlation(
                evaluation,
                _peer_values(peer_rows, peer_item.schema.direction),
                direction=item.schema.direction,
                min_cross_section=config.minimum_cross_section,
            )
            correlations.append(abs(correlation))
        maximum_correlation = max(correlations) if correlations else None
        if coverage < config.minimum_coverage:
            decision, reason = "screened_out", "insufficient coverage"
        elif rank_ic is None or rank_ic < config.minimum_mean_rank_ic:
            decision, reason = "screened_out", "training RankIC below frozen threshold"
        elif (
            maximum_correlation is not None
            and maximum_correlation > config.maximum_peer_rank_correlation
        ):
            decision, reason = "screened_out", "redundant with a stronger selected candidate"
        elif len(selected) >= campaign.spec.budget.cpcv:
            decision, reason = "screened_out", "frozen CPCV shortlist budget exhausted"
        else:
            decision, reason = "shortlisted", "passed frozen training-only screen"
            selected.append((item, evaluation))
        trial_id, trial_number = registered[item.schema.fingerprint]
        score = CandidateScreenScore(
            schema_id=item.schema.schema_id,
            fingerprint=item.schema.fingerprint,
            proposal_id=item.proposal_id,
            trial_id=trial_id,
            trial_number=trial_number,
            coverage=coverage,
            dates=len({row.timestamp for row in evaluation}),
            observations=len(evaluation),
            mean_rank_ic=rank_ic,
            maximum_selected_correlation=maximum_correlation,
            decision=decision,
            reason=reason,
        )
        registry.record_trial_result(trial_id, json.dumps(asdict(score), sort_keys=True))
        registry.transition_campaign_proposal(
            item.proposal_id,
            decision=decision,
            reason=reason,
            trial_id=trial_id,
        )
        scores.append(score)

    scores.sort(key=lambda item: item.trial_number)
    return ScreeningReport(
        campaign_id=campaign.campaign_id,
        expected_dates=len(dates),
        scores=tuple(scores),
        shortlisted_fingerprints=tuple(item.schema.fingerprint for item, _ in selected),
    )
