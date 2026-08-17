from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from itertools import pairwise

from stephen_quant.baseline import BaselineObservation
from stephen_quant.evaluation import EvaluationObservation, average_ranks
from stephen_quant.evaluation.metrics import (
    peer_rank_correlation,
    spearman_correlation,
    summarize_horizon,
)
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
    family_budgets: tuple[tuple[str, int], ...] = ()
    minimum_positive_year_fraction: float = 0.0
    maximum_rank_turnover: float = 1.0
    stability_weight: float = 0.0
    turnover_penalty: float = 0.0

    def validate(self) -> None:
        if not 0 < self.minimum_coverage <= 1:
            raise ValueError("minimum_coverage must be in (0, 1]")
        if not 0 <= self.maximum_peer_rank_correlation <= 1:
            raise ValueError("maximum_peer_rank_correlation must be in [0, 1]")
        if self.minimum_cross_section < 3:
            raise ValueError("minimum_cross_section must be at least three")
        if len({family for family, _ in self.family_budgets}) != len(self.family_budgets):
            raise ValueError("family_budgets must contain unique families")
        if any(not family or budget < 1 for family, budget in self.family_budgets):
            raise ValueError("family budgets require names and positive limits")
        if not 0 <= self.minimum_positive_year_fraction <= 1:
            raise ValueError("minimum_positive_year_fraction must be in [0, 1]")
        if not 0 <= self.maximum_rank_turnover <= 1:
            raise ValueError("maximum_rank_turnover must be in [0, 1]")
        if self.stability_weight < 0 or self.turnover_penalty < 0:
            raise ValueError("screening objective weights cannot be negative")


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
    family: str = "unspecified"
    positive_year_fraction: float | None = None
    rank_turnover: float | None = None
    objective_score: float | None = None


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
        if row.eligible
    )


def _peer_values(
    rows: tuple[EvaluationObservation, ...], direction: int
) -> dict[tuple[str, str], float]:
    return {
        (row.timestamp, row.instrument): direction * row.factor_value for row in rows
    }


def _family(schema_id: str) -> str:
    return re.sub(r"_\d+_(?:next_open|1d|5d|20d)$", "", schema_id)


def _stability_and_turnover(
    rows: tuple[EvaluationObservation, ...], direction: int, minimum_cross_section: int
) -> tuple[float | None, float | None]:
    grouped: dict[str, list[EvaluationObservation]] = {}
    for row in rows:
        grouped.setdefault(row.timestamp, []).append(row)
    daily_ic: list[tuple[str, float]] = []
    ranks: dict[str, dict[str, float]] = {}
    for timestamp, cross_section in sorted(grouped.items()):
        ordered = sorted(cross_section, key=lambda item: item.instrument)
        if len(ordered) < minimum_cross_section:
            continue
        daily_ic.append(
            (
                timestamp[:4],
                spearman_correlation(
                    [direction * row.factor_value for row in ordered],
                    [row.forward_return for row in ordered],
                ),
            )
        )
        ranked = average_ranks([direction * row.factor_value for row in ordered])
        denominator = max(len(ordered) - 1, 1)
        ranks[timestamp] = {
            row.instrument: (rank - 1) / denominator
            for row, rank in zip(ordered, ranked, strict=True)
        }
    if not daily_ic:
        return None, None
    by_year: dict[str, list[float]] = {}
    for year, value in daily_ic:
        by_year.setdefault(year, []).append(value)
    positive_year_fraction = sum(
        sum(values) / len(values) > 0 for values in by_year.values()
    ) / len(by_year)
    changes: list[float] = []
    ordered_dates = sorted(ranks)
    for previous, current in pairwise(ordered_dates):
        common = set(ranks[previous]) & set(ranks[current])
        if common:
            changes.extend(abs(ranks[current][key] - ranks[previous][key]) for key in common)
    return positive_year_fraction, (sum(changes) / len(changes) if changes else 0.0)


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

    raw: list[
        tuple[
            GeneratedCandidate,
            tuple[EvaluationObservation, ...],
            float,
            float | None,
            float | None,
            float | None,
            float | None,
        ]
    ] = []
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
        stability, turnover = _stability_and_turnover(
            evaluation, item.schema.direction, config.minimum_cross_section
        )
        objective = (
            None
            if rank_ic is None or stability is None or turnover is None
            else rank_ic + config.stability_weight * stability - config.turnover_penalty * turnover
        )
        raw.append((item, evaluation, coverage, rank_ic, stability, turnover, objective))

    raw.sort(
        key=lambda row: (
            -(row[6] if row[6] is not None else float("-inf")),
            row[0].schema.fingerprint,
        )
    )
    selected: list[tuple[GeneratedCandidate, tuple[EvaluationObservation, ...]]] = []
    selected_families: dict[str, int] = {}
    family_budgets = dict(config.family_budgets)
    scores: list[CandidateScreenScore] = []
    for item, evaluation, coverage, rank_ic, stability, turnover, objective in raw:
        family = _family(item.schema.schema_id)
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
        elif stability is None or stability < config.minimum_positive_year_fraction:
            decision, reason = "screened_out", "insufficient positive-year stability"
        elif turnover is None or turnover > config.maximum_rank_turnover:
            decision, reason = "screened_out", "rank turnover exceeds frozen cost proxy"
        elif (
            maximum_correlation is not None
            and maximum_correlation > config.maximum_peer_rank_correlation
        ):
            decision, reason = "screened_out", "redundant with a stronger selected candidate"
        elif len(selected) >= campaign.spec.budget.cpcv:
            decision, reason = "screened_out", "frozen CPCV shortlist budget exhausted"
        elif family in family_budgets and selected_families.get(family, 0) >= family_budgets[family]:
            decision, reason = "screened_out", "frozen factor-family budget exhausted"
        else:
            decision, reason = "shortlisted", "passed frozen training-only screen"
            selected.append((item, evaluation))
            selected_families[family] = selected_families.get(family, 0) + 1
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
            family=family,
            positive_year_fraction=stability,
            rank_turnover=turnover,
            objective_score=objective,
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
