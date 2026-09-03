from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from statistics import stdev

PORTFOLIO_NATIVE_VERSION = "9.0.0"


@dataclass(frozen=True)
class PortfolioObservation:
    date: str
    instrument: str
    score: float
    forward_return: float
    benchmark_return: float
    prior_adv_cny: float
    available_at: str
    label_start_at: str


@dataclass(frozen=True)
class PortfolioPolicy:
    initial_nav_cny: float = 3_000_000.0
    top_k: int = 40
    rank_buffer: int = 10
    round_trip_cost_bps: float = 41.0
    participation_rate: float = 0.05
    periods_per_year: int = 252 // 20

    def validate(self) -> None:
        if self.initial_nav_cny <= 0 or self.top_k < 2 or self.rank_buffer < 0:
            raise ValueError("invalid portfolio capital or breadth")
        if self.round_trip_cost_bps < 0 or not 0 < self.participation_rate <= 1:
            raise ValueError("invalid cost or participation policy")
        if self.periods_per_year < 1:
            raise ValueError("periods_per_year must be positive")


@dataclass(frozen=True)
class PortfolioPeriod:
    date: str
    holdings: tuple[str, ...]
    turnover: float
    gross_return: float
    benchmark_return: float
    gross_excess_return: float
    cost: float
    net_excess_return: float


@dataclass(frozen=True)
class YearAttribution:
    year: str
    periods: int
    gross_return: float
    benchmark_return: float
    total_cost: float
    net_excess_return: float


@dataclass(frozen=True)
class PortfolioNativeReport:
    method_version: str
    policy: PortfolioPolicy
    periods: tuple[PortfolioPeriod, ...]
    year_attribution: tuple[YearAttribution, ...]
    total_turnover: float
    total_cost: float
    gross_total_return: float
    benchmark_total_return: float
    net_excess_total_return: float
    annualized_net_excess_sharpe: float
    double_cost_total_return: float
    double_cost_sharpe: float
    maximum_drawdown: float
    capacity_cny: float
    capacity_passed: bool

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("portfolio timestamps must include timezone")
    return parsed


def _compound(values: list[float]) -> float:
    wealth = 1.0
    for value in values:
        wealth *= 1.0 + value
    return wealth - 1.0


def _sharpe(values: list[float], periods_per_year: int) -> float:
    if len(values) < 2:
        return 0.0
    dispersion = stdev(values)
    if dispersion == 0:
        return 0.0
    return sum(values) / len(values) / dispersion * math.sqrt(periods_per_year)


def _drawdown(values: list[float]) -> float:
    wealth = peak = 1.0
    worst = 0.0
    for value in values:
        wealth *= 1.0 + value
        peak = max(peak, wealth)
        worst = min(worst, wealth / peak - 1.0)
    return worst


def evaluate_portfolio_native(
    observations: tuple[PortfolioObservation, ...],
    *,
    policy: PortfolioPolicy | None = None,
) -> PortfolioNativeReport:
    """Evaluate exactly the portfolio policy used for candidate promotion.

    Ranking, buffer retention, costs, benchmark subtraction and capacity are applied in one place,
    preventing a high-IC candidate from being promoted using a different economic objective.
    """

    policy = policy or PortfolioPolicy()
    policy.validate()
    if not observations:
        raise ValueError("portfolio observations cannot be empty")
    by_date: dict[str, list[PortfolioObservation]] = defaultdict(list)
    keys: set[tuple[str, str]] = set()
    for item in observations:
        numeric = (
            item.score,
            item.forward_return,
            item.benchmark_return,
            item.prior_adv_cny,
        )
        if any(not math.isfinite(value) for value in numeric) or item.prior_adv_cny <= 0:
            raise ValueError("portfolio observation contains invalid numeric evidence")
        if _parse(item.available_at) > _parse(item.label_start_at):
            raise ValueError("portfolio observation leaks future information")
        key = (item.date, item.instrument)
        if key in keys:
            raise ValueError("duplicate portfolio observation")
        keys.add(key)
        by_date[item.date].append(item)
    periods: list[PortfolioPeriod] = []
    previous: tuple[str, ...] = ()
    capacity = math.inf
    for day in sorted(by_date):
        rows = sorted(by_date[day], key=lambda item: (-item.score, item.instrument))
        if len(rows) < policy.top_k:
            raise ValueError(f"portfolio date {day} has fewer rows than top_k")
        benchmark_values = [item.benchmark_return for item in rows]
        if max(benchmark_values) - min(benchmark_values) > 1e-12:
            raise ValueError("benchmark return must be unique within a portfolio date")
        ranks = {item.instrument: index + 1 for index, item in enumerate(rows)}
        retained = [
            instrument
            for instrument in previous
            if ranks.get(instrument, policy.top_k + policy.rank_buffer + 1)
            <= policy.top_k + policy.rank_buffer
        ]
        selected = retained[: policy.top_k]
        for item in rows:
            if item.instrument not in selected:
                selected.append(item.instrument)
            if len(selected) == policy.top_k:
                break
        holdings = tuple(sorted(selected))
        old_weight = 1.0 / len(previous) if previous else 0.0
        new_weight = 1.0 / len(holdings)
        union = set(previous) | set(holdings)
        turnover = 0.5 * sum(
            abs((new_weight if name in holdings else 0.0) - (old_weight if name in previous else 0.0))
            for name in union
        )
        index = {item.instrument: item for item in rows}
        gross = sum(index[name].forward_return for name in holdings) / len(holdings)
        benchmark = sum(benchmark_values) / len(benchmark_values)
        cost = turnover * policy.round_trip_cost_bps / 10_000.0
        net_excess = gross - benchmark - cost
        periods.append(
            PortfolioPeriod(
                day,
                holdings,
                turnover,
                gross,
                benchmark,
                gross - benchmark,
                cost,
                net_excess,
            )
        )
        capacity = min(
            capacity,
            min(
                index[name].prior_adv_cny * policy.participation_rate / new_weight
                for name in holdings
            ),
        )
        previous = holdings
    by_year: dict[str, list[PortfolioPeriod]] = defaultdict(list)
    for item in periods:
        by_year[item.date[:4]].append(item)
    years = tuple(
        YearAttribution(
            year,
            len(rows),
            _compound([item.gross_return for item in rows]),
            _compound([item.benchmark_return for item in rows]),
            sum(item.cost for item in rows),
            _compound([item.net_excess_return for item in rows]),
        )
        for year, rows in sorted(by_year.items())
    )
    net = [item.net_excess_return for item in periods]
    double_cost = [item.gross_excess_return - 2 * item.cost for item in periods]
    return PortfolioNativeReport(
        PORTFOLIO_NATIVE_VERSION,
        policy,
        tuple(periods),
        years,
        sum(item.turnover for item in periods),
        sum(item.cost for item in periods),
        _compound([item.gross_return for item in periods]),
        _compound([item.benchmark_return for item in periods]),
        _compound(net),
        _sharpe(net, policy.periods_per_year),
        _compound(double_cost),
        _sharpe(double_cost, policy.periods_per_year),
        _drawdown(net),
        capacity,
        capacity >= policy.initial_nav_cny,
    )
