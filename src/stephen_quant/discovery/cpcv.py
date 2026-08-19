from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import timedelta
from math import comb

from stephen_quant.baseline import BaselineObservation
from stephen_quant.cross_validation import (
    SampleInterval,
    SplitLineage,
    audit_manifest,
    generate_cpcv_manifest,
)
from stephen_quant.evaluation import spearman_correlation
from stephen_quant.falsification import PBOResult, probability_of_backtest_overfitting
from stephen_quant.integrity.models import TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry

from .campaign import SearchCampaign
from .generator import GeneratedCandidate
from .screening import ScreeningReport, ScreeningWindow, _timestamp_date

CPCV_DISCOVERY_VERSION = "v1.8.16-generated-factor-cpcv-1.0.0"


@dataclass(frozen=True)
class DiscoveryCpcvConfig:
    groups: int = 6
    test_groups: int = 3
    embargo_days: int = 5
    minimum_mean_path_rank_ic: float = 0.02
    minimum_positive_paths: int = 8
    maximum_pbo: float = 0.20

    def validate(self) -> None:
        if self.groups < 2 or not 1 <= self.test_groups < self.groups:
            raise ValueError("invalid CPCV group configuration")
        if self.embargo_days < 0:
            raise ValueError("embargo_days cannot be negative")
        if self.minimum_positive_paths < 1:
            raise ValueError("minimum_positive_paths must be positive")
        available_paths = comb(self.groups - 1, self.test_groups - 1)
        if self.minimum_positive_paths > available_paths:
            raise ValueError(
                "minimum_positive_paths exceeds the configured CPCV path count"
            )
        if not 0 <= self.maximum_pbo <= 1:
            raise ValueError("maximum_pbo must be in [0, 1]")


@dataclass(frozen=True)
class DiscoveryCpcvScore:
    schema_id: str
    fingerprint: str
    trial_id: str
    trial_number: int
    mean_path_rank_ic: float
    positive_paths: int
    path_scores: dict[str, float]


@dataclass(frozen=True)
class DiscoveryCpcvReport:
    method_version: str
    campaign_id: str
    experiment_id: str
    cpcv_manifest_sha256: str
    hygiene_passed: bool
    configurations: tuple[DiscoveryCpcvScore, ...]
    selected_fingerprint: str
    pbo: PBOResult
    signal_gate_passed: bool
    validation_window_opened: bool
    decision: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, *, language: str = "en") -> str:
        selected = next(
            score for score in self.configurations
            if score.fingerprint == self.selected_fingerprint
        )
        if language == "zh":
            title = "# V1.8.16 自动生成因子 CPCV 报告"
            conclusion = "结论"
            candidate = "入选候选"
            mean_score = "路径平均 RankIC"
            positives = "正路径"
            hygiene = "CPCV 完整性"
            validation = "是否打开验证期"
            no = "否"
        elif language == "en":
            title = "# V1.8.16 Generated-Factor CPCV Report"
            conclusion = "Decision"
            candidate = "Selected candidate"
            mean_score = "Mean path RankIC"
            positives = "Positive paths"
            hygiene = "CPCV hygiene"
            validation = "Validation window opened"
            no = "no"
        else:
            raise ValueError("report language must be en or zh")
        lines = [
            title,
            "",
            f"**{conclusion}: {self.decision}**",
            "",
            f"- Campaign: `{self.campaign_id}`",
            f"- Experiment: `{self.experiment_id}`",
            f"- CPCV manifest: `{self.cpcv_manifest_sha256}`",
            f"- {candidate}: `{selected.schema_id}` / `{selected.fingerprint}`",
            f"- {mean_score}: {selected.mean_path_rank_ic:.6f}",
            f"- {positives}: {selected.positive_paths}/{len(selected.path_scores)}",
            f"- PBO: {self.pbo.probability:.6f}",
            f"- {hygiene}: {self.hygiene_passed}",
            f"- {validation}: {no}",
            "",
        ]
        return "\n".join(lines)


