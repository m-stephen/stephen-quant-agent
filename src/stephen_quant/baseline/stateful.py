from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .models import BaselineError

STATEFUL_EXECUTION_VERSION = "stateful-dynamic-universe-execution-1.0.0"


@dataclass(frozen=True)
class StatefulBar:
    trade_date: str
    instrument: str
    open_price: float
    close_price: float
    capacity_cny: float
    capacity_available_at: str
    can_buy_open: bool = True
    can_sell_open: bool = True
    forced_exit: bool = False
    tradability_reason: str = "unrestricted"


@dataclass(frozen=True)
class TargetAllocation:
    trade_date: str
    decided_at: str
    weights: dict[str, float]
    rebalance: bool = True
    forced_exits: tuple[str, ...] = ()


@dataclass(frozen=True)
class StatefulExecutionConfig:
    maximum_position_weight: float = 0.20
    commission_bps: float = 3.0
    sell_tax_bps: float = 5.0
    slippage_bps: float = 5.0
    stale_writeoff_sessions: int = 20


@dataclass(frozen=True)
class PositionMark:
    instrument: str
    shares: float
    mark_price: float
    market_value: float
    stale_sessions: int
    source: str


@dataclass(frozen=True)
class StatefulOrder:
    instrument: str
    desired_notional: float
    capacity_notional: float
    executed_notional: float
    blocked_notional: float
    total_cost: float
    reason: str


@dataclass(frozen=True)
class StatefulPeriod:
    trade_date: str
    previous_nav: float
    open_nav: float
    end_nav: float
    net_return: float | None
    overnight_mark_return: float | None
    cash: float
    total_cost: float
    stale_position_days: int
    writeoff_positions: int
    writeoff_loss: float
    recovery_positions: int
    recovery_value: float
    marks: tuple[PositionMark, ...]
    orders: tuple[StatefulOrder, ...]


@dataclass(frozen=True)
class StatefulMetrics:
    periods: int
    initial_nav: float
    final_nav: float
    net_total_return: float
    max_drawdown: float
    total_cost: float
    blocked_orders: int
    blocked_notional: float
    stale_position_days: int
    writeoff_events: int
    writeoff_loss: float
    recovery_events: int
    recovery_value: float


@dataclass(frozen=True)
class StatefulExecutionReport:
    method_version: str
    config: StatefulExecutionConfig
    metrics: StatefulMetrics
    periods: tuple[StatefulPeriod, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self) -> str:
        metrics = self.metrics
        return "\n".join(
            (
                "# Stateful dynamic-universe execution audit",
                "",
                f"- Method: `{self.method_version}`",
                f"- Periods: {metrics.periods}",
                f"- Final NAV: {metrics.final_nav:.2f}",
                f"- Net total return: {metrics.net_total_return:.6f}",
                f"- Maximum drawdown: {metrics.max_drawdown:.6f}",
                f"- Total cost: {metrics.total_cost:.2f}",
                f"- Blocked orders: {metrics.blocked_orders}",
                f"- Stale position-days: {metrics.stale_position_days}",
                f"- Write-off events: {metrics.writeoff_events}",
                f"- Recovery events: {metrics.recovery_events}",
                "",
            )
        )


@dataclass(frozen=True)
class StatefulExecutionArtifacts:
    json_path: Path
    markdown_path: Path
    json_sha256: str
    markdown_sha256: str


@dataclass
class _Position:
    shares: float
    last_close: float
    stale_sessions: int = 0
    written_down: bool = False


def _timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BaselineError(f"invalid timestamp: {value}") from exc


def _cost(notional: float, config: StatefulExecutionConfig) -> float:
    absolute = abs(notional)
    commission = absolute * config.commission_bps / 10_000
    sell_tax = absolute * config.sell_tax_bps / 10_000 if notional < 0 else 0.0
    slippage = absolute * config.slippage_bps / 10_000
    return commission + sell_tax + slippage


def _validate(
    sessions: tuple[tuple[StatefulBar, ...], ...],
    targets: tuple[TargetAllocation, ...],
    config: StatefulExecutionConfig,
) -> None:
    if not sessions or len(sessions) != len(targets):
        raise BaselineError("stateful execution requires one target for every non-empty session")
    if not 0 < config.maximum_position_weight <= 1:
        raise BaselineError("maximum_position_weight must be in (0, 1]")
    if config.stale_writeoff_sessions < 1:
        raise BaselineError("stale_writeoff_sessions must be positive")
    if any(value < 0 for value in (config.commission_bps, config.sell_tax_bps, config.slippage_bps)):
        raise BaselineError("execution costs cannot be negative")
    previous_date = ""
    for bars, target in zip(sessions, targets, strict=True):
        if not bars:
            raise BaselineError("stateful session cannot be empty")
        if target.trade_date <= previous_date:
            raise BaselineError("stateful sessions must be strictly chronological")
        if any(bar.trade_date != target.trade_date for bar in bars):
            raise BaselineError("bar and target dates must match")
        if len({bar.instrument for bar in bars}) != len(bars):
            raise BaselineError(f"duplicate instrument on {target.trade_date}")
        execution_at = _timestamp(f"{target.trade_date}T09:30:00+08:00")
        if _timestamp(target.decided_at) >= execution_at:
            raise BaselineError("target must be decided before the execution open")
        if any(weight < 0 or weight > config.maximum_position_weight for weight in target.weights.values()):
            raise BaselineError("target weight violates long-only position limits")
        if sum(target.weights.values()) > 1 + 1e-12:
            raise BaselineError("target weights cannot exceed one")
        for bar in bars:
            if (
                not bar.instrument
                or not math.isfinite(bar.open_price)
                or not math.isfinite(bar.close_price)
                or bar.open_price <= 0
                or bar.close_price <= 0
                or not math.isfinite(bar.capacity_cny)
                or bar.capacity_cny < 0
            ):
                raise BaselineError("stateful bar contains invalid prices or capacity")
            if _timestamp(bar.capacity_available_at) >= execution_at:
                raise BaselineError("capacity must be available before the execution open")
        previous_date = target.trade_date


