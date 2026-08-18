from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from stephen_quant.discovery import FactorSchema, v43_sparse_domain_inverse_plan
from stephen_quant.evaluation import EvaluationObservation
from stephen_quant.falsification import deflated_sharpe_ratio
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
from .v41_semantic_alpha import UsageScore, UsageSpec, V41Config, _anchors, evaluate_usage

V43_CONVERSION_VERSION = "v4.3-ic-to-return-conversion-1.0.0"
FROZEN_SIGNAL_IDS = (
    "chip_concentrated_momentum_5_inverse_20_20d",
    "chip_cost_band_compression_5_20_inverse_20_20d",
    "chip_cost_basis_momentum_confirmation_5_inverse_20_20d",
    "chip_win_rate_acceleration_5_20_inverse_20_20d",
    "limit_up_persistence_20_inverse_20_20d",
    "limit_up_seal_strength_5_inverse_20_20d",
)
FROZEN_SIGNAL_SET_SHA256 = hashlib.sha256("\n".join(FROZEN_SIGNAL_IDS).encode()).hexdigest()


@dataclass(frozen=True)
class ConversionConfig:
    data_start: str = "2021-01-01"
    selection_year: int = 2022
    confirmation_year: int = 2023
    unopened_final_year: int = 2024
    horizon: int = 20
    universe_top_n: int = 50
    usages: tuple[str, ...] = ("BUY", "AVOID")
    breadths: tuple[int, ...] = (5, 10, 20)
    primary_nav: float = 3_000_000.0
    commission_bps: float = 3.0
    sell_tax_bps: float = 5.0
    slippage_bps: float = 5.0
    impact_bps: float = 10.0
    participation_rate: float = 0.05
    minimum_selection_sharpe: float = 0.50
    minimum_confirmation_sharpe: float = 0.50
    maximum_confirmation_drawdown: float = 0.25
    minimum_dsr: float = 0.95
    ingested_at: str = "2026-08-18T00:00:00+08:00"
    seed: int = 42

    def validate(self) -> None:
        if (self.selection_year, self.confirmation_year, self.unopened_final_year) != (
            2022,
            2023,
            2024,
        ):
            raise ValueError("conversion windows are frozen to 2022/2023/2024")
        if self.usages != ("BUY", "AVOID") or self.breadths != (5, 10, 20):
            raise ValueError("conversion mapping identities are frozen")
        if self.horizon != 20 or self.primary_nav != 3_000_000.0:
            raise ValueError("conversion horizon and primary NAV are frozen")


@dataclass(frozen=True)
class MappingResult:
    candidate_id: str
    usage: str
    breadth: int
    year: int
    excess_sharpe: float
    excess_return: float
    maximum_drawdown: float
    turnover: float
    total_cost_rate: float
    active_days: int
    trial_id: str
    trial_number: int


@dataclass(frozen=True)
class V43ConversionReport:
    method_version: str
    experiment_id: str
    snapshot_id: str
    snapshot_sha256: str
    frozen_signal_set_sha256: str
    selection_trials: int
    selected_mapping: MappingResult
    confirmation: MappingResult
    dsr_probability: float
    recorded_trial_count: int
    confirmation_window_opened: bool
    final_window_opened: bool
    decision: str
    failures: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        lines = [
            "# V4.3 IC 到收益转换报告" if zh else "# V4.3 IC-to-return Conversion Report",
            "",
            f"**{'结论' if zh else 'Decision'}: `{self.decision}`**",
            "",
            f"- {'选择期映射 Trials' if zh else 'Selection mapping Trials'}: {self.selection_trials}",
            f"- {'全局记录 Trials' if zh else 'Global recorded Trials'}: {self.recorded_trial_count}",
            f"- DSR: {self.dsr_probability:.6f}",
            f"- {'2023 已打开' if zh else '2023 opened'}: {self.confirmation_window_opened}",
            f"- {'2024 已打开' if zh else '2024 opened'}: {self.final_window_opened}",
            "",
            "| Window | Candidate | Usage | Breadth | Sharpe | Excess return | Drawdown |",
            "|---|---|---|---:|---:|---:|---:|",
        ]
        for label, item in (("2022 selection", self.selected_mapping), ("2023 confirmation", self.confirmation)):
            lines.append(
                f"| {label} | `{item.candidate_id}` | {item.usage} | {item.breadth} | "
                f"{item.excess_sharpe:.4f} | {item.excess_return:.2%} | {item.maximum_drawdown:.2%} |"
            )
        lines.extend(
            [
                "",
                f"- {'失败门禁' if zh else 'Failed gates'}: {', '.join(self.failures) or ('无' if zh else 'none')}",
                "",
            ]
        )
        return "\n".join(lines)


