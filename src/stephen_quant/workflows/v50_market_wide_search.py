from __future__ import annotations

import gc
import hashlib
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import timedelta
from pathlib import Path
from statistics import mean

from stephen_quant.cross_validation import (
    SampleInterval,
    SplitLineage,
    audit_manifest,
    generate_cpcv_manifest,
)
from stephen_quant.evaluation import EvaluationObservation
from stephen_quant.falsification import (
    deflated_sharpe_ratio,
    probability_of_backtest_overfitting,
    run_rank_placebo_fast,
)
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import (
    build_composite_snapshot_manifest,
    build_selected_files_snapshot_manifest,
)
from stephen_quant.qmt import (
    QdAlternativeConfig,
    build_multisource_factor_observations,
    load_qd_alternative_directory,
    load_qd_daily_directory,
    select_qd_daily_files,
)

from .price_discovery_lab import _execution_memberships, _load_memberships
from .v41_semantic_alpha import (
    UsageEvent,
    UsageSpec,
    V41Config,
    _anchors,
    _daily_metrics,
    evaluate_usage,
    evaluate_usage_events,
)
from .v44_path_robust_alpha import PathRobustness, summarize_paths
from .v46_orthogonal_search import (
    CandidateEvidence,
    EnsembleStress,
    YearEvidence,
    _decay_alarm,
    _ensemble_panel,
    _quarterly,
    curated_schemas,
    select_orthogonal,
)

V50_VERSION = "v5.0-market-wide-alpha-search-1.1.0"
YEARS = (2022, 2023, 2024)
DIMENSIONS = {"size": ("large", "mid", "small"), "liquidity": ("high", "mid", "low")}


@dataclass(frozen=True)
class V50Config:
    data_start: str = "2021-01-01"
    data_end: str = "2024-12-31"
    years: tuple[int, ...] = YEARS
    horizon: int = 20
    breadth: int = 50
    primary_nav: float = 3_000_000.0
    stress_nav: float = 20_000_000.0
    commission_bps: float = 3.0
    sell_tax_bps: float = 5.0
    slippage_bps: float = 5.0
    impact_bps: float = 10.0
    participation_rate: float = 0.05
    maximum_orthogonal_correlation: float = 0.75
    minimum_ensemble_domains: int = 2
    minimum_development_sharpe: float = 0.50
    minimum_positive_stress_fraction: float = 0.75
    minimum_dsr: float = 0.95
    maximum_pbo: float = 0.05
    maximum_placebo_p: float = 0.05
    placebo_repetitions: int = 199
    cpcv_groups: int = 6
    cpcv_test_groups: int = 3
    embargo_days: int = 5
    ingested_at: str = "2026-08-18T00:00:00+08:00"
    seed: int = 42

    def validate(self) -> None:
        if self.years != YEARS or self.horizon != 20 or self.breadth != 50:
            raise ValueError("V5.0 years, horizon and breadth are frozen")
        if self.data_start != "2021-01-01" or self.data_end != "2024-12-31":
            raise ValueError("V5.0 data window is frozen")
        if self.primary_nav != 3_000_000.0 or self.stress_nav != 20_000_000.0:
            raise ValueError("V5.0 NAV grid is frozen")
        if (self.cpcv_groups, self.cpcv_test_groups, self.embargo_days) != (6, 3, 5):
            raise ValueError("V5.0 CPCV design is frozen")


@dataclass(frozen=True)
class SliceEvidence:
    dimension: str
    bucket: str
    observations: int
    dates: int
    mean_rank_ic: float
    mean_top_bottom: float
    path: PathRobustness
    trial_id: str
    trial_number: int


