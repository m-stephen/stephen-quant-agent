from __future__ import annotations

import hashlib
import json
import random
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from stephen_quant.discovery.portfolio_native import (
    PortfolioNativeReport,
    PortfolioObservation,
    PortfolioPolicy,
    evaluate_portfolio_native,
)
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest
from stephen_quant.qmt.data_warehouse import _duckdb
from stephen_quant.qmt.qd_alternative import SOURCE_FIELDS

from .v90_alpha_discovery import (
    V90_VERSION,
    V90Config,
    frozen_v81_proposal,
)

V90_EMPIRICAL_VERSION = "v9.0-frozen-v8.1-portfolio-replay-1.0.0"
V90_DAILY_SNAPSHOT = "9ba3320edf76036e5431c0360eed5bf54ca641936a3fa2f1ab12064019cfebd5"
V90_MULTISOURCE_SNAPSHOT = "cc4d6ccb871887aa9d1561827e430e52fcd6c0e2fbc63ba617369580e5f07bcd"


@dataclass(frozen=True)
class V90SegmentEvidence:
    name: str
    start: str
    end: str
    observations: int
    rebalance_periods: int
    placebo_p_value: float
    portfolio: PortfolioNativeReport
    economic_gate_passed: bool


@dataclass(frozen=True)
class V90EmpiricalReport:
    method_version: str
    planning_version: str
    daily_snapshot_sha256: str
    multisource_snapshot_sha256: str
    experiment_id: str
    trial_id: str
    trial_number: int
    total_recorded_trials: int
    candidate_id: str
    candidate_formula: str
    candidate_direction: int
    policy: PortfolioPolicy
    segments: tuple[V90SegmentEvidence, ...]
    dsr_recomputed: bool
    pbo_recomputed: bool
    alpha_court_passed: bool
    decision: str
    integrity_note: str
    analysis_sha256: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        lines = [
            "# V9.0 冻结候选组合原生重放" if zh else "# V9.0 Frozen-candidate Portfolio-native Replay",
            "",
            f"**{'结论' if zh else 'Decision'}: `{self.decision}`**",
            "",
            f"- {'候选' if zh else 'Candidate'}: `{self.candidate_id}`",
            f"- {'累计 Trial' if zh else 'Cumulative Trials'}: {self.total_recorded_trials}",
            f"- {'资金' if zh else 'NAV'}: CNY {self.policy.initial_nav_cny:,.0f}",
            f"- Top-K / buffer: {self.policy.top_k} / {self.policy.rank_buffer}",
            f"- {'DSR 已重算' if zh else 'DSR recomputed'}: {self.dsr_recomputed}",
            f"- {'PBO 已重算' if zh else 'PBO recomputed'}: {self.pbo_recomputed}",
            "",
            "| Segment | Periods | Net excess | Sharpe | Double-cost | Drawdown | Placebo p | Capacity | Gate |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
        for item in self.segments:
            report = item.portfolio
            lines.append(
                f"| {item.name} | {item.rebalance_periods} | {report.net_excess_total_return:.2%} | "
                f"{report.annualized_net_excess_sharpe:.3f} | {report.double_cost_total_return:.2%} | "
                f"{report.maximum_drawdown:.2%} | {item.placebo_p_value:.3f} | "
                f"CNY {report.capacity_cny:,.0f} | {'PASS' if item.economic_gate_passed else 'FAIL'} |"
            )
        lines.extend(["", f"> {self.integrity_note}", ""])
        return "\n".join(lines)


def _frozen_manifest(
    root: Path, folder: str, snapshot_id: str
) -> tuple[Path, dict[str, object]]:
    if len(snapshot_id) != 64 or any(char not in "0123456789abcdef" for char in snapshot_id):
        raise ValueError("snapshot_id must be a lowercase SHA-256")
    path = root / folder / f"{snapshot_id}.json"
    if not path.is_file():
        raise ValueError(f"warehouse has no frozen {folder} manifest {snapshot_id}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("warehouse manifest must be an object")
    expected = str(payload.get("snapshot_id") or path.stem)
    if expected != path.stem:
        raise ValueError("warehouse manifest filename and snapshot_id differ")
    return path, payload


def _daily_paths(root: Path, payload: dict[str, object], start: str, end: str) -> list[str]:
    rows = payload.get("active_partitions")
    if not isinstance(rows, list):
        raise TypeError("daily snapshot has no active partitions")
    selected = []
    for row in rows:
        if (
            isinstance(row, list)
            and len(row) >= 9
            and row[0] == "qd_daily"
            and str(row[7]) <= end
            and str(row[8]) >= start
        ):
            path = (root / str(row[3])).resolve()
            if root not in path.parents or not path.is_file():
                raise ValueError("daily manifest path escapes or is missing")
            selected.append(str(path))
    if not selected:
        raise ValueError("daily snapshot has no selected partitions")
    return selected


def _flow_paths(root: Path, payload: dict[str, object], start: str, end: str) -> list[str]:
    rows = payload.get("partitions")
    if not isinstance(rows, list):
        raise TypeError("multisource snapshot has no partitions")
    selected = []
    for row in rows:
        if (
            isinstance(row, dict)
            and row.get("dataset") == "qd_fund_flow"
            and str(row.get("min_date")) <= end
            and str(row.get("max_date")) >= start
        ):
            path = (root / str(row["path"])).resolve()
            if root not in path.parents or not path.is_file():
                raise ValueError("fund-flow manifest path escapes or is missing")
            selected.append(str(path))
    if not selected:
        raise ValueError("multisource snapshot has no fund-flow partitions")
    return selected


def _load_candidate_panel(
    warehouse_root: Path,
    *,
    daily_manifest: dict[str, object],
    multisource_manifest: dict[str, object],
    data_start: str,
    data_end: str,
) -> tuple[PortfolioObservation, ...]:
    daily_paths = _daily_paths(warehouse_root, daily_manifest, data_start, data_end)
    flow_paths = _flow_paths(warehouse_root, multisource_manifest, data_start, data_end)
    flow_column = SOURCE_FIELDS["fund_flow"]["net_inflow_amount"].column.replace('"', '""')
    query = f"""
        WITH daily_base AS (
          SELECT trade_date, upper(instrument) instrument,
                 open * adjustment_factor adjusted_open,
                 close * adjustment_factor adjusted_close,
                 amount * 1000.0 amount_cny
          FROM read_parquet(?, union_by_name=true)
          WHERE trade_date BETWEEN ? AND ?
        ), daily_window AS (
          SELECT *,
                 lag(adjusted_close, 5) OVER w close_lag_5,
                 lead(adjusted_open, 1) OVER w execution_open,
                 lead(adjusted_open, 21) OVER w exit_open,
                 lead(trade_date, 1) OVER w execution_date,
                 avg(amount_cny) OVER (
                   PARTITION BY instrument ORDER BY trade_date
                   ROWS BETWEEN 120 PRECEDING AND 1 PRECEDING
                 ) prior_adv_cny,
                 count(*) OVER (
                   PARTITION BY instrument ORDER BY trade_date
                   ROWS BETWEEN 120 PRECEDING AND 1 PRECEDING
                 ) history_sessions
          FROM daily_base
          WINDOW w AS (PARTITION BY instrument ORDER BY trade_date)
        ), flow_raw AS (
          SELECT _trade_date trade_date, upper(_entity_id) instrument,
                 try_cast("{flow_column}" AS DOUBLE) * 10000.0 net_inflow_amount,
                 row_number() OVER (
                   PARTITION BY _trade_date, upper(_entity_id)
                   ORDER BY _ingested_at DESC, _source_container_sha256 DESC
                 ) revision_rank
          FROM read_parquet(?, union_by_name=true)
          WHERE _trade_date BETWEEN ? AND ?
        ), flow AS (
          SELECT trade_date, instrument, net_inflow_amount
          FROM flow_raw WHERE revision_rank = 1
        ), joined AS (
          SELECT d.*, f.net_inflow_amount
          FROM daily_window d LEFT JOIN flow f USING(trade_date, instrument)
        ), signals AS (
          SELECT *,
                 avg(net_inflow_amount) OVER w5 flow_mean_5,
                 count(net_inflow_amount) OVER w5 flow_count_5,
                 avg(amount_cny) OVER w5 amount_mean_5
          FROM joined
          WINDOW w5 AS (
            PARTITION BY instrument ORDER BY trade_date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
          )
        ), eligible AS (
          SELECT *,
                 flow_mean_5 / (amount_mean_5 + 1.0)
                   - (adjusted_close / close_lag_5 - 1.0) signal,
                 exit_open / execution_open - 1.0 forward_return
          FROM signals
          WHERE history_sessions >= 120 AND flow_count_5 = 5
            AND close_lag_5 IS NOT NULL AND execution_open > 0 AND exit_open > 0
            AND execution_date IS NOT NULL AND prior_adv_cny > 0
        ), ranked AS (
          SELECT *, row_number() OVER (
            PARTITION BY trade_date ORDER BY prior_adv_cny DESC, instrument
          ) liquidity_rank
          FROM eligible
        ), universe AS (
          SELECT * FROM ranked WHERE liquidity_rank <= 300
        ), labelled AS (
          SELECT *, avg(forward_return) OVER (PARTITION BY execution_date) benchmark_return
          FROM universe
        )
        SELECT CAST(execution_date AS VARCHAR), instrument, signal, forward_return,
               benchmark_return, prior_adv_cny,
               CAST(trade_date AS VARCHAR)
        FROM labelled ORDER BY execution_date, instrument
    """
    connection = _duckdb().connect()
    try:
        rows = connection.execute(
            query,
            [daily_paths, data_start, data_end, flow_paths, data_start, data_end],
        ).fetchall()
    finally:
        connection.close()
    result = tuple(
        PortfolioObservation(
            date=str(row[0]),
            instrument=str(row[1]),
            score=float(row[2]),
            forward_return=float(row[3]),
            benchmark_return=float(row[4]),
            prior_adv_cny=float(row[5]),
            available_at=f"{row[6]}T18:00:00+08:00",
            label_start_at=f"{row[0]}T09:30:00+08:00",
        )
        for row in rows
    )
    if not result:
        raise ValueError("frozen V8.1 query produced no observations")
    return result


def _segment_rows(
    rows: tuple[PortfolioObservation, ...], start: str, end: str, horizon_sessions: int = 20
) -> tuple[PortfolioObservation, ...]:
    dates = sorted({item.date for item in rows if start <= item.date <= end})
    selected = set(dates[::horizon_sessions])
    return tuple(item for item in rows if item.date in selected)


def _placebo_p_value(
    rows: tuple[PortfolioObservation, ...],
    observed: PortfolioNativeReport,
    policy: PortfolioPolicy,
    *,
    repetitions: int = 199,
    seed: int = 20260902,
) -> float:
    by_date: dict[str, list[PortfolioObservation]] = defaultdict(list)
    for item in rows:
        by_date[item.date].append(item)
    rng = random.Random(seed)
    exceed = 0
    for _ in range(repetitions):
        shuffled = []
        for day in sorted(by_date):
            cross = by_date[day]
            scores = [item.score for item in cross]
            rng.shuffle(scores)
            shuffled.extend(replace(item, score=score) for item, score in zip(cross, scores, strict=True))
        placebo = evaluate_portfolio_native(tuple(shuffled), policy=policy)
        exceed += placebo.net_excess_total_return >= observed.net_excess_total_return
    return (exceed + 1) / (repetitions + 1)


def run_v90_empirical_replay(
    warehouse_root: str | Path,
    *,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    policy: PortfolioPolicy | None = None,
    daily_snapshot_id: str = V90_DAILY_SNAPSHOT,
    multisource_snapshot_id: str = V90_MULTISOURCE_SNAPSHOT,
    config: V90Config | None = None,
) -> V90EmpiricalReport:
    root = Path(warehouse_root).expanduser().resolve()
    config = config or V90Config()
    config.validate()
    policy = policy or config.portfolio_policy
    policy.validate()
    daily_path, daily_manifest = _frozen_manifest(root, "snapshots", daily_snapshot_id)
    multi_path, multi_manifest = _frozen_manifest(
        root, "multisource-snapshots", multisource_snapshot_id
    )
    daily_snapshot = str(daily_manifest.get("snapshot_id") or daily_path.stem)
    multi_snapshot = str(multi_manifest.get("snapshot_id") or multi_path.stem)
    panel = _load_candidate_panel(
        root,
        daily_manifest=daily_manifest,
        multisource_manifest=multi_manifest,
        data_start="2014-06-01",
        data_end=config.stress_end,
    )
    candidate = frozen_v81_proposal()
    composite = build_composite_snapshot_manifest(
        {"qd_daily": daily_snapshot, "qd_multisource": multi_snapshot}
    )
    snapshot_id = registry.register_snapshot(
        composite,
        vendor_version=V90_EMPIRICAL_VERSION,
        notes="Manifest-bound read-only DuckDB/Parquet V9 replay; 2025+ excluded from evaluation.",
    )
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            name="v9_frozen_v81_portfolio_native_replay",
            hypothesis=candidate.proposal.hypothesis,
            dataset_snapshot_id=snapshot_id,
            code_version=code_version,
            search_space=json.dumps(
                {
                    "candidate": candidate.proposal_id,
                    "formula": candidate.schema.formula,
                    "policy": asdict(policy),
                    "selection": "frozen before this replay",
                },
                sort_keys=True,
            ),
        )
    )
    trial_id, trial_number = registry.create_trial(
        TrialSpec(
            experiment_id=experiment_id,
            model_name=V90_EMPIRICAL_VERSION,
            factor_set=candidate.proposal_id,
            hyperparams=json.dumps(asdict(policy), sort_keys=True),
            seed=20260902,
            train_start=config.discovery_start,
            train_end=config.discovery_end,
            validation_start=config.validation_start,
            validation_end=config.validation_end,
            test_start=config.frozen_test_start,
            test_end=config.stress_end,
        )
    )
    definitions = (
        ("discovery", config.discovery_start, config.discovery_end),
        ("validation", config.validation_start, config.validation_end),
        ("frozen_test", config.frozen_test_start, config.frozen_test_end),
        ("confirmation", config.confirmation_start, config.confirmation_end),
        ("stress", config.stress_start, config.stress_end),
    )
    segments = []
    for index, (name, start, end) in enumerate(definitions):
        selected = _segment_rows(panel, start, end)
        portfolio = evaluate_portfolio_native(selected, policy=policy)
        placebo = _placebo_p_value(
            selected,
            portfolio,
            policy,
            seed=20260902 + index,
        )
        gate = (
            portfolio.net_excess_total_return > 0
            and portfolio.annualized_net_excess_sharpe >= 0.50
            and portfolio.double_cost_total_return > 0
            and portfolio.maximum_drawdown >= -0.25
            and portfolio.capacity_passed
            and placebo <= 0.05
        )
        segments.append(
            V90SegmentEvidence(
                name,
                start,
                end,
                len(selected),
                len(portfolio.periods),
                placebo,
                portfolio,
                gate,
            )
        )
    with registry.connect() as connection:
        local_trials = int(connection.execute("SELECT count(*) FROM trials").fetchone()[0])
    stable_analysis = {
        "method_version": V90_EMPIRICAL_VERSION,
        "planning_version": V90_VERSION,
        "daily_snapshot_sha256": daily_snapshot,
        "multisource_snapshot_sha256": multi_snapshot,
        "candidate_id": candidate.proposal_id,
        "candidate_formula": candidate.schema.formula,
        "candidate_direction": candidate.schema.direction,
        "policy": asdict(policy),
        "segments": [asdict(item) for item in segments],
        "dsr_recomputed": False,
        "pbo_recomputed": False,
        "alpha_court_passed": False,
        "decision": "NO_RELIABLE_ALPHA",
    }
    analysis_sha256 = hashlib.sha256(
        json.dumps(stable_analysis, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    report = V90EmpiricalReport(
        V90_EMPIRICAL_VERSION,
        V90_VERSION,
        daily_snapshot,
        multi_snapshot,
        experiment_id,
        trial_id,
        trial_number,
        config.prior_inferential_trials + local_trials,
        candidate.proposal_id,
        candidate.schema.formula,
        candidate.schema.direction,
        policy,
        tuple(segments),
        False,
        False,
        False,
        "NO_RELIABLE_ALPHA",
        (
            "The V8.1 candidate and portfolio policy were frozen before this replay. Placebo and "
            "economic gates were recomputed from 2015-2024 only. A one-candidate replay cannot "
            "reconstruct the complete historical trial-Sharpe matrix or selection PBO, so DSR/PBO "
            "remain fail-closed and Alpha Court cannot pass. 2025-2026 labels were not queried."
        ),
        analysis_sha256,
    )
    registry.record_trial_result(trial_id, report.to_json())
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "v9.0-empirical.json").write_text(report.to_json() + "\n", encoding="utf-8")
    (output / "v9.0-empirical.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (output / "v9.0-empirical.en.md").write_text(report.to_markdown("en"), encoding="utf-8")
    digest = hashlib.sha256((output / "v9.0-empirical.json").read_bytes()).hexdigest()
    (output / "v9.0-empirical.sha256").write_text(digest + "\n", encoding="utf-8")
    return report
