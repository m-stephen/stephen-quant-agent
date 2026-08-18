from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from statistics import mean, stdev

from stephen_quant.evaluation import EvaluationObservation
from stephen_quant.falsification import deflated_sharpe_ratio, run_rank_placebo_fast
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
from stephen_quant.qmt.csv_adapter import _decode

from .price_discovery_lab import _execution_memberships, _load_memberships
from .v4_ohlcv_platform import residualize_panel
from .v41_semantic_alpha import (
    UsageSpec,
    V41Config,
    _anchors,
    _daily_metrics,
    evaluate_usage,
    evaluate_usage_events,
)
from .v44_path_robust_alpha import PathRobustness, summarize_paths
from .v46_orthogonal_search import _ensemble_panel, curated_schemas
from .v50_market_wide_search import (
    YEARS,
    _execution_tiers,
    _incremental_returns,
    _load_tiers,
    _moments,
)

V51_VERSION = "v5.1-frozen-candidate-reliability-audit-1.0.0"
FROZEN_CANDIDATES = (
    "chip_cost_gap_reversal_5_20_20d",
    "flow_price_divergence_20_20d",
)
SIGNAL_VARIANTS = ("raw", "style_residual", "industry_proxy", "style_industry_proxy")
EXECUTION_SCENARIOS = ("standard", "double", "conservative")


@dataclass(frozen=True)
class V51Config:
    data_start: str = "2021-01-01"
    data_end: str = "2024-12-31"
    years: tuple[int, ...] = YEARS
    horizon: int = 20
    breadth: int = 50
    nav: float = 3_000_000.0
    minimum_positive_paths: int = 15
    minimum_dsr: float = 0.95
    maximum_pbo: float = 0.05
    maximum_placebo_p: float = 0.05
    placebo_repetitions: int = 199
    ingested_at: str = "2026-08-18T00:00:00+08:00"
    seed: int = 42

    def validate(self) -> None:
        if (self.data_start, self.data_end) != ("2021-01-01", "2024-12-31"):
            raise ValueError("V5.1 data window is frozen")
        if self.years != YEARS or (self.horizon, self.breadth) != (20, 50):
            raise ValueError("V5.1 years, horizon and breadth are frozen")
        if self.nav != 3_000_000.0 or self.minimum_positive_paths != 15:
            raise ValueError("V5.1 NAV and path gate are frozen")
        if (self.minimum_dsr, self.maximum_pbo, self.maximum_placebo_p) != (0.95, 0.05, 0.05):
            raise ValueError("V5.1 falsification gates are frozen")


@dataclass(frozen=True)
class SourceAudit:
    source: str
    snapshot_sha256: str
    availability_policy: str
    historical_vintage_proven: bool
    status: str


@dataclass(frozen=True)
class AuditCell:
    signal_variant: str
    execution_scenario: str
    annual_rank_ic: tuple[tuple[int, float], ...]
    path: PathRobustness
    capacity_clipped_notional: float
    trial_id: str
    trial_number: int