@dataclass(frozen=True)
class V50Report:
    method_version: str
    experiment_id: str
    snapshot_id: str
    snapshot_sha256: str
    screening_membership_sha256: str
    membership_sha256: str
    tiers_sha256: str
    candidate_trials: int
    stable_candidates: int
    selected_candidates: tuple[CandidateEvidence, ...]
    pairwise_ic_correlations: tuple[tuple[str, str, float], ...]
    ensemble_stress: tuple[EnsembleStress, ...]
    slice_evidence: tuple[SliceEvidence, ...]
    positive_stress_fraction: float
    cpcv_paths: int
    pbo_probability: float | None
    signal_placebo_p: float | None
    return_placebo_p: float | None
    dsr_probability: float | None
    dsr_skewness: float | None
    dsr_excess_kurtosis: float | None
    recorded_trial_count: int
    decision: str
    failures: tuple[str, ...]
    evidence_status: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        lines = [
            "# V5.0 全市场平衡股票池 Alpha 搜索" if zh else "# V5.0 Market-wide balanced-universe Alpha search",
            "",
            f"**{'结论' if zh else 'Decision'}: `{self.decision}`**",
            "",
            f"- {'候选 Trials' if zh else 'Candidate Trials'}: {self.candidate_trials}",
            f"- {'稳定候选' if zh else 'Stable candidates'}: {self.stable_candidates}",
            f"- {'累计 Trial' if zh else 'Cumulative Trials'}: {self.recorded_trial_count}",
            f"- PBO: {self.pbo_probability if self.pbo_probability is not None else 'N/A'}",
            f"- DSR: {self.dsr_probability if self.dsr_probability is not None else 'N/A'}",
            (
                f"- {'DSR 偏度/超额峰度' if zh else 'DSR skew/excess kurtosis'}: "
                f"{self.dsr_skewness if self.dsr_skewness is not None else 'N/A'} / "
                f"{self.dsr_excess_kurtosis if self.dsr_excess_kurtosis is not None else 'N/A'}"
            ),
            f"- Placebo: {self.signal_placebo_p} / {self.return_placebo_p}",
            "",
            "## 入选候选" if zh else "## Selected candidates",
            "",
            "| Candidate | Domain | 2022 IC | 2023 IC | 2024 IC | Objective |",
            "|---|---|---:|---:|---:|---:|",
        ]
        for item in self.selected_candidates:
            values = {year.year: year.mean_rank_ic for year in item.years}
            lines.append(
                f"| `{item.candidate_id}` | {item.domain} | {values[2022]:.4f} | "
                f"{values[2023]:.4f} | {values[2024]:.4f} | {item.objective:.4f} |"
            )
        lines.extend(
            [
                "",
                "## 规模与流动性切片" if zh else "## Size and liquidity slices",
                "",
                "| Dimension | Bucket | RankIC | Increment | Positive paths |",
                "|---|---|---:|---:|---:|",
            ]
        )
        for item in self.slice_evidence:
            lines.append(
                f"| {item.dimension} | {item.bucket} | {item.mean_rank_ic:.4f} | "
                f"{item.path.incremental_return:.2%} | "
                f"{item.path.positive_return_paths}/{item.path.paths} |"
            )
        lines.extend(
            [
                "",
                (
                    f"- {'失败门禁' if zh else 'Failed gates'}: "
                    f"{', '.join(self.failures) or ('无' if zh else 'none')}"
                ),
                f"- {'证据状态' if zh else 'Evidence status'}: {self.evidence_status}",
                "",
            ]
        )
        return "\n".join(lines)


def _trial(
    registry: ExperimentRegistry,
    experiment_id: str,
    *,
    stage: str,
    factor_set: str,
    parameters: dict[str, object],
    seed: int,
) -> tuple[str, int]:
    return registry.create_trial(
        TrialSpec(
            experiment_id,
            stage,
            factor_set,
            json.dumps(parameters, sort_keys=True, separators=(",", ":")),
            seed,
            "2020-01-01",
            "2022-12-31",
            "2023-01-01",
            "2023-12-31",
            "2024-01-01",
            "2024-12-31",
        )
    )


def _stable(years: tuple[YearEvidence, ...]) -> bool:
    if tuple(item.year for item in years) != YEARS:
        raise ValueError("V5.0 candidate evidence must cover 2022-2024")
    return (
        sum(item.mean_rank_ic > 0 for item in years) >= 2
        and sum(item.path.incremental_return > 0 for item in years) >= 2
        and min(item.mean_rank_ic for item in years) >= -0.02
        and years[1].mean_rank_ic > 0
        and years[2].mean_rank_ic > 0
        and sum(item.path.median_sharpe > 0 for item in years) >= 2
    )