def select_mapping(results: tuple[MappingResult, ...]) -> MappingResult:
    if not results or any(item.year != 2022 for item in results):
        raise ValueError("mapping selection accepts 2022 results only")
    if any(
        not all(
            math.isfinite(value)
            for value in (item.excess_sharpe, item.excess_return, item.maximum_drawdown)
        )
        or item.active_days < 1
        for item in results
    ):
        raise ValueError("mapping selection requires finite results with active observations")
    return max(
        results,
        key=lambda item: (
            item.excess_sharpe,
            item.excess_return,
            -item.turnover,
            item.candidate_id,
            item.usage,
            item.breadth,
        ),
    )


def _schemas() -> dict[str, FactorSchema]:
    rendered = {
        template.render(window=20, horizon="20d").schema_id: template.render(
            window=20, horizon="20d"
        )
        for template in v43_sparse_domain_inverse_plan().templates
    }
    missing = set(FROZEN_SIGNAL_IDS) - set(rendered)
    if missing:
        raise ValueError(f"frozen V4.3 signal set is not reproducible: {sorted(missing)}")
    return {key: rendered[key] for key in FROZEN_SIGNAL_IDS}


def _panel(
    schema: FactorSchema,
    *,
    year: int,
    bars: tuple[QmtDailyBar, ...],
    alternatives: dict[str, tuple],
    anchors: tuple,
) -> tuple[EvaluationObservation, ...]:
    built = build_multisource_factor_observations(
        bars,
        alternatives,
        schema.compile(),
        anchors,
    )
    return tuple(
        EvaluationObservation(
            timestamp=row.execution_at,
            instrument=row.instrument,
            factor_value=schema.direction * row.signal,
            factor_available_at=row.signal_available_at,
            label_start_at=row.execution_at,
            label_end_at=row.return_end_at,
            forward_return=row.forward_return,
            horizon="20d",
            subperiod=str(year),
            regime="unspecified",
        )
        for row in built
        if row.eligible and row.execution_at.startswith(f"{year}-")
    )


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
            "2022-01-01",
            "2022-12-31",
            "2023-01-01",
            "2023-12-31",
            "2024-01-01",
            "2024-12-31",
        )
    )


def _mapping_result(score: UsageScore, trial: tuple[str, int]) -> MappingResult:
    return MappingResult(
        score.candidate_id,
        score.spec.usage,
        score.spec.breadth,
        score.year,
        score.excess_sharpe,
        score.cumulative_excess_return,
        score.maximum_drawdown,
        score.mean_turnover,
        score.total_cost_rate,
        score.active_days,
        trial[0],
        trial[1],
    )


