from __future__ import annotations

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
    AuditThresholds,
    FalsificationLineage,
    build_alpha_court_report,
    deflated_sharpe_ratio,
    probability_of_backtest_overfitting,
    run_placebo,
)
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import (
    build_composite_snapshot_manifest,
    build_selected_files_snapshot_manifest,
)
from stephen_quant.qmt import (
    QdAlternativeConfig,
    QmtDailyBar,
    build_multisource_factor_observations,
    load_qd_alternative_directory,
    load_qd_daily_directory,
    select_qd_daily_files,
)

from .price_discovery_lab import _execution_memberships, _load_memberships
from .v41_semantic_alpha import UsageEvent, UsageSpec, V41Config, _anchors, evaluate_usage_events
from .v46_orthogonal_search import _ensemble_panel
from .v47_low_turnover_alpha import (
    AUCTION_SCHEMA_ID,
    BUFFER_RANKS,
    FLOW_SCHEMA_ID,
    SIGNAL_STRUCTURES,
    GridEvidence,
    TurnoverAttribution,
    _path,
    _selected_schemas,
    evaluate_buffered_avoid_events,
    v46_trial_sharpes,
)

V48_VERSION = "v4.8-sealed-alpha-court-1.0.0"
FROZEN_START = "2026-01-01"
FROZEN_END = "2026-08-16"
FROZEN_CANDIDATE_COMMIT = "30de08a7edd0ded2b3bd8977b505829e18b64582"


@dataclass(frozen=True)
class V48Config:
    data_start: str = "2021-01-01"
    holdout_start: str = FROZEN_START
    holdout_end: str = FROZEN_END
    universe_top_n: int = 50
    horizon: int = 20
    breadth: int = 10
    buffer_ranks: int = 10
    nav: float = 3_000_000.0
    commission_bps: float = 3.0
    sell_tax_bps: float = 5.0
    slippage_bps: float = 5.0
    impact_bps: float = 10.0
    participation_rate: float = 0.05
    minimum_positive_paths: int = 15
    minimum_median_path_sharpe: float = 0.0
    maximum_placebo_p: float = 0.05
    minimum_dsr: float = 0.95
    maximum_pbo: float = 0.05
    placebo_repetitions: int = 199
    ingested_at: str = "2026-08-18T00:00:00+08:00"
    seed: int = 42

    def validate(self) -> None:
        if (self.holdout_start, self.holdout_end) != (FROZEN_START, FROZEN_END):
            raise ValueError("V4.8 holdout dates are sealed")
        if (self.horizon, self.breadth, self.buffer_ranks) != (20, 10, 10):
            raise ValueError("V4.8 execution identity is frozen")
        if self.nav != 3_000_000.0:
            raise ValueError("V4.8 NAV is frozen")


