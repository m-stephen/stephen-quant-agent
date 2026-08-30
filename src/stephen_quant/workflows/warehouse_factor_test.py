from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean

from stephen_quant.evaluation import EvaluationObservation
from stephen_quant.evaluation.metrics import summarize_horizon
from stephen_quant.factors import build_seed_registry
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest
from stephen_quant.qmt.observations import build_qmt_factor_observations
from stephen_quant.qmt.warehouse_adapter import (
    latest_warehouse_snapshot,
    load_qd_warehouse_daily,
    select_prior_liquidity_universe,
)

WAREHOUSE_FACTOR_TEST_VERSION = "v8.4-warehouse-factor-smoke-1.0.0"


@dataclass(frozen=True)
class WarehouseFactorTestConfig:
    universe_start: str = "2021-01-01"
    universe_end: str = "2021-12-31"
    data_start: str = "2021-10-01"
    data_end: str = "2023-01-10"
    evaluation_start: str = "2022-01-04"
    evaluation_end: str = "2022-12-30"
    top_n: int = 200
    minimum_universe_sessions: int = 120
    factor_id: str = "ret_20"
    horizon_sessions: int = 1
    minimum_cross_section: int = 20


@dataclass(frozen=True)
class WarehouseFactorTestReport:
    method_version: str
    status: str
    verdict: str
    warehouse_snapshot_sha256: str
    registry_snapshot_id: str
    experiment_id: str
    trial_id: str
    trial_number: int
    factor_id: str
    factor_version: str
    universe_method: str
    universe_size: int
    data_rows: int
    evaluation_observations: int
    evaluation_dates: int
    mean_rank_ic: float
    rank_icir: float | None
    rank_ic_hit_rate: float
    mean_top_decile_return: float
    mean_bottom_decile_return: float
    mean_gross_top_minus_bottom: float
    integrity_note: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True)

    def to_markdown(self, language: str) -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        title = "V8.4 数据库因子链路验收报告" if zh else "V8.4 Warehouse Factor Path Test"
        note = (
            "该结果仅证明数据库接入和因子计算链路可用，不是 Alpha Court 通过结论。"
            if zh
            else "This result proves the warehouse-to-factor path only; it is not an Alpha Court pass."
        )
        labels = {
            "状态": "Status",
            "结论": "Verdict",
            "仓库快照": "Warehouse snapshot",
            "实验": "Experiment",
            "Trial": "Trial",
            "因子": "Factor",
            "股票池": "Universe",
            "数据行": "Data rows",
            "评价观测": "Evaluation observations",
            "评价交易日": "Evaluation dates",
            "平均 RankIC": "Mean RankIC",
            "RankICIR": "RankICIR",
            "RankIC 胜率": "RankIC hit rate",
            "多头十分位日均收益": "Mean top-decile daily return",
            "空头十分位日均收益": "Mean bottom-decile daily return",
            "毛多空日均收益": "Mean gross top-minus-bottom daily return",
        }
        def label(value: str) -> str:
            return value if zh else labels[value]
        return "\n".join(
            [
                f"# {title}",
                "",
                f"- {label('状态')}: `{self.status}`",
                f"- {label('结论')}: `{self.verdict}`",
                f"- {label('仓库快照')}: `{self.warehouse_snapshot_sha256}`",
                f"- {label('实验')}: `{self.experiment_id}`",
                f"- {label('Trial')}: `{self.trial_id}` (#{self.trial_number})",
                f"- {label('因子')}: `{self.factor_id}@{self.factor_version}`",
                f"- {label('股票池')}: {self.universe_size} ({self.universe_method})",
                f"- {label('数据行')}: {self.data_rows:,}",
                f"- {label('评价观测')}: {self.evaluation_observations:,}",
                f"- {label('评价交易日')}: {self.evaluation_dates}",
                f"- {label('平均 RankIC')}: {self.mean_rank_ic:.6f}",
                f"- {label('RankICIR')}: {'N/A' if self.rank_icir is None else f'{self.rank_icir:.6f}'}",
                f"- {label('RankIC 胜率')}: {self.rank_ic_hit_rate:.2%}",
                f"- {label('多头十分位日均收益')}: {self.mean_top_decile_return:.6%}",
                f"- {label('空头十分位日均收益')}: {self.mean_bottom_decile_return:.6%}",
                f"- {label('毛多空日均收益')}: {self.mean_gross_top_minus_bottom:.6%}",
                "",
                f"> {note}",
                "",
            ]
        )