def _load_tiers(path: str | Path) -> tuple[dict[str, dict[str, dict[str, tuple[str, ...]]]], str]:
    source = Path(path).expanduser().resolve()
    content = source.read_bytes()
    result: dict[str, dict[str, dict[str, tuple[str, ...]]]] = {}
    for number, line in enumerate(content.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        day = str(payload["decision_date"])
        if day in result:
            raise ValueError(f"duplicate V5.0 tier date at line {number}")
        result[day] = {
            dimension: {
                bucket: tuple(str(item) for item in members)
                for bucket, members in payload[f"{dimension}_buckets"].items()
            }
            for dimension in DIMENSIONS
        }
    if not result:
        raise ValueError("V5.0 tier file is empty")
    return result, hashlib.sha256(content).hexdigest()


def _execution_tiers(
    tiers: dict[str, dict[str, dict[str, tuple[str, ...]]]],
    dates: tuple[str, ...],
) -> dict[str, dict[str, dict[str, frozenset[str]]]]:
    decisions = sorted(tiers)
    output: dict[str, dict[str, dict[str, frozenset[str]]]] = {}
    latest = {dimension: {bucket: frozenset() for bucket in buckets} for dimension, buckets in DIMENSIONS.items()}
    cursor = 0
    for day in dates:
        while cursor < len(decisions) and decisions[cursor] < day:
            source = tiers[decisions[cursor]]
            latest = {
                dimension: {
                    bucket: frozenset(source[dimension][bucket]) for bucket in buckets
                }
                for dimension, buckets in DIMENSIONS.items()
            }
            cursor += 1
        output[day] = latest
    return output


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


def _incremental_returns(
    events: list[UsageEvent], controls: list[UsageEvent]
) -> tuple[float, ...]:
    candidate = {(item.day, item.offset): item.excess_return for item in events}
    control = {(item.day, item.offset): item.excess_return for item in controls}
    if set(candidate) != set(control):
        raise ValueError("candidate/control grids differ in V5.0 DSR")
    values = {
        day: candidate[(day, offset)] - control[(day, offset)]
        for day, offset in candidate
    }
    return tuple(values[day] for day in sorted(values))


def _moments(values: tuple[float, ...]) -> tuple[float, float]:
    if len(values) < 4:
        raise ValueError("V5.0 DSR moments require at least four observations")
    center = mean(values)
    variance = mean((item - center) ** 2 for item in values)
    if variance <= 0:
        raise ValueError("V5.0 DSR moments require non-zero variance")
    skewness = mean((item - center) ** 3 for item in values) / variance**1.5
    excess_kurtosis = mean((item - center) ** 4 for item in values) / variance**2 - 3
    return skewness, excess_kurtosis


def _candidate_pbo(
    daily_ics: dict[str, dict[str, float]],
    intervals: dict[str, tuple[str, str, str]],
    *,
    registry_lineage: SplitLineage,
    config: V50Config,
) -> tuple[float, int]:
    dates = sorted(set(intervals).intersection(*(set(values) for values in daily_ics.values())))
    samples = tuple(
        SampleInterval(
            sample_id=day,
            instrument="CROSS_SECTION",
            feature_at=intervals[day][0],
            label_start_at=intervals[day][1],
            label_end_at=intervals[day][2],
        )
        for day in dates
    )
    manifest = generate_cpcv_manifest(
        samples,
        registry_lineage,
        n_groups=config.cpcv_groups,
        n_test_groups=config.cpcv_test_groups,
        embargo=timedelta(days=config.embargo_days),
    )
    findings = audit_manifest(manifest, samples)
    groups = _date_groups(dates, config.cpcv_groups)
    folds = {fold.fold_id: fold for fold in manifest.folds}
    pbo_inputs: dict[str, dict[str, float]] = {}
    for candidate_id, daily in daily_ics.items():
        scores: dict[str, float] = {}
        for path in manifest.paths:
            values: list[float] = []
            for segment in path.segments:
                fold = folds[segment.fold_id]
                values.extend(
                    daily[day]
                    for day in fold.test_ids
                    if groups[day] == segment.group_id
                )
            scores[path.path_id] = mean(values)
        pbo_inputs[candidate_id] = scores
    result = probability_of_backtest_overfitting(manifest, pbo_inputs, findings)
    return result.probability, len(manifest.paths)


def run_v50_market_wide_search(
    daily_dir: str | Path,
    screening_membership_path: str | Path,
    validation_membership_path: str | Path,
    tiers_path: str | Path,
    *,
    auction_dir: str | Path,
    fund_flow_dir: str | Path,
    chip_dir: str | Path,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    config: V50Config | None = None,
    prior_inferential_trials: int = 1114,
) -> V50Report:
    config = config or V50Config()
    config.validate()
    if prior_inferential_trials < 1114:
        raise ValueError("V5.0 cannot discard the 1,114 pre-existing inferential Trials")
    schemas = curated_schemas()
    screening_memberships, screening_membership_sha = _load_memberships(
        screening_membership_path, 10_000
    )
    memberships, membership_sha = _load_memberships(validation_membership_path, 10_000)
    tiers, tiers_sha = _load_tiers(tiers_path)
    if set(screening_memberships) != set(memberships) or set(memberships) != set(tiers):
        raise ValueError("V5.0 screening, validation and tier dates differ")
    screening_instruments = tuple(
        sorted({item for members in screening_memberships.values() for item in members})
    )
    validation_instruments = tuple(
        sorted({item for members in memberships.values() for item in members})
    )
    root = Path(daily_dir).expanduser().resolve()
    files = select_qd_daily_files(root, start_date=config.data_start, end_date=config.data_end)
    daily_manifest = build_selected_files_snapshot_manifest(root, files)
    daily = load_qd_daily_directory(
        root,
        start_date=config.data_start,
        end_date=config.data_end,
        instruments=screening_instruments,
    )
    alternatives = {}
    alternative_hashes = {}
    for kind, source in (
        ("auction", auction_dir),
        ("fund_flow", fund_flow_dir),
        ("chip", chip_dir),
    ):
        dataset = load_qd_alternative_directory(
            source,
            QdAlternativeConfig(
                source_kind=kind,  # type: ignore[arg-type]
                start_date=config.data_start,
                end_date=config.data_end,
                ingested_at=config.ingested_at,
                instruments=screening_instruments,
            ),
        )
        alternatives[kind] = dataset.observations
        alternative_hashes[kind] = dataset.audit.source_sha256
    composite = build_composite_snapshot_manifest(
        {
            "qd_daily": daily_manifest.snapshot_sha256,
            "market_wide_screening_membership": screening_membership_sha,
            "market_wide_membership": membership_sha,
            "market_wide_tiers": tiers_sha,
            **alternative_hashes,
        }
    )
    snapshot_id = registry.register_snapshot(
        composite,
        vendor_version=V50_VERSION,
        notes="2022 development, 2023 confirmation, 2024 reused shadow; no independent final proof",
    )
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            "V5.0 market-wide balanced-universe alpha search",
            "A size-balanced investable panel may reveal mechanisms hidden by the Top50 universe.",
            snapshot_id,
            code_version,
            json.dumps({"version": V50_VERSION, "config": asdict(config)}, sort_keys=True),
        )
    )
    calendar = tuple(sorted({item.trade_date for item in daily.bars}))
    by_instrument = defaultdict(dict)
    for bar in daily.bars:
        by_instrument[bar.instrument][bar.trade_date] = bar
    screening_execution_members = _execution_memberships(screening_memberships, calendar)
    validation_execution_members = _execution_memberships(memberships, calendar)
    execution_tiers = _execution_tiers(tiers, calendar)
    usage_config = V41Config(
        primary_nav=config.primary_nav,
        commission_bps=config.commission_bps,
        sell_tax_bps=config.sell_tax_bps,
        slippage_bps=config.slippage_bps,
        impact_bps=config.impact_bps,
        participation_rate=config.participation_rate,
        ingested_at=config.ingested_at,
    )
    screening_anchors = {
        year: _anchors(
            year=year,
            horizon=config.horizon,
            calendar=calendar,
            bars=by_instrument,
            execution_members=screening_execution_members,
        )
        for year in YEARS
    }
    combined_screening_anchors = tuple(
        row for year in YEARS for row in screening_anchors[year]
    )
    evidence: list[CandidateEvidence] = []
    daily_ics: dict[str, dict[str, float]] = {}
    raw_candidate_sharpes: list[float] = []
    intervals: dict[str, tuple[str, str, str]] = {}
    trial_ids: list[str] = []
    schema_by_id = {schema.schema_id: schema for _, schema in schemas}
    for domain, schema in schemas:
        required = {
            source: alternatives[source.removeprefix("qd_")]
            for source in schema.data_sources
            if source != "qd_daily"
        }
        trial = _trial(
            registry,
            experiment_id,
            stage="v5.0_market_wide_candidate",
            factor_set=schema.schema_id,
            parameters={"domain": domain, "fingerprint": schema.fingerprint, "usage": "BUY50"},
            seed=config.seed,
        )
        trial_ids.append(trial[0])
        built = build_multisource_factor_observations(
            daily.bars, required, schema.compile(), combined_screening_anchors
        )
        all_rows = tuple(
            EvaluationObservation(
                timestamp=row.execution_at,
                instrument=row.instrument,
                factor_value=schema.direction * row.signal,
                factor_available_at=row.signal_available_at,
                label_start_at=row.execution_at,
                label_end_at=row.return_end_at,
                forward_return=row.forward_return,
                horizon="20d",
                subperiod=row.execution_at[:4],
                regime="unspecified",
            )
            for row in built
            if row.eligible
        )
        yearly: list[YearEvidence] = []
        ic_series: dict[str, float] = {}
        for year in YEARS:
            rows = tuple(row for row in all_rows if row.timestamp.startswith(f"{year}-"))
            metrics = _daily_metrics(rows)
            if not metrics:
                raise ValueError(f"empty V5.0 metrics: {schema.schema_id}:{year}")
            ic_series.update({item.day: item.rank_ic for item in metrics})
            spec = UsageSpec("BUY", config.breadth, "all")
            events, _ = evaluate_usage_events(
                rows,
                rows,
                spec,
                horizon=config.horizon,
                nav=config.primary_nav,
                bars=by_instrument,
                calendar=calendar,
                regimes={},
                config=usage_config,
            )
            controls, _ = evaluate_usage_events(
                rows,
                rows,
                UsageSpec("AVOID", 0, "all"),
                horizon=config.horizon,
                nav=config.primary_nav,
                bars=by_instrument,
                calendar=calendar,
                regimes={},
                config=usage_config,
            )
            portfolio, _ = evaluate_usage(
                schema.schema_id,
                rows,
                rows,
                spec,
                year=year,
                horizon=config.horizon,
                nav=config.primary_nav,
                bars=by_instrument,
                calendar=calendar,
                regimes={},
                config=usage_config,
            )
            path = summarize_paths(
                year,
                events,
                controls,
                horizon=config.horizon,
                portfolio_sharpe=portfolio.excess_sharpe,
                portfolio_return=portfolio.cumulative_excess_return,
                portfolio_drawdown=portfolio.maximum_drawdown,
            )
            yearly.append(
                YearEvidence(
                    year,
                    len(metrics),
                    mean(item.rank_ic for item in metrics),
                    mean(item.top_bottom for item in metrics),
                    _quarterly(metrics),
                    path,
                )
            )
        for row in all_rows:
            day = row.timestamp[:10]
            current = intervals.get(day)
            candidate = (row.factor_available_at, row.label_start_at, row.label_end_at)
            if current is None:
                intervals[day] = candidate
            else:
                if current[1:] != candidate[1:]:
                    raise ValueError("V5.0 candidate label intervals differ")
                intervals[day] = (max(current[0], candidate[0]), current[1], current[2])
        year_tuple = tuple(yearly)
        objective = min(item.mean_rank_ic for item in year_tuple[1:]) + mean(
            item.mean_rank_ic for item in year_tuple
        )
        candidate_evidence = CandidateEvidence(
            schema.schema_id,
            schema.fingerprint,
            domain,
            schema.direction,
            year_tuple,
            _stable(year_tuple),
            _decay_alarm(year_tuple),
            objective,
            trial[0],
            trial[1],
        )
        registry.record_trial_result(
            trial[0], json.dumps(asdict(candidate_evidence), sort_keys=True)
        )
        evidence.append(candidate_evidence)
        daily_ics[schema.schema_id] = ic_series
        raw_candidate_sharpes.append(
            mean(item.path.incremental_daily_sharpe for item in year_tuple) / math.sqrt(252)
        )
    selected, correlations = select_orthogonal(
        tuple(evidence),
        daily_ics,
        maximum_correlation=config.maximum_orthogonal_correlation,
    )
    pbo, cpcv_paths = _candidate_pbo(
        daily_ics,
        intervals,
        registry_lineage=SplitLineage(
            snapshot_id, experiment_id, trial_ids[0], code_version
        ),
        config=config,
    )

    stress_results: list[EnsembleStress] = []
    slice_results: list[SliceEvidence] = []
    signal_p = return_p = dsr_probability = None
    dsr_skewness = dsr_excess_kurtosis = None
    failures: list[str] = []
    stress_raw: list[float] = []
    slice_raw: list[float] = []
    primary_incremental_returns: tuple[float, ...] | None = None
    if len(selected) < config.minimum_ensemble_domains:
        failures.append("insufficient_orthogonal_domains")
    else:
        del daily, alternatives, by_instrument
        gc.collect()
        daily = load_qd_daily_directory(
            root,
            start_date=config.data_start,
            end_date=config.data_end,
            instruments=validation_instruments,
        )
        alternatives = {}
        for kind, source in (
            ("auction", auction_dir),
            ("fund_flow", fund_flow_dir),
            ("chip", chip_dir),
        ):
            dataset = load_qd_alternative_directory(
                source,
                QdAlternativeConfig(
                    source_kind=kind,  # type: ignore[arg-type]
                    start_date=config.data_start,
                    end_date=config.data_end,
                    ingested_at=config.ingested_at,
                    instruments=validation_instruments,
                ),
            )
            if dataset.audit.source_sha256 != alternative_hashes[kind]:
                raise ValueError(f"V5.0 {kind} source changed between stages")
            alternatives[kind] = dataset.observations
        calendar = tuple(sorted({item.trade_date for item in daily.bars}))
        by_instrument = defaultdict(dict)
        for bar in daily.bars:
            by_instrument[bar.instrument][bar.trade_date] = bar
        validation_anchors = {
            year: _anchors(
                year=year,
                horizon=config.horizon,
                calendar=calendar,
                bars=by_instrument,
                execution_members=validation_execution_members,
            )
            for year in YEARS
        }
        combined_validation_anchors = tuple(
            row for year in YEARS for row in validation_anchors[year]
        )
        selected_panels: dict[str, dict[int, tuple[EvaluationObservation, ...]]] = {}
        for item in selected:
            schema = schema_by_id[item.candidate_id]
            required = {
                source: alternatives[source.removeprefix("qd_")]
                for source in schema.data_sources
                if source != "qd_daily"
            }
            built = build_multisource_factor_observations(
                daily.bars, required, schema.compile(), combined_validation_anchors
            )
            rows = tuple(
                EvaluationObservation(
                    timestamp=row.execution_at,
                    instrument=row.instrument,
                    factor_value=schema.direction * row.signal,
                    factor_available_at=row.signal_available_at,
                    label_start_at=row.execution_at,
                    label_end_at=row.return_end_at,
                    forward_return=row.forward_return,
                    horizon="20d",
                    subperiod=row.execution_at[:4],
                    regime="unspecified",
                )
                for row in built
                if row.eligible
            )
            selected_panels[item.candidate_id] = {
                year: tuple(row for row in rows if row.timestamp.startswith(f"{year}-"))
                for year in YEARS
            }
        ensemble_by_year = {
            year: _ensemble_panel(
                tuple(selected_panels[item.candidate_id][year] for item in selected),
                year=year,
            )
            for year in YEARS
        }
        all_ensemble = tuple(row for year in YEARS for row in ensemble_by_year[year])
        for nav in (config.primary_nav, config.stress_nav):
            for multiplier in (1.0, 2.0):
                stress_config = replace(
                    usage_config,
                    primary_nav=nav,
                    commission_bps=config.commission_bps * multiplier,
                    sell_tax_bps=config.sell_tax_bps * multiplier,
                    slippage_bps=config.slippage_bps * multiplier,
                    impact_bps=config.impact_bps * multiplier,
                )
                events_all, controls_all = [], []
                returns, drawdowns, sharpes = [], [], []
                clipped = 0.0
                for year in YEARS:
                    rows = ensemble_by_year[year]
                    spec = UsageSpec("BUY", config.breadth, "all")
                    events, clipped_year = evaluate_usage_events(
                        rows,
                        rows,
                        spec,
                        horizon=config.horizon,
                        nav=nav,
                        bars=by_instrument,
                        calendar=calendar,
                        regimes={},
                        config=stress_config,
                    )
                    controls, _ = evaluate_usage_events(
                        rows,
                        rows,
                        UsageSpec("AVOID", 0, "all"),
                        horizon=config.horizon,
                        nav=nav,
                        bars=by_instrument,
                        calendar=calendar,
                        regimes={},
                        config=stress_config,
                    )
                    score, _ = evaluate_usage(
                        "v50_equal_rank_ensemble",
                        rows,
                        rows,
                        spec,
                        year=year,
                        horizon=config.horizon,
                        nav=nav,
                        bars=by_instrument,
                        calendar=calendar,
                        regimes={},
                        config=stress_config,
                    )
                    events_all.extend(events)
                    controls_all.extend(controls)
                    clipped += clipped_year
                    returns.append(score.cumulative_excess_return)
                    drawdowns.append(score.maximum_drawdown)
                    sharpes.append(score.excess_sharpe)
                trial = _trial(
                    registry,
                    experiment_id,
                    stage="v5.0_ensemble_stress",
                    factor_set="+".join(item.candidate_id for item in selected),
                    parameters={"nav": nav, "cost_multiplier": multiplier},
                    seed=config.seed,
                )
                path = summarize_paths(
                    YEARS[0],
                    tuple(events_all),
                    tuple(controls_all),
                    horizon=config.horizon,
                    portfolio_sharpe=mean(sharpes),
                    portfolio_return=math.prod(1 + item for item in returns) - 1,
                    portfolio_drawdown=min(drawdowns),
                )
                result = EnsembleStress(nav, multiplier, path, clipped, trial[0], trial[1])
                registry.record_trial_result(trial[0], json.dumps(asdict(result), sort_keys=True))
                stress_results.append(result)
                stress_raw.append(path.incremental_daily_sharpe / math.sqrt(252))
                if nav == config.primary_nav and multiplier == 1.0:
                    primary_incremental_returns = _incremental_returns(
                        events_all, controls_all
                    )

        for dimension, buckets in DIMENSIONS.items():
            for bucket in buckets:
                rows = tuple(
                    row
                    for row in all_ensemble
                    if row.instrument
                    in execution_tiers[row.timestamp[:10]][dimension][bucket]
                )
                metrics = _daily_metrics(rows)
                events_all, controls_all = [], []
                returns, drawdowns, sharpes = [], [], []
                for year in YEARS:
                    year_rows = tuple(
                        row for row in rows if row.timestamp.startswith(f"{year}-")
                    )
                    spec = UsageSpec("BUY", min(config.breadth, 50), "all")
                    events, _ = evaluate_usage_events(
                        year_rows,
                        year_rows,
                        spec,
                        horizon=config.horizon,
                        nav=config.primary_nav,
                        bars=by_instrument,
                        calendar=calendar,
                        regimes={},
                        config=usage_config,
                    )
                    controls, _ = evaluate_usage_events(
                        year_rows,
                        year_rows,
                        UsageSpec("AVOID", 0, "all"),
                        horizon=config.horizon,
                        nav=config.primary_nav,
                        bars=by_instrument,
                        calendar=calendar,
                        regimes={},
                        config=usage_config,
                    )
                    score, _ = evaluate_usage(
                        f"v50_{dimension}_{bucket}",
                        year_rows,
                        year_rows,
                        spec,
                        year=year,
                        horizon=config.horizon,
                        nav=config.primary_nav,
                        bars=by_instrument,
                        calendar=calendar,
                        regimes={},
                        config=usage_config,
                    )
                    events_all.extend(events)
                    controls_all.extend(controls)
                    returns.append(score.cumulative_excess_return)
                    drawdowns.append(score.maximum_drawdown)
                    sharpes.append(score.excess_sharpe)
                trial = _trial(
                    registry,
                    experiment_id,
                    stage="v5.0_slice_diagnostic",
                    factor_set="+".join(item.candidate_id for item in selected),
                    parameters={"dimension": dimension, "bucket": bucket},
                    seed=config.seed,
                )
                path = summarize_paths(
                    YEARS[0],
                    tuple(events_all),
                    tuple(controls_all),
                    horizon=config.horizon,
                    portfolio_sharpe=mean(sharpes),
                    portfolio_return=math.prod(1 + item for item in returns) - 1,
                    portfolio_drawdown=min(drawdowns),
                )
                result = SliceEvidence(
                    dimension,
                    bucket,
                    len(rows),
                    len(metrics),
                    mean(item.rank_ic for item in metrics),
                    mean(item.top_bottom for item in metrics),
                    path,
                    trial[0],
                    trial[1],
                )
                registry.record_trial_result(trial[0], json.dumps(asdict(result), sort_keys=True))
                slice_results.append(result)
                slice_raw.append(path.incremental_daily_sharpe / math.sqrt(252))

        recorded_for_dsr = prior_inferential_trials + registry.global_trial_count()
        primary = next(
            item
            for item in stress_results
            if item.nav == config.primary_nav and item.cost_multiplier == 1.0
        )
        if primary_incremental_returns is None:
            raise AssertionError("primary V5.0 DSR return series was not captured")
        dsr_skewness, dsr_excess_kurtosis = _moments(primary_incremental_returns)
        dsr_probability = deflated_sharpe_ratio(
            observed_sharpe=primary.path.incremental_daily_sharpe / math.sqrt(252),
            trial_sharpes=raw_candidate_sharpes + stress_raw + slice_raw,
            recorded_trial_count=recorded_for_dsr,
            observations=sum(item.dates for item in selected[0].years),
            skewness=dsr_skewness,
            excess_kurtosis=dsr_excess_kurtosis,
        ).probability
        signal_p = run_rank_placebo_fast(
            all_ensemble,
            horizon="20d",
            direction=1,
            method="signal_shuffle",
            seed=config.seed,
            repetitions=config.placebo_repetitions,
            min_cross_section=10,
        ).empirical_p_value
        return_p = run_rank_placebo_fast(
            all_ensemble,
            horizon="20d",
            direction=1,
            method="return_permutation",
            seed=config.seed,
            repetitions=config.placebo_repetitions,
            min_cross_section=10,
        ).empirical_p_value
        positive_fraction = sum(
            item.path.incremental_return > 0 and item.path.portfolio_excess_return > 0
            for item in stress_results
        ) / len(stress_results)
        if primary.path.incremental_daily_sharpe < config.minimum_development_sharpe:
            failures.append("ensemble_sharpe")
        if primary.path.incremental_return <= 0 or primary.path.portfolio_excess_return <= 0:
            failures.append("ensemble_return")
        if positive_fraction < config.minimum_positive_stress_fraction:
            failures.append("stress_robustness")
        if dsr_probability < config.minimum_dsr:
            failures.append("multiplicity_dsr")
        if signal_p > config.maximum_placebo_p:
            failures.append("signal_placebo")
        if return_p > config.maximum_placebo_p:
            failures.append("return_placebo")
    if pbo > config.maximum_pbo:
        failures.append("candidate_selection_pbo")
    positive_fraction = (
        sum(
            item.path.incremental_return > 0 and item.path.portfolio_excess_return > 0
            for item in stress_results
        )
        / len(stress_results)
        if stress_results
        else 0.0
    )
    report = V50Report(
        V50_VERSION,
        experiment_id,
        snapshot_id,
        composite.snapshot_sha256,
        screening_membership_sha,
        membership_sha,
        tiers_sha,
        len(evidence),
        sum(item.stable for item in evidence),
        selected,
        correlations,
        tuple(stress_results),
        tuple(slice_results),
        positive_fraction,
        cpcv_paths,
        pbo,
        signal_p,
        return_p,
        dsr_probability,
        dsr_skewness,
        dsr_excess_kurtosis,
        prior_inferential_trials + registry.global_trial_count(),
        "DEVELOPMENT_CANDIDATE" if not failures else "NO_DEVELOPMENT_ALPHA",
        tuple(dict.fromkeys(failures)),
        "2022-2024 reused development evidence; requires genuinely new forward data",
    )
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "v5.0-market-wide-search.json").write_text(
        report.to_json() + "\n", encoding="utf-8"
    )
    (output / "v5.0-market-wide-search.zh.md").write_text(
        report.to_markdown("zh") + "\n", encoding="utf-8"
    )
    (output / "v5.0-market-wide-search.en.md").write_text(
        report.to_markdown("en") + "\n", encoding="utf-8"
    )
    return report