def _date_groups(dates: list[str], groups: int) -> dict[str, int]:
    size, remainder = divmod(len(dates), groups)
    result: dict[str, int] = {}
    offset = 0
    for group_id in range(groups):
        width = size + (1 if group_id < remainder else 0)
        for day in dates[offset : offset + width]:
            result[day] = group_id
        offset += width
    return result


def _daily_rank_ic(
    rows: tuple[BaselineObservation, ...], direction: int
) -> dict[str, float]:
    by_day: dict[str, list[BaselineObservation]] = defaultdict(list)
    for row in rows:
        if row.eligible:
            by_day[_timestamp_date(row.execution_at)].append(row)
    result: dict[str, float] = {}
    for day in sorted(by_day):
        cross_section = sorted(by_day[day], key=lambda row: row.instrument)
        if len(cross_section) < 3:
            raise ValueError(f"CPCV cross-section {day} requires at least three instruments")
        signals = [direction * row.signal for row in cross_section]
        returns = [row.forward_return for row in cross_section]
        if len(set(signals)) < 2 or len(set(returns)) < 2:
            continue
        result[day] = spearman_correlation(
            signals,
            returns,
        )
    return result


def run_discovery_cpcv(
    registry: ExperimentRegistry,
    campaign: SearchCampaign,
    screening: ScreeningReport,
    candidates: tuple[GeneratedCandidate, ...],
    observations: dict[str, tuple[BaselineObservation, ...]],
    *,
    snapshot_id: str,
    code_version: str,
    window: ScreeningWindow,
    config: DiscoveryCpcvConfig,
    seed: int = 42,
) -> DiscoveryCpcvReport:
    """Evaluate only the frozen shortlist with purged CPCV and PBO."""

    config.validate()
    window.validate()
    if screening.campaign_id != campaign.campaign_id:
        raise ValueError("screening report belongs to another campaign")
    shortlisted = set(screening.shortlisted_fingerprints)
    selected_candidates = [item for item in candidates if item.schema.fingerprint in shortlisted]
    if len(selected_candidates) < 2:
        raise ValueError("CPCV/PBO requires at least two shortlisted configurations")
    if len(selected_candidates) > campaign.spec.budget.cpcv:
        raise ValueError("shortlist exceeds the frozen CPCV budget")
    if set(observations) != shortlisted:
        raise ValueError("CPCV observations must exactly match the frozen shortlist")

    reference: dict[str, BaselineObservation] = {}
    reference_keys: set[tuple[str, str]] | None = None
    for item in selected_candidates:
        rows = observations[item.schema.fingerprint]
        eligible_rows = tuple(row for row in rows if row.eligible)
        keys = {
            (_timestamp_date(row.execution_at), row.instrument)
            for row in eligible_rows
        }
        if len(keys) != len(eligible_rows):
            raise ValueError("duplicate CPCV observation key")
        if reference_keys is None:
            reference_keys = keys
            for row in eligible_rows:
                reference.setdefault(_timestamp_date(row.execution_at), row)
        elif keys != reference_keys:
            raise ValueError("CPCV candidates must share the same eligible observation panel")
        for row in rows:
            if (
                _timestamp_date(row.execution_at) < window.research_start
                or _timestamp_date(row.return_end_at) > window.research_end
            ):
                raise ValueError("CPCV observations touch a sealed or out-of-research window")
    daily_by_fingerprint = {
        item.schema.fingerprint: _daily_rank_ic(
            observations[item.schema.fingerprint], item.schema.direction
        )
        for item in selected_candidates
    }
    valid_date_sets = [set(values) for values in daily_by_fingerprint.values()]
    dates = sorted(set(reference).intersection(*valid_date_sets))
    if len(dates) < config.groups:
        raise ValueError("CPCV common valid-IC dates are fewer than configured groups")

    trials: dict[str, tuple[str, int]] = {}
    for item in selected_candidates:
        schema = item.schema
        trials[schema.fingerprint] = registry.create_trial(
            TrialSpec(
                experiment_id=campaign.spec.experiment_id,
                model_name="v1.8.16_generated_factor_cpcv",
                factor_set=schema.schema_id,
                hyperparams=json.dumps(
                    {
                        "campaign_id": campaign.campaign_id,
                        "fingerprint": schema.fingerprint,
                        "schema": json.loads(schema.to_json()),
                        "cpcv": asdict(config),
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                seed=seed,
                train_start=window.research_start,
                train_end=window.research_end,
                validation_start=window.validation_start,
                validation_end=window.validation_end,
                test_start=window.test_start,
                test_end=window.test_end,
            )
        )

    samples = tuple(
        SampleInterval(
            sample_id=day,
            instrument="CROSS_SECTION",
            feature_at=reference[day].signal_available_at,
            label_start_at=reference[day].execution_at,
            label_end_at=reference[day].return_end_at,
        )
        for day in dates
    )
    first_trial = trials[selected_candidates[0].schema.fingerprint][0]
    manifest = generate_cpcv_manifest(
        samples,
        SplitLineage(snapshot_id, campaign.spec.experiment_id, first_trial, code_version),
        n_groups=config.groups,
        n_test_groups=config.test_groups,
        embargo=timedelta(days=config.embargo_days),
    )
    findings = audit_manifest(manifest, samples)
    hygiene = all(finding.passed for finding in findings)
    groups = _date_groups(dates, config.groups)
    fold_by_id = {fold.fold_id: fold for fold in manifest.folds}
    scores: list[DiscoveryCpcvScore] = []
    pbo_inputs: dict[str, dict[str, float]] = {}
    for item in selected_candidates:
        daily = daily_by_fingerprint[item.schema.fingerprint]
        path_scores: dict[str, float] = {}
        for path in manifest.paths:
            values: list[float] = []
            for segment in path.segments:
                fold = fold_by_id[segment.fold_id]
                values.extend(
                    daily[day]
                    for day in fold.test_ids
                    if groups[day] == segment.group_id
                )
            path_scores[path.path_id] = sum(values) / len(values)
        trial_id, trial_number = trials[item.schema.fingerprint]
        score = DiscoveryCpcvScore(
            schema_id=item.schema.schema_id,
            fingerprint=item.schema.fingerprint,
            trial_id=trial_id,
            trial_number=trial_number,
            mean_path_rank_ic=sum(path_scores.values()) / len(path_scores),
            positive_paths=sum(value > 0 for value in path_scores.values()),
            path_scores=path_scores,
        )
        scores.append(score)
        pbo_inputs[item.schema.fingerprint] = path_scores
    pbo = probability_of_backtest_overfitting(manifest, pbo_inputs, findings)
    winner = max(scores, key=lambda score: (score.mean_path_rank_ic, score.fingerprint))
    # A fixed, non-fitted signal can produce identical full-path averages because
    # every combinatorial path traverses every temporal group exactly once.  In
    # that case PBO and positive-path counts contain no path-wise falsification
    # information and must not authorize the signal gate.
    degenerate_paths = all(
        max(score.path_scores.values()) - min(score.path_scores.values()) <= 1e-12
        for score in scores
    )
    passed = (
        hygiene
        and not degenerate_paths
        and winner.mean_path_rank_ic >= config.minimum_mean_path_rank_ic
        and winner.positive_paths >= config.minimum_positive_paths
        and pbo.probability <= config.maximum_pbo
    )
    decision = (
        "PASS_SIGNAL_GATE"
        if passed
        else "REJECT_DEGENERATE_CPCV_PATHS"
        if degenerate_paths
        else "REJECT_SIGNAL_GATE"
    )
    report = DiscoveryCpcvReport(
        method_version=CPCV_DISCOVERY_VERSION,
        campaign_id=campaign.campaign_id,
        experiment_id=campaign.spec.experiment_id,
        cpcv_manifest_sha256=manifest.manifest_sha256,
        hygiene_passed=hygiene,
        configurations=tuple(scores),
        selected_fingerprint=winner.fingerprint,
        pbo=pbo,
        signal_gate_passed=passed,
        validation_window_opened=False,
        decision=decision,
    )
    for score in scores:
        registry.record_trial_result(
            score.trial_id,
            json.dumps(
                {"family_decision": decision, **asdict(score)},
                separators=(",", ":"),
                sort_keys=True,
            ),
        )
    return report