@dataclass(frozen=True)
class V51Report:
    method_version: str
    experiment_id: str
    snapshot_id: str
    snapshot_sha256: str
    v50_report_sha256: str
    frozen_candidates: tuple[str, ...]
    source_audits: tuple[SourceAudit, ...]
    timing_rows: int
    timing_violations: int
    industry_proxy_status: str
    audit_cells: tuple[AuditCell, ...]
    inherited_pbo_probability: float
    signal_placebo_p: float
    return_placebo_p: float
    dsr_probability: float
    dsr_skewness: float
    dsr_excess_kurtosis: float
    audit_trials: int
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
            "# V5.1 冻结候选可靠性审计" if zh else "# V5.1 Frozen Candidate Reliability Audit",
            "",
            f"**{'结论' if zh else 'Decision'}: `{self.decision}`**",
            "",
            (
                "本报告审计冻结候选，不重新搜索或调参；2022–2024 仍是重复使用的开发证据。"
                if zh
                else "This report audits a frozen candidate without new search or tuning; 2022–2024 remains reused development evidence."
            ),
            "",
            f"- {'审计 Trials' if zh else 'Audit Trials'}: {self.audit_trials}",
            f"- {'累计 Trials' if zh else 'Cumulative Trials'}: {self.recorded_trial_count}",
            f"- {'时间违规' if zh else 'Timing violations'}: {self.timing_violations}/{self.timing_rows}",
            f"- {'继承 PBO' if zh else 'Inherited PBO'}: {self.inherited_pbo_probability:.6f}",
            f"- DSR: {self.dsr_probability:.6f}",
            f"- Placebo: {self.signal_placebo_p:.6f} / {self.return_placebo_p:.6f}",
            f"- {'行业标签' if zh else 'Industry label'}: `{self.industry_proxy_status}`",
            "",
            "## 固定审计网格" if zh else "## Frozen audit grid",
            "",
            "| Signal | Execution | 2022 IC | 2023 IC | 2024 IC | Excess return | Positive paths | Q25 Sharpe | Clipped |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for cell in self.audit_cells:
            yearly = dict(cell.annual_rank_ic)
            lines.append(
                f"| {cell.signal_variant} | {cell.execution_scenario} | {yearly[2022]:.4f} | "
                f"{yearly[2023]:.4f} | {yearly[2024]:.4f} | "
                f"{cell.path.portfolio_excess_return:.2%} | "
                f"{cell.path.positive_return_paths}/{cell.path.paths} | "
                f"{cell.path.lower_quartile_sharpe:.3f} | {cell.capacity_clipped_notional:.2f} |"
            )
        lines.extend(
            [
                "",
                "## 数据与可证伪性" if zh else "## Data and falsifiability",
                "",
                "| Source | Availability | Vintage proof | Status |",
                "|---|---|---:|---|",
            ]
        )
        for item in self.source_audits:
            lines.append(
                f"| {item.source} | {item.availability_policy} | "
                f"{'yes' if item.historical_vintage_proven else 'no'} | {item.status} |"
            )
        lines.extend(
            [
                "",
                f"- {'失败门禁' if zh else 'Failed gates'}: {', '.join(self.failures) or 'none'}",
                f"- {'证据状态' if zh else 'Evidence status'}: {self.evidence_status}",
                "",
            ]
        )
        return "\n".join(lines)


def _execution_config(name: str, config: V51Config) -> V41Config:
    values = {
        "standard": (3.0, 5.0, 5.0, 10.0, 0.05),
        "double": (6.0, 10.0, 10.0, 20.0, 0.05),
        "conservative": (3.0, 5.0, 15.0, 25.0, 0.02),
    }[name]
    return V41Config(
        primary_nav=config.nav,
        commission_bps=values[0],
        sell_tax_bps=values[1],
        slippage_bps=values[2],
        impact_bps=values[3],
        participation_rate=values[4],
        ingested_at=config.ingested_at,
    )


def _tier_value(
    day: str,
    instrument: str,
    dimension: str,
    execution_tiers: dict[str, dict[str, dict[str, frozenset[str]]]],
) -> float | None:
    for value, bucket in (
        (1.0, "large" if dimension == "size" else "high"),
        (0.0, "mid"),
        (-1.0, "small" if dimension == "size" else "low"),
    ):
        if instrument in execution_tiers[day][dimension][bucket]:
            return value
    return None