@dataclass(frozen=True)
class V48Report:
    method_version: str
    candidate_fingerprint: str
    candidate_commit: str
    experiment_id: str
    snapshot_id: str
    snapshot_sha256: str
    standard: GridEvidence
    double_cost: GridEvidence
    signal_placebo_p: float
    return_placebo_p: float
    dsr_probability: float
    dsr_skewness: float
    dsr_excess_kurtosis: float
    pbo_probability: float
    pbo_manifest_sha256: str
    pbo_configurations: int
    pbo_paths: int
    recorded_trial_count: int
    court_failures: tuple[str, ...]
    decision: str
    evidence_status: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        lines = [
            "# V4.8 封存候选 Alpha Court" if zh else "# V4.8 Sealed Candidate Alpha Court",
            "",
            f"**{'结论' if zh else 'Decision'}: `{self.decision}`**",
            "",
            f"- {'候选指纹' if zh else 'Candidate fingerprint'}: `{self.candidate_fingerprint}`",
            f"- {'封存窗口' if zh else 'Sealed window'}: {FROZEN_START} — {FROZEN_END}",
            f"- DSR: {self.dsr_probability:.6g}",
            (
                f"- {'DSR 偏度/超额峰度' if zh else 'DSR skew/excess kurtosis'}: "
                f"{self.dsr_skewness:.6g} / {self.dsr_excess_kurtosis:.6g}"
            ),
            f"- PBO: {self.pbo_probability:.6g}",
            (
                f"- {'置换 p 值（信号/收益）' if zh else 'Placebo p-values (signal/return)'}: "
                f"{self.signal_placebo_p:.6g} / {self.return_placebo_p:.6g}"
            ),
            "",
            "| Cost | Full excess | Sharpe | Increment | Positive paths | Median / Q25 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for label, item in (("1x", self.standard), ("2x", self.double_cost)):
            path = item.combined
            lines.append(
                f"| {label} | {path.portfolio_excess_return:.2%} | "
                f"{path.portfolio_excess_sharpe:.4f} | {path.incremental_return:.2%} | "
                f"{path.positive_return_paths}/20 | {path.median_sharpe:.4f} / "
                f"{path.lower_quartile_sharpe:.4f} |"
            )
        lines.extend(
            [
                "",
                (
                    f"- {'失败项' if zh else 'Failed gates'}: "
                    f"{', '.join(self.court_failures) or ('无' if zh else 'none')}"
                ),
                f"- {'证据状态' if zh else 'Evidence status'}: {self.evidence_status}",
                "",
            ]
        )
        return "\n".join(lines)


def _fingerprint() -> str:
    payload = {
        "commit": FROZEN_CANDIDATE_COMMIT,
        "signals": [FLOW_SCHEMA_ID, AUCTION_SCHEMA_ID],
        "combination": "equal_percentile_rank",
        "usage": "AVOID",
        "breadth": 10,
        "buffer_ranks": 10,
        "horizon": 20,
        "nav": 3_000_000,
        "holdout": [FROZEN_START, FROZEN_END],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def v47_trial_sharpes(prior_registry: ExperimentRegistry) -> tuple[float, ...]:
    values = []
    with prior_registry.connect() as conn:
        rows = conn.execute(
            "SELECT model_name, result_json FROM trials ORDER BY created_at, trial_number"
        ).fetchall()
    for row in rows:
        if str(row[0]) != "v4.7_predeclared_low_turnover_grid" or row[1] is None:
            continue
        result = json.loads(str(row[1]))
        values.append(float(result["combined"]["incremental_daily_sharpe"]) / math.sqrt(252))
    if len(values) != 12:
        raise ValueError(f"V4.8 requires the complete 12-Trial V4.7 ledger; found {len(values)}")
    return tuple(values)


def _increment_by_day(
    events: tuple[UsageEvent, ...], controls: tuple[UsageEvent, ...]
) -> dict[str, float]:
    candidate = {(item.day, item.offset): item.excess_return for item in events}
    control = {(item.day, item.offset): item.excess_return for item in controls}
    if set(candidate) != set(control):
        raise ValueError("candidate/control grids differ in V4.8 PBO")
    return {day: candidate[(day, offset)] - control[(day, offset)] for day, offset in candidate}


def _moments(values: tuple[float, ...]) -> tuple[float, float]:
    if len(values) < 4:
        raise ValueError("V4.8 DSR moments require at least four observations")
    center = mean(values)
    variance = mean((item - center) ** 2 for item in values)
    if variance <= 0:
        raise ValueError("V4.8 DSR moments require non-zero variance")
    skewness = mean((item - center) ** 3 for item in values) / variance**1.5
    excess_kurtosis = mean((item - center) ** 4 for item in values) / variance**2 - 3
    return skewness, excess_kurtosis


def _execution_pbo(
    panels: dict[str, tuple[EvaluationObservation, ...]],
    *,
    bars: dict[str, dict[str, QmtDailyBar]],
    calendar: tuple[str, ...],
    usage: V41Config,
    snapshot_id: str,
    experiment_id: str,
    trial_id: str,
    code_version: str,
) -> object:
    scores = {}
    label_rows = {}
    for structure in SIGNAL_STRUCTURES:
        rows = tuple(row for row in panels[structure] if "2022-01-01" <= row.timestamp[:10] <= "2025-12-31")
        controls, _ = evaluate_usage_events(
            rows, rows, UsageSpec("AVOID", 0, "all"), horizon=20, nav=3_000_000,
            bars=bars, calendar=calendar, regimes={}, config=usage,
        )
        for buffer_ranks in BUFFER_RANKS:
            events, _ = evaluate_buffered_avoid_events(
                rows, breadth=10, buffer_ranks=buffer_ranks, horizon=20, nav=3_000_000,
                bars=bars, calendar=calendar, config=usage,
            )
            key = f"{structure}:buffer{buffer_ranks}"
            scores[key] = _increment_by_day(events, controls)
        for row in rows:
            label_rows.setdefault(row.timestamp[:10], row)
    common = sorted(set.intersection(*(set(item) for item in scores.values())))
    samples = tuple(
        SampleInterval(
            sample_id=day,
            instrument="CROSS_SECTION",
            feature_at=label_rows[day].factor_available_at,
            label_start_at=label_rows[day].label_start_at,
            label_end_at=label_rows[day].label_end_at,
        )
        for day in common
    )
    manifest = generate_cpcv_manifest(
        samples,
        SplitLineage(snapshot_id, experiment_id, trial_id, code_version),
        n_groups=5,
        n_test_groups=2,
        embargo=timedelta(days=20),
    )
    findings = audit_manifest(manifest, samples)
    fold_by_id = {fold.fold_id: fold for fold in manifest.folds}
    path_scores = {key: {} for key in scores}
    for path in manifest.paths:
        test_days = []
        for segment in path.segments:
            test_days.extend(fold_by_id[segment.fold_id].test_ids)
        unique_days = sorted(set(test_days))
        for key, values in scores.items():
            path_scores[key][path.path_id] = mean(values[day] for day in unique_days)
    return probability_of_backtest_overfitting(manifest, path_scores, findings)


def _trial(
    registry: ExperimentRegistry,
    experiment_id: str,
    multiplier: float,
    fingerprint: str,
    seed: int,
) -> tuple[str, int]:
    return registry.create_trial(
        TrialSpec(
            experiment_id,
            "v4.8_one_time_sealed_alpha_court",
            fingerprint,
            json.dumps({"cost_multiplier": multiplier}, sort_keys=True),
            seed,
            "2022-01-01",
            "2025-12-31",
            FROZEN_START,
            FROZEN_END,
            FROZEN_START,
            FROZEN_END,
        )
    )


def run_v48_sealed_alpha_court(
    daily_dir: str | Path,
    membership_path: str | Path,
    *,
    auction_dir: str | Path,
    fund_flow_dir: str | Path,
    registry: ExperimentRegistry,
    v46_registry: ExperimentRegistry,
    v47_registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    config: V48Config | None = None,
    prior_inferential_trials: int = 1101,
) -> V48Report:
    config = config or V48Config()
    config.validate()
    fingerprint = _fingerprint()
    prior_sharpes = (*v46_trial_sharpes(v46_registry), *v47_trial_sharpes(v47_registry))
    memberships, membership_sha = _load_memberships(membership_path, config.universe_top_n)
    instruments = tuple(sorted({item for members in memberships.values() for item in members}))
    root = Path(daily_dir).expanduser().resolve()
    files = select_qd_daily_files(root, start_date=config.data_start, end_date=config.holdout_end)
    daily_manifest = build_selected_files_snapshot_manifest(root, files)
    daily = load_qd_daily_directory(
        root, start_date=config.data_start, end_date=config.holdout_end, instruments=instruments
    )
    alternatives = {}
    hashes = {}
    for kind, source in (("auction", auction_dir), ("fund_flow", fund_flow_dir)):
        dataset = load_qd_alternative_directory(
            source,
            QdAlternativeConfig(
                source_kind=kind,  # type: ignore[arg-type]
                start_date=config.data_start,
                end_date=config.holdout_end,
                ingested_at=config.ingested_at,
                instruments=instruments,
            ),
        )
        alternatives[kind] = dataset.observations
        hashes[kind] = dataset.audit.source_sha256
    composite = build_composite_snapshot_manifest(
        {"qd_daily": daily_manifest.snapshot_sha256, "dynamic_universe": membership_sha, **hashes}
    )
    snapshot_id = registry.register_snapshot(
        composite, vendor_version=V48_VERSION, notes="one-time sealed 2026 candidate audit"
    )
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            "V4.8 sealed candidate Alpha Court",
            "The V4.7 frozen candidate should survive never-selected 2026 evidence.",
            snapshot_id,
            code_version,
            json.dumps({"version": V48_VERSION, "config": asdict(config), "fingerprint": fingerprint}, sort_keys=True),
        )
    )
    calendar = tuple(sorted({item.trade_date for item in daily.bars}))
    bars: dict[str, dict[str, QmtDailyBar]] = defaultdict(dict)
    for bar in daily.bars:
        bars[bar.instrument][bar.trade_date] = bar
    execution_members = _execution_memberships(memberships, calendar)
    anchors = tuple(
        row
        for year in (2022, 2023, 2024, 2025, 2026)
        for row in _anchors(
            year=year, horizon=20, calendar=calendar, bars=bars,
            execution_members=execution_members,
        )
    )
    flow_schema, auction_schema = _selected_schemas()
    raw_panels = {}
    for schema, source_kind in ((flow_schema, "fund_flow"), (auction_schema, "auction")):
        built = build_multisource_factor_observations(
            daily.bars, {f"qd_{source_kind}": alternatives[source_kind]}, schema.compile(), anchors
        )
        raw_panels[schema.schema_id] = tuple(
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
            for row in built if row.eligible
        )
    ensemble = tuple(
        row
        for year in (2022, 2023, 2024, 2025, 2026)
        for row in _ensemble_panel(
            (
                tuple(item for item in raw_panels[FLOW_SCHEMA_ID] if item.timestamp.startswith(f"{year}-")),
                tuple(item for item in raw_panels[AUCTION_SCHEMA_ID] if item.timestamp.startswith(f"{year}-")),
            ), year=year,
        )
    )
    panels = {"flow_only": raw_panels[FLOW_SCHEMA_ID], "flow_auction_ensemble": ensemble}
    base_usage = V41Config(
        primary_nav=config.nav,
        commission_bps=config.commission_bps,
        sell_tax_bps=config.sell_tax_bps,
        slippage_bps=config.slippage_bps,
        impact_bps=config.impact_bps,
        participation_rate=config.participation_rate,
        ingested_at=config.ingested_at,
    )
    holdout = tuple(
        row for row in ensemble if config.holdout_start <= row.timestamp[:10] <= config.holdout_end
    )
    if len({row.timestamp[:10] for row in holdout}) < 80:
        raise ValueError("sealed V4.8 holdout has insufficient dates")
    evidence = []
    raw_sharpes = []
    incremental_series = []
    for multiplier in (1.0, 2.0):
        usage = replace(
            base_usage,
            commission_bps=config.commission_bps * multiplier,
            sell_tax_bps=config.sell_tax_bps * multiplier,
            slippage_bps=config.slippage_bps * multiplier,
            impact_bps=config.impact_bps * multiplier,
        )
        events, clipped = evaluate_buffered_avoid_events(
            holdout, breadth=10, buffer_ranks=10, horizon=20, nav=config.nav,
            bars=bars, calendar=calendar, config=usage,
        )
        controls, _ = evaluate_usage_events(
            holdout, holdout, UsageSpec("AVOID", 0, "all"), horizon=20, nav=config.nav,
            bars=bars, calendar=calendar, regimes={}, config=usage,
        )
        path = _path(2026, events, controls, 20)
        incremental = _increment_by_day(events, controls)
        trial = _trial(registry, experiment_id, multiplier, fingerprint, config.seed)
        attribution = TurnoverAttribution(
            mean(item.turnover for item in events),
            sum(item.cost_rate for item in events),
            math.prod(1 + item.excess_return + item.cost_rate for item in events) - 1,
            math.prod(1 + item.excess_return for item in events) - 1,
        )
        item = GridEvidence(
            "flow_auction_ensemble", 10, multiplier, path, (path,), attribution,
            clipped, trial[0], trial[1],
        )
        registry.record_trial_result(trial[0], json.dumps(asdict(item), sort_keys=True))
        evidence.append(item)
        raw_sharpes.append(path.incremental_daily_sharpe / math.sqrt(252))
        incremental_series.append(tuple(incremental[day] for day in sorted(incremental)))
    if registry.global_trial_count() != 2:
        raise AssertionError("V4.8 must contain exactly two sealed stress Trials")
    signal_placebo = run_placebo(
        holdout, horizon="20d", direction=1, method="signal_shuffle", seed=config.seed,
        repetitions=config.placebo_repetitions, min_cross_section=10,
    )
    return_placebo = run_placebo(
        holdout, horizon="20d", direction=1, method="return_permutation", seed=config.seed,
        repetitions=config.placebo_repetitions, min_cross_section=10,
    )
    recorded = prior_inferential_trials + registry.global_trial_count()
    skewness, excess_kurtosis = _moments(incremental_series[0])
    dsr = deflated_sharpe_ratio(
        observed_sharpe=raw_sharpes[0],
        trial_sharpes=(*prior_sharpes, *raw_sharpes),
        recorded_trial_count=recorded,
        observations=len({row.timestamp[:10] for row in holdout}),
        skewness=skewness,
        excess_kurtosis=excess_kurtosis,
    )
    pbo = _execution_pbo(
        panels, bars=bars, calendar=calendar, usage=base_usage, snapshot_id=snapshot_id,
        experiment_id=experiment_id, trial_id=evidence[0].trial_id, code_version=code_version,
    )
    official = build_alpha_court_report(
        FalsificationLineage(
            fingerprint, V48_VERSION, snapshot_id, experiment_id, evidence[0].trial_id, code_version
        ),
        signal_placebo,
        return_placebo,
        dsr,
        pbo,
        recorded_trial_count=recorded,
        thresholds=AuditThresholds(config.maximum_placebo_p, config.minimum_dsr, config.maximum_pbo),
    )
    failures = []
    for label, item in (("standard", evidence[0]), ("double_cost", evidence[1])):
        path = item.combined
        if path.portfolio_excess_return <= 0 or path.incremental_return <= 0:
            failures.append(f"{label}_return")
        if path.positive_return_paths < config.minimum_positive_paths:
            failures.append(f"{label}_path_count")
        if path.median_sharpe < config.minimum_median_path_sharpe:
            failures.append(f"{label}_median_path_sharpe")
    failures.extend(name for name, passed in official.decision.checks if not passed)
    report = V48Report(
        V48_VERSION, fingerprint, FROZEN_CANDIDATE_COMMIT, experiment_id, snapshot_id,
        composite.snapshot_sha256, evidence[0], evidence[1],
        signal_placebo.empirical_p_value, return_placebo.empirical_p_value,
        dsr.probability, skewness, excess_kurtosis,
        pbo.probability, pbo.split_manifest_sha256,
        pbo.configurations, pbo.paths, recorded, tuple(failures),
        "PASS_ALPHA_COURT" if not failures else "REJECT_ALPHA_COURT",
        "one-time never-selected 2026 holdout; no tuning permitted after reveal",
    )
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "v4.8-sealed-alpha-court.json").write_text(report.to_json() + "\n", encoding="utf-8")
    (output / "v4.8-sealed-alpha-court.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (output / "v4.8-sealed-alpha-court.en.md").write_text(report.to_markdown("en"), encoding="utf-8")
    (output / "v4.8-official-alpha-court.json").write_text(official.to_json() + "\n", encoding="utf-8")
    return report