def run_v43_conversion(
    daily_dir: str | Path,
    membership_path: str | Path,
    *,
    chip_dir: str | Path,
    limit_event_dir: str | Path,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    config: ConversionConfig | None = None,
    prior_inferential_trials: int = 804,
) -> V43ConversionReport:
    config = config or ConversionConfig()
    config.validate()
    if prior_inferential_trials < 0:
        raise ValueError("prior_inferential_trials cannot be negative")
    schemas = _schemas()
    memberships, membership_sha = _load_memberships(membership_path, config.universe_top_n)
    memberships = {day: members for day, members in memberships.items() if day <= "2023-12-31"}
    instruments = tuple(sorted({item for members in memberships.values() for item in members}))
    root = Path(daily_dir).expanduser().resolve()
    daily_files = select_qd_daily_files(root, start_date=config.data_start, end_date="2023-12-31")
    daily_manifest = build_selected_files_snapshot_manifest(root, daily_files)
    daily = load_qd_daily_directory(
        root, start_date=config.data_start, end_date="2023-12-31", instruments=instruments
    )
    alternatives = {}
    alternative_hashes = {}
    for kind, source in (("chip", chip_dir), ("limit_event", limit_event_dir)):
        dataset = load_qd_alternative_directory(
            source,
            QdAlternativeConfig(
                source_kind=kind,  # type: ignore[arg-type]
                start_date="2022-01-01",
                end_date="2023-12-31",
                ingested_at=config.ingested_at,
                instruments=instruments,
            ),
        )
        alternatives[kind] = dataset.observations
        alternative_hashes[kind] = dataset.audit.source_sha256
    composite = build_composite_snapshot_manifest(
        {"qd_daily": daily_manifest.snapshot_sha256, "dynamic_universe": membership_sha, **alternative_hashes}
    )
    snapshot_id = registry.register_snapshot(
        composite, vendor_version=V43_CONVERSION_VERSION, notes="2022 select; 2023 confirm; 2024 unopened"
    )
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            "V4.3 frozen IC-to-return conversion",
            "Avoidance or breadth conversion may monetize stable cross-sectional IC without concentrated long exposure.",
            snapshot_id,
            code_version,
            json.dumps(
                {"version": V43_CONVERSION_VERSION, "config": asdict(config), "signal_set": FROZEN_SIGNAL_SET_SHA256},
                sort_keys=True,
            ),
        )
    )
    calendar = tuple(sorted({item.trade_date for item in daily.bars}))
    by_instrument: dict[str, dict[str, QmtDailyBar]] = defaultdict(dict)
    for bar in daily.bars:
        by_instrument[bar.instrument][bar.trade_date] = bar
    execution_members = _execution_memberships(memberships, calendar)
    usage_config = V41Config(
        primary_nav=config.primary_nav,
        commission_bps=config.commission_bps,
        sell_tax_bps=config.sell_tax_bps,
        slippage_bps=config.slippage_bps,
        impact_bps=config.impact_bps,
        participation_rate=config.participation_rate,
        ingested_at=config.ingested_at,
    )
    panels: dict[tuple[int, str], tuple[EvaluationObservation, ...]] = {}
    for year in (2022, 2023):
        anchors = _anchors(
            year=year,
            horizon=config.horizon,
            calendar=calendar,
            bars=by_instrument,
            execution_members=execution_members,
        )
        for candidate_id, schema in schemas.items():
            required = {
                source: alternatives[source.removeprefix("qd_")]
                for source in schema.data_sources
                if source != "qd_daily"
            }
            panels[(year, candidate_id)] = _panel(
                schema,
                year=year,
                bars=daily.bars,
                alternatives=required,
                anchors=anchors,
            )
    diagnostics = {}
    for (year, candidate_id), rows in panels.items():
        counts: dict[str, int] = defaultdict(int)
        for item in rows:
            counts[item.timestamp[:10]] += 1
        diagnostics[f"{year}:{candidate_id}"] = (len(rows), max(counts.values(), default=0))
    if any(size == 0 or maximum <= max(config.breadths) for size, maximum in diagnostics.values()):
        raise ValueError(f"conversion panels lack required cross-section: {diagnostics}")
    selection: list[MappingResult] = []
    raw_sharpes = []
    for candidate_id in FROZEN_SIGNAL_IDS:
        rows = panels[(2022, candidate_id)]
        for usage in config.usages:
            for breadth in config.breadths:
                spec = UsageSpec(usage, breadth, "all")
                trial = _trial(
                    registry,
                    experiment_id,
                    stage="v4.3_2022_mapping_selection",
                    factor_set=f"{candidate_id}:{spec.identity}",
                    parameters={"candidate_id": candidate_id, "spec": asdict(spec), "year": 2022},
                    seed=config.seed,
                )
                score, returns = evaluate_usage(
                    candidate_id,
                    rows,
                    rows,
                    spec,
                    year=2022,
                    horizon=config.horizon,
                    nav=config.primary_nav,
                    bars=by_instrument,
                    calendar=calendar,
                    regimes={},
                    config=usage_config,
                )
                result = _mapping_result(score, trial)
                registry.record_trial_result(trial[0], json.dumps(asdict(result), sort_keys=True))
                selection.append(result)
                raw_sharpes.append(
                    (sum(returns) / len(returns))
                    / (math.sqrt(sum((item - sum(returns) / len(returns)) ** 2 for item in returns) / (len(returns) - 1)))
                    if len(returns) > 1 and len(set(returns)) > 1
                    else 0.0
                )
    selected = select_mapping(tuple(selection))
    recorded_trials = prior_inferential_trials + registry.global_trial_count()
    selected_raw = selected.excess_sharpe / math.sqrt(252)
    dsr = deflated_sharpe_ratio(
        observed_sharpe=selected_raw,
        trial_sharpes=raw_sharpes,
        recorded_trial_count=recorded_trials,
        observations=max(selected.active_days, 2),
    )
    selected_spec = UsageSpec(selected.usage, selected.breadth, "all")
    confirm_trial = _trial(
        registry,
        experiment_id,
        stage="v4.3_2023_frozen_confirmation",
        factor_set=f"{selected.candidate_id}:{selected_spec.identity}",
        parameters={
            "frozen_from": selected.trial_id,
            "candidate_id": selected.candidate_id,
            "spec": asdict(selected_spec),
            "year": 2023,
        },
        seed=config.seed,
    )
    confirmation_score, _ = evaluate_usage(
        selected.candidate_id,
        panels[(2023, selected.candidate_id)],
        panels[(2023, selected.candidate_id)],
        selected_spec,
        year=2023,
        horizon=config.horizon,
        nav=config.primary_nav,
        bars=by_instrument,
        calendar=calendar,
        regimes={},
        config=usage_config,
    )
    confirmation = _mapping_result(confirmation_score, confirm_trial)
    registry.record_trial_result(confirm_trial[0], json.dumps(asdict(confirmation), sort_keys=True))
    failures = []
    if selected.excess_sharpe < config.minimum_selection_sharpe:
        failures.append("selection_sharpe")
    if dsr.probability < config.minimum_dsr:
        failures.append("multiplicity_dsr")
    if confirmation.excess_sharpe < config.minimum_confirmation_sharpe:
        failures.append("confirmation_sharpe")
    if confirmation.excess_return <= 0:
        failures.append("confirmation_return")
    if confirmation.maximum_drawdown < -config.maximum_confirmation_drawdown:
        failures.append("confirmation_drawdown")
    report = V43ConversionReport(
        V43_CONVERSION_VERSION,
        experiment_id,
        snapshot_id,
        composite.snapshot_sha256,
        FROZEN_SIGNAL_SET_SHA256,
        len(selection),
        selected,
        confirmation,
        dsr.probability,
        recorded_trials + 1,
        True,
        False,
        "PASS_2023_CONFIRMATION" if not failures else "REJECT_2023_CONFIRMATION",
        tuple(failures),
    )
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "v4.3-conversion.json").write_text(report.to_json() + "\n", encoding="utf-8")
    (output / "v4.3-conversion.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (output / "v4.3-conversion.en.md").write_text(report.to_markdown("en"), encoding="utf-8")
    return report