def _decile_returns(rows: tuple[EvaluationObservation, ...], direction: int) -> tuple[float, float]:
    by_date: dict[str, list[EvaluationObservation]] = defaultdict(list)
    for row in rows:
        by_date[row.timestamp].append(row)
    top: list[float] = []
    bottom: list[float] = []
    for day in sorted(by_date):
        cross = sorted(by_date[day], key=lambda row: (direction * row.factor_value, row.instrument))
        width = max(1, len(cross) // 10)
        bottom.append(mean(row.forward_return for row in cross[:width]))
        top.append(mean(row.forward_return for row in cross[-width:]))
    return mean(top), mean(bottom)


def run_warehouse_factor_test(
    warehouse_root: str | Path,
    *,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    config: WarehouseFactorTestConfig | None = None,
) -> WarehouseFactorTestReport:
    config = config or WarehouseFactorTestConfig()
    warehouse_snapshot = latest_warehouse_snapshot(warehouse_root)
    universe = select_prior_liquidity_universe(
        warehouse_root,
        start_date=config.universe_start,
        end_date=config.universe_end,
        top_n=config.top_n,
        minimum_sessions=config.minimum_universe_sessions,
        verified_snapshot_id=warehouse_snapshot,
    )
    dataset = load_qd_warehouse_daily(
        warehouse_root,
        start_date=config.data_start,
        end_date=config.data_end,
        instruments=universe,
        adjustment="back_ratio",
        verified_snapshot_id=warehouse_snapshot,
    )
    factor = build_seed_registry().get(config.factor_id)
    dates = sorted({bar.trade_date for bar in dataset.bars})
    eligibility = {day: universe for day in dates}
    baseline_rows = build_qmt_factor_observations(
        dataset.bars,
        factor,
        test_start=config.evaluation_start,
        test_end=config.evaluation_end,
        horizon_sessions=config.horizon_sessions,
        eligible_by_execution_date=eligibility,
    )
    rows = tuple(
        EvaluationObservation(
            timestamp=row.execution_at,
            instrument=row.instrument,
            factor_value=row.signal,
            factor_available_at=row.signal_available_at,
            label_start_at=row.execution_at,
            label_end_at=row.return_end_at,
            forward_return=row.forward_return,
            horizon=f"{config.horizon_sessions}d",
            subperiod="warehouse_smoke",
            regime="unspecified",
        )
        for row in baseline_rows
        if row.eligible
    )
    metrics = summarize_horizon(
        f"{config.horizon_sessions}d",
        rows,
        direction=factor.direction,
        min_cross_section=config.minimum_cross_section,
    )
    top, bottom = _decile_returns(rows, factor.direction)

    manifest = build_composite_snapshot_manifest({"qd_warehouse": warehouse_snapshot})
    registry_snapshot = registry.register_snapshot(
        manifest,
        vendor_version=WAREHOUSE_FACTOR_TEST_VERSION,
        notes="Read-only DuckDB warehouse factor-path test",
    )
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            name="v8.4_warehouse_factor_path_test",
            hypothesis="The frozen DuckDB warehouse can feed the existing point-in-time factor engine.",
            dataset_snapshot_id=registry_snapshot,
            code_version=code_version,
            search_space=json.dumps(asdict(config), sort_keys=True),
        )
    )
    trial_id, trial_number = registry.create_trial(
        TrialSpec(
            experiment_id=experiment_id,
            model_name=WAREHOUSE_FACTOR_TEST_VERSION,
            factor_set=f"{factor.factor_id}@{factor.version}",
            hyperparams=json.dumps(asdict(config), sort_keys=True),
            seed=0,
            train_start=config.universe_start,
            train_end=config.universe_end,
            validation_start=config.evaluation_start,
            validation_end=config.evaluation_end,
            test_start="SEALED",
            test_end="SEALED",
        )
    )
    report = WarehouseFactorTestReport(
        WAREHOUSE_FACTOR_TEST_VERSION,
        "PASSED",
        "DATABASE_FACTOR_PATH_OPERATIONAL",
        warehouse_snapshot,
        registry_snapshot,
        experiment_id,
        trial_id,
        trial_number,
        factor.factor_id,
        factor.version,
        f"prior-period mean amount {config.universe_start}..{config.universe_end}",
        len(universe),
        len(dataset.bars),
        len(rows),
        metrics.dates,
        metrics.mean_rank_ic,
        metrics.rank_icir,
        metrics.rank_ic_hit_rate,
        top,
        bottom,
        top - bottom,
        "The warehouse snapshot was verified before reading; one predeclared factor attempt was recorded.",
    )
    registry.record_trial_result(trial_id, report.to_json())
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "warehouse-factor-test.json").write_text(report.to_json() + "\n", encoding="utf-8")
    (output / "warehouse-factor-test.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (output / "warehouse-factor-test.en.md").write_text(report.to_markdown("en"), encoding="utf-8")
    return report