def run_stateful_execution(
    sessions: tuple[tuple[StatefulBar, ...], ...],
    targets: tuple[TargetAllocation, ...],
    config: StatefulExecutionConfig,
    *,
    initial_nav: float = 1_000_000.0,
) -> StatefulExecutionReport:
    """Execute sparse daily panels without deleting or silently forward-filling holdings."""

    _validate(sessions, targets, config)
    if not math.isfinite(initial_nav) or initial_nav <= 0:
        raise BaselineError("initial_nav must be finite and positive")
    cash = float(initial_nav)
    positions: dict[str, _Position] = {}
    previous_nav = float(initial_nav)
    periods: list[StatefulPeriod] = []

    for bars, target in zip(sessions, targets, strict=True):
        by_instrument = {bar.instrument: bar for bar in bars}
        open_marks: dict[str, float] = {}
        mark_sources: dict[str, str] = {}
        writeoff_loss = 0.0
        writeoff_positions = 0
        recovery_value = 0.0
        recovery_positions = 0
        for instrument, position in positions.items():
            bar = by_instrument.get(instrument)
            if bar is not None:
                open_marks[instrument] = bar.open_price
                mark_sources[instrument] = "current_open"
                if position.written_down:
                    recovery_value += position.shares * bar.open_price
                    recovery_positions += 1
                position.stale_sessions = 0
                position.written_down = False
            else:
                position.stale_sessions += 1
                if position.stale_sessions >= config.stale_writeoff_sessions:
                    open_marks[instrument] = 0.0
                    mark_sources[instrument] = "conservative_zero_writeoff"
                    if not position.written_down:
                        writeoff_loss += position.shares * position.last_close
                        writeoff_positions += 1
                    position.written_down = True
                else:
                    open_marks[instrument] = position.last_close
                    mark_sources[instrument] = "explicit_stale_last_close"

        open_nav = cash + sum(
            position.shares * open_marks[instrument]
            for instrument, position in positions.items()
        )
        desired_weights = (
            dict(target.weights)
            if target.rebalance
            else {
                instrument: position.shares * open_marks[instrument] / open_nav
                for instrument, position in positions.items()
                if open_nav > 0
            }
        )
        for instrument in target.forced_exits:
            desired_weights.pop(instrument, None)
        for instrument, bar in by_instrument.items():
            if bar.forced_exit:
                desired_weights.pop(instrument, None)

        desired: dict[str, float] = {}
        original_desired: dict[str, float] = {}
        reasons: dict[str, str] = {}
        capacity: dict[str, float] = {}
        for instrument in sorted(set(positions) | set(desired_weights)):
            bar = by_instrument.get(instrument)
            current_value = positions[instrument].shares * open_marks[instrument] if instrument in positions else 0.0
            desired_value = desired_weights.get(instrument, 0.0) * open_nav
            notional = desired_value - current_value
            original_desired[instrument] = notional
            capacity[instrument] = bar.capacity_cny if bar is not None else 0.0
            if bar is None:
                desired[instrument] = 0.0
                reasons[instrument] = "missing_bar_suspension"
            elif (notional > 0 and not bar.can_buy_open) or (
                notional < 0 and not bar.can_sell_open
            ):
                desired[instrument] = 0.0
                reasons[instrument] = bar.tradability_reason
            else:
                desired[instrument] = (
                    math.copysign(min(abs(notional), bar.capacity_cny), notional)
                    if notional
                    else 0.0
                )
                if abs(desired[instrument]) + 1e-12 < abs(notional):
                    reasons[instrument] = "capacity_clipped"
                else:
                    reasons[instrument] = "executed" if desired[instrument] else "no_trade"

        executed: dict[str, float] = {}
        total_cost = 0.0
        for instrument in sorted(desired):
            notional = desired[instrument]
            if notional >= 0:
                continue
            bar = by_instrument[instrument]
            position = positions[instrument]
            notional = max(notional, -position.shares * bar.open_price)
            cost = _cost(notional, config)
            position.shares += notional / bar.open_price
            cash -= notional + cost
            total_cost += cost
            executed[instrument] = notional

        buys = {instrument: value for instrument, value in desired.items() if value > 0}
        buy_values = tuple(buys.values())

        def required(scale: float, values: tuple[float, ...] = buy_values) -> float:
            return sum(value * scale + _cost(value * scale, config) for value in values)

        scale = 1.0
        if required(1.0) > cash and buys:
            low, high = 0.0, 1.0
            for _ in range(80):
                middle = (low + high) / 2
                if required(middle) <= cash:
                    low = middle
                else:
                    high = middle
            scale = low
        for instrument in sorted(buys):
            bar = by_instrument[instrument]
            notional = buys[instrument] * scale
            cost = _cost(notional, config)
            position = positions.setdefault(
                instrument, _Position(shares=0.0, last_close=bar.open_price)
            )
            position.shares += notional / bar.open_price
            cash -= notional + cost
            total_cost += cost
            executed[instrument] = notional
            if scale < 1:
                reasons[instrument] = "funding_scaled"

        if cash < -1e-7:
            raise BaselineError("stateful execution created negative cash")
        cash = max(cash, 0.0)

        positions = {
            instrument: position
            for instrument, position in positions.items()
            if position.shares > 1e-12
        }
        marks: list[PositionMark] = []
        for instrument, position in sorted(positions.items()):
            bar = by_instrument.get(instrument)
            if bar is not None:
                position.last_close = bar.close_price
                position.stale_sessions = 0
                position.written_down = False
                mark_price = bar.close_price
                source = "current_close"
            else:
                mark_price = 0.0 if position.written_down else position.last_close
                source = mark_sources[instrument]
            marks.append(
                PositionMark(
                    instrument=instrument,
                    shares=position.shares,
                    mark_price=mark_price,
                    market_value=position.shares * mark_price,
                    stale_sessions=position.stale_sessions,
                    source=source,
                )
            )
        end_nav = cash + sum(mark.market_value for mark in marks)
        orders: list[StatefulOrder] = []
        for instrument in sorted(desired):
            actual = executed.get(instrument, 0.0)
            orders.append(
                StatefulOrder(
                    instrument=instrument,
                    desired_notional=original_desired[instrument],
                    capacity_notional=capacity[instrument],
                    executed_notional=actual,
                    blocked_notional=max(
                        abs(original_desired[instrument]) - abs(actual), 0.0
                    ),
                    total_cost=_cost(actual, config),
                    reason=reasons[instrument],
                )
            )
        periods.append(
            StatefulPeriod(
                trade_date=target.trade_date,
                previous_nav=previous_nav,
                open_nav=open_nav,
                end_nav=end_nav,
                net_return=end_nav / previous_nav - 1 if previous_nav > 0 else None,
                overnight_mark_return=(
                    open_nav / previous_nav - 1 if previous_nav > 0 else None
                ),
                cash=max(cash, 0.0),
                total_cost=total_cost,
                stale_position_days=sum(mark.stale_sessions > 0 for mark in marks),
                writeoff_positions=writeoff_positions,
                writeoff_loss=writeoff_loss,
                recovery_positions=recovery_positions,
                recovery_value=recovery_value,
                marks=tuple(marks),
                orders=tuple(orders),
            )
        )
        previous_nav = end_nav

    peak = initial_nav
    max_drawdown = 0.0
    for period in periods:
        peak = max(peak, period.end_nav)
        max_drawdown = min(max_drawdown, period.end_nav / peak - 1)
    orders = [order for period in periods for order in period.orders]
    metrics = StatefulMetrics(
        periods=len(periods),
        initial_nav=initial_nav,
        final_nav=periods[-1].end_nav,
        net_total_return=periods[-1].end_nav / initial_nav - 1,
        max_drawdown=max_drawdown,
        total_cost=sum(period.total_cost for period in periods),
        blocked_orders=sum(
            order.blocked_notional > 1e-9
            or order.reason not in {"executed", "no_trade"}
            for order in orders
        ),
        blocked_notional=sum(order.blocked_notional for order in orders),
        stale_position_days=sum(period.stale_position_days for period in periods),
        writeoff_events=sum(period.writeoff_positions for period in periods),
        writeoff_loss=sum(period.writeoff_loss for period in periods),
        recovery_events=sum(period.recovery_positions for period in periods),
        recovery_value=sum(period.recovery_value for period in periods),
    )
    return StatefulExecutionReport(
        method_version=STATEFUL_EXECUTION_VERSION,
        config=config,
        metrics=metrics,
        periods=tuple(periods),
    )


def _write(path: Path, content: str) -> str:
    path.write_text(content, encoding="utf-8", newline="\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def write_stateful_execution_report(
    report: StatefulExecutionReport, output_dir: str | Path
) -> StatefulExecutionArtifacts:
    directory = Path(output_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "stateful-execution.json"
    markdown_path = directory / "stateful-execution.md"
    return StatefulExecutionArtifacts(
        json_path=json_path,
        markdown_path=markdown_path,
        json_sha256=_write(json_path, report.to_json() + "\n"),
        markdown_sha256=_write(markdown_path, report.to_markdown()),
    )
