from __future__ import annotations

import json
from dataclasses import asdict, dataclass

METHOD_VERSION = "momentum-topk-baseline-1.0.0"
COST_MODEL_VERSION = "linear-plus-sqrt-impact-1.0.0"


@dataclass(frozen=True)
class BaselineObservation:
    """Point-in-time signal, liquidity, and subsequent return for one asset."""

    instrument: str
    signal: float
    signal_at: str
    signal_available_at: str
    average_daily_value: float
    liquidity_available_at: str
    execution_at: str
    return_end_at: str
    forward_return: float


@dataclass(frozen=True)
class BaselineLineage:
    factor_id: str
    factor_version: str
    snapshot_id: str
    experiment_id: str
    trial_id: str
    code_version: str


@dataclass(frozen=True)
class BaselineConfig:
    top_k: int
    rebalance_every: int = 1
    direction: int = 1
    cash_reserve: float = 0.0
    max_position_weight: float = 1.0
    commission_bps: float = 0.0
    slippage_bps: float = 0.0
    impact_coefficient_bps: float = 0.0
    max_participation_rate: float = 0.05
    periods_per_year: int = 252
    cost_model_version: str = COST_MODEL_VERSION


@dataclass(frozen=True)
class OrderExecution:
    instrument: str
    selected: bool
    signal: float
    pretrade_weight: float
    target_weight: float
    desired_notional: float
    capacity_notional: float
    executed_notional: float
    participation_rate: float
    capacity_clipped_notional: float
    funding_clipped_notional: float
    commission_cost: float
    slippage_cost: float
    market_impact_cost: float
    total_cost: float


@dataclass(frozen=True)
class BacktestPeriod:
    execution_at: str
    return_end_at: str
    rebalanced: bool
    selected_instruments: tuple[str, ...]
    start_nav: float
    end_nav: float
    gross_return: float
    net_return: float
    turnover: float
    traded_notional: float
    total_cost: float
    cash_after_execution: float
    orders: tuple[OrderExecution, ...]


@dataclass(frozen=True)
class BaselineMetrics:
    periods: int
    initial_nav: float
    final_nav: float
    gross_total_return: float
    net_total_return: float
    annualized_net_return: float
    annualized_net_volatility: float | None
    net_sharpe: float | None
    max_drawdown: float
    total_turnover: float
    total_traded_notional: float
    total_cost: float
    capacity_clipped_notional: float
    funding_clipped_notional: float
    clipped_orders: int


@dataclass(frozen=True)
class BaselineReport:
    method_version: str
    lineage: BaselineLineage
    config: BaselineConfig
    metrics: BaselineMetrics
    periods: tuple[BacktestPeriod, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)

    @staticmethod
    def _optional(value: float | None) -> str:
        return "N/A" if value is None else f"{value:.6f}"

    def to_markdown(self) -> str:
        metrics = self.metrics
        lines = [
            f"# Momentum Top-K Baseline: {self.lineage.factor_id}@{self.lineage.factor_version}",
            "",
            "## Lineage and assumptions",
            "",
            f"- Snapshot: `{self.lineage.snapshot_id}`",
            f"- Experiment: `{self.lineage.experiment_id}`",
            f"- Trial: `{self.lineage.trial_id}`",
            f"- Code: `{self.lineage.code_version}`",
            f"- Method: `{self.method_version}`",
            f"- Cost model: `{self.config.cost_model_version}`",
            f"- Top-K: {self.config.top_k}",
            f"- Rebalance every: {self.config.rebalance_every} period(s)",
            f"- Commission: {self.config.commission_bps:.4f} bps",
            f"- Slippage: {self.config.slippage_bps:.4f} bps",
            f"- Impact coefficient: {self.config.impact_coefficient_bps:.4f} bps",
            f"- Maximum ADV participation: {self.config.max_participation_rate:.2%}",
            "",
            "## Net-of-cost results",
            "",
            f"- Initial NAV: {metrics.initial_nav:.6f}",
            f"- Final NAV: {metrics.final_nav:.6f}",
            f"- Gross total return: {metrics.gross_total_return:.6%}",
            f"- Net total return: {metrics.net_total_return:.6%}",
            f"- Annualized net return: {metrics.annualized_net_return:.6%}",
            f"- Annualized net volatility: {self._optional(metrics.annualized_net_volatility)}",
            f"- Net Sharpe: {self._optional(metrics.net_sharpe)}",
            f"- Maximum drawdown: {metrics.max_drawdown:.6%}",
            f"- Total cost: {metrics.total_cost:.6f}",
            f"- Total turnover: {metrics.total_turnover:.6f}",
            f"- Capacity-clipped notional: {metrics.capacity_clipped_notional:.6f}",
            f"- Funding-clipped notional: {metrics.funding_clipped_notional:.6f}",
            f"- Clipped orders: {metrics.clipped_orders}",
        ]
        return "\n".join(lines) + "\n"


class BaselineError(ValueError):
    """Raised when a baseline backtest violates timing or execution constraints."""