def _style_controls(
    rows: tuple[EvaluationObservation, ...],
    *,
    by_instrument: dict[str, dict[str, object]],
    calendar: tuple[str, ...],
    execution_tiers: dict[str, dict[str, dict[str, frozenset[str]]]],
) -> tuple[tuple[EvaluationObservation, ...], ...]:
    indices = {day: index for index, day in enumerate(calendar)}
    panels: list[list[EvaluationObservation]] = [[], [], [], []]
    for row in rows:
        day = row.timestamp[:10]
        index = indices[day]
        history = [
            by_instrument[row.instrument].get(calendar[offset])
            for offset in range(max(0, index - 21), index)
        ]
        history = [item for item in history if item is not None]
        if len(history) < 21:
            continue
        closes = [float(item.close) for item in history[-21:]]
        returns = [closes[pos] / closes[pos - 1] - 1 for pos in range(1, len(closes))]
        size = _tier_value(day, row.instrument, "size", execution_tiers)
        liquidity = _tier_value(day, row.instrument, "liquidity", execution_tiers)
        if size is None or liquidity is None or stdev(returns) == 0:
            continue
        values = (size, liquidity, closes[-1] / closes[0] - 1, stdev(returns))
        for panel, value in zip(panels, values, strict=True):
            panel.append(replace(row, factor_value=value))
    return tuple(tuple(panel) for panel in panels)


def _load_industry_labels(
    daily_dir: str | Path,
    *,
    start_date: str,
    end_date: str,
    instruments: frozenset[str],
) -> dict[tuple[str, str], str]:
    labels: dict[tuple[str, str], str] = {}
    for path in select_qd_daily_files(daily_dir, start_date=start_date, end_date=end_date):
        text, _ = _decode(path.read_bytes())
        reader = csv.DictReader(io.StringIO(text, newline=""))
        if (
            not reader.fieldnames
            or "行业" not in reader.fieldnames
            or "代码" not in reader.fieldnames
        ):
            raise ValueError(f"V5.1 daily industry proxy columns missing in {path.name}")
        day = f"{path.stem[:4]}-{path.stem[4:6]}-{path.stem[6:8]}"
        for row in reader:
            instrument = (row.get("代码") or "").strip().upper()
            industry = (row.get("行业") or "").strip()
            if instrument in instruments and industry:
                labels[(day, instrument)] = industry
    return labels


def _industry_demean(
    rows: tuple[EvaluationObservation, ...],
    *,
    labels: dict[tuple[str, str], str],
    calendar: tuple[str, ...],
) -> tuple[EvaluationObservation, ...]:
    indices = {day: index for index, day in enumerate(calendar)}
    grouped: dict[tuple[str, str], list[EvaluationObservation]] = defaultdict(list)
    for row in rows:
        day = row.timestamp[:10]
        index = indices[day]
        if index == 0:
            continue
        industry = labels.get((calendar[index - 1], row.instrument))
        if industry:
            grouped[(day, industry)].append(row)
    output: list[EvaluationObservation] = []
    for key in sorted(grouped):
        cross = grouped[key]
        if len(cross) < 2:
            continue
        center = mean(item.factor_value for item in cross)
        output.extend(replace(item, factor_value=item.factor_value - center) for item in cross)
    return tuple(output)


def _make_trial(
    registry: ExperimentRegistry,
    experiment_id: str,
    variant: str,
    scenario: str,
    seed: int,
) -> tuple[str, int]:
    return registry.create_trial(
        TrialSpec(
            experiment_id,
            "v5.1_frozen_audit_grid",
            "+".join(FROZEN_CANDIDATES),
            json.dumps({"signal_variant": variant, "execution_scenario": scenario}, sort_keys=True),
            seed,
            "2020-01-01",
            "2022-12-31",
            "2023-01-01",
            "2023-12-31",
            "2024-01-01",
            "2024-12-31",
        )
    )


def run_v51_candidate_audit(
    daily_dir: str | Path,
    membership_path: str | Path,
    tiers_path: str | Path,
    v50_report_path: str | Path,
    *,
    auction_dir: str | Path,
    fund_flow_dir: str | Path,
    chip_dir: str | Path,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    config: V51Config | None = None,
    prior_inferential_trials: int = 1206,
) -> V51Report:
    config = config or V51Config()
    config.validate()
    if prior_inferential_trials < 1206:
        raise ValueError("V5.1 cannot discard the 1,206 pre-existing inferential Trials")
    v50_path = Path(v50_report_path).expanduser().resolve()
    v50_bytes = v50_path.read_bytes()
    v50 = json.loads(v50_bytes)
    selected = tuple(item["candidate_id"] for item in v50["selected_candidates"])
    if selected != FROZEN_CANDIDATES:
        raise ValueError("V5.1 V5.0 candidate identity differs from the frozen protocol")

    memberships, membership_sha = _load_memberships(membership_path, 10_000)
    tiers, tiers_sha = _load_tiers(tiers_path)
    if set(memberships) != set(tiers):
        raise ValueError("V5.1 membership and tier dates differ")
    instruments = tuple(sorted({item for members in memberships.values() for item in members}))
    daily_root = Path(daily_dir).expanduser().resolve()
    daily_files = select_qd_daily_files(
        daily_root, start_date=config.data_start, end_date=config.data_end
    )
    daily_manifest = build_selected_files_snapshot_manifest(daily_root, daily_files)
    daily = load_qd_daily_directory(
        daily_root,
        start_date=config.data_start,
        end_date=config.data_end,
        instruments=instruments,
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
                instruments=instruments,
            ),
        )
        alternatives[kind] = dataset.observations
        alternative_hashes[kind] = dataset.audit.source_sha256
    composite = build_composite_snapshot_manifest(
        {
            "qd_daily": daily_manifest.snapshot_sha256,
            "market_wide_membership": membership_sha,
            "market_wide_tiers": tiers_sha,
            "v5_report": hashlib.sha256(v50_bytes).hexdigest(),
            **alternative_hashes,
        }
    )
    snapshot_id = registry.register_snapshot(
        composite,
        vendor_version=V51_VERSION,
        notes="Frozen V5.0 candidate audit; 2022-2024 reused development evidence",
    )
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            "V5.1 frozen candidate reliability audit",
            "The frozen V5.0 candidate should survive attribution, path and execution stress.",
            snapshot_id,
            code_version,
            json.dumps({"version": V51_VERSION, "config": asdict(config)}, sort_keys=True),
        )
    )

    calendar = tuple(sorted({item.trade_date for item in daily.bars}))
    by_instrument: dict[str, dict[str, object]] = defaultdict(dict)
    for bar in daily.bars:
        by_instrument[bar.instrument][bar.trade_date] = bar
    execution_members = _execution_memberships(memberships, calendar)
    execution_tiers = _execution_tiers(tiers, calendar)
    anchors = tuple(
        row
        for year in YEARS
        for row in _anchors(
            year=year,
            horizon=config.horizon,
            calendar=calendar,
            bars=by_instrument,
            execution_members=execution_members,
        )
    )
    schemas = {schema.schema_id: schema for _, schema in curated_schemas()}
    panels = []
    for candidate_id in FROZEN_CANDIDATES:
        schema = schemas[candidate_id]
        required = {
            source: alternatives[source.removeprefix("qd_")]
            for source in schema.data_sources
            if source != "qd_daily"
        }
        built = build_multisource_factor_observations(
            daily.bars, required, schema.compile(), anchors
        )
        panels.append(
            tuple(
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
        )
    raw = tuple(
        row
        for year in YEARS
        for row in _ensemble_panel(
            tuple(
                tuple(item for item in panel if item.timestamp.startswith(f"{year}-"))
                for panel in panels
            ),
            year=year,
        )
    )
    timing_violations = sum(item.factor_available_at >= item.label_start_at for item in raw)
    style = residualize_panel(
        raw,
        _style_controls(
            raw,
            by_instrument=by_instrument,
            calendar=calendar,
            execution_tiers=execution_tiers,
        ),
    )
    labels = _load_industry_labels(
        daily_root,
        start_date=config.data_start,
        end_date=config.data_end,
        instruments=frozenset(instruments),
    )
    variants = {
        "raw": raw,
        "style_residual": style,
        "industry_proxy": _industry_demean(raw, labels=labels, calendar=calendar),
        "style_industry_proxy": _industry_demean(style, labels=labels, calendar=calendar),
    }

    cells: list[AuditCell] = []
    raw_incremental_returns: tuple[float, ...] | None = None
    for variant in SIGNAL_VARIANTS:
        rows = variants[variant]
        annual_ic = tuple(
            (
                year,
                mean(
                    item.rank_ic
                    for item in _daily_metrics(
                        tuple(row for row in rows if row.timestamp.startswith(f"{year}-"))
                    )
                ),
            )
            for year in YEARS
        )
        for scenario in EXECUTION_SCENARIOS:
            usage_config = _execution_config(scenario, config)
            all_events, all_controls = [], []
            annual_returns, drawdowns, sharpes = [], [], []
            clipped = 0.0
            for year in YEARS:
                yearly = tuple(row for row in rows if row.timestamp.startswith(f"{year}-"))
                spec = UsageSpec("BUY", config.breadth, "all")
                events, clipped_year = evaluate_usage_events(
                    yearly,
                    yearly,
                    spec,
                    horizon=config.horizon,
                    nav=config.nav,
                    bars=by_instrument,
                    calendar=calendar,
                    regimes={},
                    config=usage_config,
                )
                controls, _ = evaluate_usage_events(
                    yearly,
                    yearly,
                    UsageSpec("AVOID", 0, "all"),
                    horizon=config.horizon,
                    nav=config.nav,
                    bars=by_instrument,
                    calendar=calendar,
                    regimes={},
                    config=usage_config,
                )
                score, _ = evaluate_usage(
                    f"v51_{variant}_{scenario}",
                    yearly,
                    yearly,
                    spec,
                    year=year,
                    horizon=config.horizon,
                    nav=config.nav,
                    bars=by_instrument,
                    calendar=calendar,
                    regimes={},
                    config=usage_config,
                )
                all_events.extend(events)
                all_controls.extend(controls)
                clipped += clipped_year
                annual_returns.append(score.cumulative_excess_return)
                drawdowns.append(score.maximum_drawdown)
                sharpes.append(score.excess_sharpe)
            path = summarize_paths(
                YEARS[0],
                tuple(all_events),
                tuple(all_controls),
                horizon=config.horizon,
                portfolio_sharpe=mean(sharpes),
                portfolio_return=math.prod(1 + item for item in annual_returns) - 1,
                portfolio_drawdown=min(drawdowns),
            )
            trial_id, trial_number = _make_trial(
                registry, experiment_id, variant, scenario, config.seed
            )
            cell = AuditCell(variant, scenario, annual_ic, path, clipped, trial_id, trial_number)
            registry.record_trial_result(trial_id, json.dumps(asdict(cell), sort_keys=True))
            cells.append(cell)
            if variant == "raw" and scenario == "standard":
                raw_incremental_returns = _incremental_returns(all_events, all_controls)

    if raw_incremental_returns is None:
        raise AssertionError("V5.1 raw standard return series missing")
    skewness, excess_kurtosis = _moments(raw_incremental_returns)
    raw_standard = next(
        item
        for item in cells
        if (item.signal_variant, item.execution_scenario) == ("raw", "standard")
    )
    dsr = deflated_sharpe_ratio(
        observed_sharpe=raw_standard.path.incremental_daily_sharpe / math.sqrt(252),
        trial_sharpes=[item.path.incremental_daily_sharpe / math.sqrt(252) for item in cells],
        recorded_trial_count=prior_inferential_trials + len(cells),
        observations=len(_daily_metrics(raw)),
        skewness=skewness,
        excess_kurtosis=excess_kurtosis,
    ).probability
    signal_p = run_rank_placebo_fast(
        raw,
        horizon="20d",
        direction=1,
        method="signal_shuffle",
        seed=config.seed,
        repetitions=config.placebo_repetitions,
        min_cross_section=10,
    ).empirical_p_value
    return_p = run_rank_placebo_fast(
        raw,
        horizon="20d",
        direction=1,
        method="return_permutation",
        seed=config.seed,
        repetitions=config.placebo_repetitions,
        min_cross_section=10,
    ).empirical_p_value
    inherited_pbo = float(v50["pbo_probability"])
    source_audits = (
        SourceAudit(
            "qd_daily", daily_manifest.snapshot_sha256, "prior close and next open", True, "PASS"
        ),
        SourceAudit(
            "qd_fund_flow", alternative_hashes["fund_flow"], "end of day + next open", True, "PASS"
        ),
        SourceAudit(
            "qd_chip", alternative_hashes["chip"], "end of day + next open", False, "BLOCKED"
        ),
        SourceAudit(
            "daily_industry_proxy",
            daily_manifest.snapshot_sha256,
            "prior-file label",
            False,
            "DIAGNOSTIC_ONLY",
        ),
    )
    failures: list[str] = []
    economic_failures: list[str] = []
    if timing_violations:
        failures.append("feature_timing_violation")
    raw_conservative = next(
        item
        for item in cells
        if (item.signal_variant, item.execution_scenario) == ("raw", "conservative")
    )
    style_standard = next(
        item
        for item in cells
        if (item.signal_variant, item.execution_scenario) == ("style_residual", "standard")
    )
    for label, cell in (("raw_standard", raw_standard), ("raw_conservative", raw_conservative)):
        if cell.path.incremental_return <= 0 or cell.path.portfolio_excess_return <= 0:
            economic_failures.append(f"{label}_return")
        if cell.path.positive_return_paths < config.minimum_positive_paths:
            economic_failures.append(f"{label}_path_robustness")
    style_ic = dict(style_standard.annual_rank_ic)
    if style_standard.path.incremental_return <= 0 or min(style_ic[2023], style_ic[2024]) <= 0:
        economic_failures.append("style_attribution")
    if any(item.capacity_clipped_notional > 0 for item in cells):
        economic_failures.append("capacity_clipping")
    failures.extend(economic_failures)
    if inherited_pbo > config.maximum_pbo:
        failures.append("inherited_candidate_selection_pbo")
    if signal_p > config.maximum_placebo_p:
        failures.append("signal_placebo")
    if return_p > config.maximum_placebo_p:
        failures.append("return_placebo")
    if dsr < config.minimum_dsr:
        failures.append("multiplicity_dsr")
    failures.append("chip_revision_provenance_unverified")
    decision = (
        "REJECT_CANDIDATE"
        if economic_failures
        else "FORWARD_CANDIDATE_WITH_BLOCKERS"
        if failures
        else "RELIABLE_ALPHA_CANDIDATE"
    )
    report = V51Report(
        V51_VERSION,
        experiment_id,
        snapshot_id,
        composite.snapshot_sha256,
        hashlib.sha256(v50_bytes).hexdigest(),
        FROZEN_CANDIDATES,
        source_audits,
        len(raw),
        timing_violations,
        "B_CURRENT_LABEL_PROXY_DIAGNOSTIC_ONLY",
        tuple(cells),
        inherited_pbo,
        signal_p,
        return_p,
        dsr,
        skewness,
        excess_kurtosis,
        len(cells),
        prior_inferential_trials + len(cells),
        decision,
        tuple(dict.fromkeys(failures)),
        "Reused 2022-2024 evidence; not deployment proof; genuinely new forward data required",
    )
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "v5.1-candidate-audit.json").write_text(report.to_json() + "\n", encoding="utf-8")
    for language in ("zh", "en"):
        (output / f"v5.1-candidate-audit.{language}.md").write_text(
            report.to_markdown(language) + "\n", encoding="utf-8"
        )
    return report
