from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime

from stephen_quant.baseline import BaselineObservation
from stephen_quant.factors import FactorDefinition
from stephen_quant.research_agent.dsl import FormulaInput, evaluate_formula
from stephen_quant.research_agent.models import ResearchAgentError

from .models import QmtDailyBar, QmtDataError
from .qd_alternative import AlternativeObservation

DAILY_FIELDS = {"open", "high", "low", "close", "volume", "amount"}


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def build_alternative_factor_observations(
    source: Sequence[AlternativeObservation],
    definition: FactorDefinition,
    anchors: Sequence[BaselineObservation],
) -> tuple[BaselineObservation, ...]:
    """Evaluate an alternative-data DSL factor against price-labelled anchor rows."""

    if not source or not anchors:
        raise QmtDataError("alternative factor requires source and anchor observations")
    kinds = {row.source_kind for row in source}
    if len(kinds) != 1:
        raise QmtDataError("alternative factor source must contain exactly one source kind")
    available_fields = {field for row in source for field, _ in row.values}
    unsupported = set(definition.required_fields) - available_fields
    if unsupported:
        raise QmtDataError(
            f"factor {definition.key} requires unavailable alternative fields: {sorted(unsupported)}"
        )

    source_by_instrument: dict[str, list[AlternativeObservation]] = defaultdict(list)
    anchors_by_instrument: dict[str, list[BaselineObservation]] = defaultdict(list)
    for row in source:
        source_by_instrument[row.instrument].append(row)
    for row in anchors:
        anchors_by_instrument[row.instrument].append(row)
    built: list[BaselineObservation] = []
    for instrument in sorted(anchors_by_instrument):
        history = sorted(
            source_by_instrument.get(instrument, ()),
            key=lambda row: _time(row.available_at),
        )
        instrument_anchors = sorted(
            anchors_by_instrument[instrument], key=lambda row: _time(row.execution_at)
        )
        visible: list[AlternativeObservation] = []
        offset = 0
        for anchor in instrument_anchors:
            decision = _time(anchor.execution_at)
            while offset < len(history) and _time(history[offset].available_at) < decision:
                visible.append(history[offset])
                offset += 1
            if not visible:
                built.append(
                    BaselineObservation(
                        instrument=anchor.instrument,
                        signal=0.0,
                        signal_at=anchor.signal_at,
                        signal_available_at=anchor.signal_available_at,
                        average_daily_value=anchor.average_daily_value,
                        liquidity_available_at=anchor.liquidity_available_at,
                        execution_at=anchor.execution_at,
                        return_end_at=anchor.return_end_at,
                        forward_return=anchor.forward_return,
                        can_buy_open=anchor.can_buy_open,
                        can_sell_open=anchor.can_sell_open,
                        tradability_reason=anchor.tradability_reason,
                        eligible=False,
                    )
                )
                continue
            latest = visible[-1]
            expected_source_date = (
                anchor.execution_at[:10]
                if latest.source_kind == "auction"
                else anchor.signal_at[:10]
            )
            usable = (
                len(visible) >= definition.minimum_observations
                and latest.trade_date == expected_source_date
            )
            signal = 0.0
            if usable:
                formula_history = visible[-definition.minimum_observations :]
                inputs = {
                    field: FormulaInput(
                        values=tuple(row.value(field) for row in formula_history),
                        available_at=tuple(row.available_at for row in formula_history),
                    )
                    for field in definition.required_fields
                }
                try:
                    signal = evaluate_formula(
                        definition.formula, inputs, decision_at=anchor.execution_at
                    )
                except ResearchAgentError:
                    usable = False
            built.append(
                BaselineObservation(
                    instrument=anchor.instrument,
                    signal=signal,
                    signal_at=latest.effective_at,
                    signal_available_at=latest.available_at,
                    average_daily_value=anchor.average_daily_value,
                    liquidity_available_at=anchor.liquidity_available_at,
                    execution_at=anchor.execution_at,
                    return_end_at=anchor.return_end_at,
                    forward_return=anchor.forward_return,
                    can_buy_open=anchor.can_buy_open,
                    can_sell_open=anchor.can_sell_open,
                    tradability_reason=anchor.tradability_reason,
                    eligible=anchor.eligible and usable,
                )
            )
    if not built:
        raise QmtDataError(f"factor {definition.key} produced no point-in-time observations")
    built.sort(key=lambda row: (row.execution_at, row.instrument))
    return tuple(built)


def build_multisource_factor_observations(
    bars: Sequence[QmtDailyBar],
    alternatives: dict[str, Sequence[AlternativeObservation]],
    definition: FactorDefinition,
    anchors: Sequence[BaselineObservation],
) -> tuple[BaselineObservation, ...]:
    """Evaluate a safe-DSL factor over daily bars and one or more PIT sources.

    Each field is sliced independently to information strictly available before the
    execution timestamp.  Same-day auction data is therefore usable after 09:26,
    while close-derived and end-of-day alternative data remain prior-session only.
    """

    if not bars or not anchors:
        raise QmtDataError("multi-source factor requires daily bars and anchor observations")
    compiled_fields = set(definition.required_fields)
    available_alternative_fields = {
        field for rows in alternatives.values() for row in rows for field, _ in row.values
    }
    unsupported = compiled_fields - DAILY_FIELDS - available_alternative_fields
    if unsupported:
        raise QmtDataError(
            f"factor {definition.key} requires unavailable multi-source fields: "
            f"{sorted(unsupported)}"
        )

    daily_by_instrument: dict[str, list[QmtDailyBar]] = defaultdict(list)
    alternative_by_field: dict[str, dict[str, list[AlternativeObservation]]] = defaultdict(
        lambda: defaultdict(list)
    )
    kinds_by_field: dict[str, str] = {}
    anchors_by_instrument: dict[str, list[BaselineObservation]] = defaultdict(list)
    for bar in bars:
        daily_by_instrument[bar.instrument].append(bar)
    for rows in alternatives.values():
        for row in rows:
            for field, _ in row.values:
                alternative_by_field[field][row.instrument].append(row)
                previous = kinds_by_field.setdefault(field, row.source_kind)
                if previous != row.source_kind:
                    raise QmtDataError(f"alternative field {field} has ambiguous source kinds")
    for row in anchors:
        anchors_by_instrument[row.instrument].append(row)

    built: list[BaselineObservation] = []
    for instrument in sorted(anchors_by_instrument):
        daily = sorted(daily_by_instrument.get(instrument, ()), key=lambda row: row.trade_date)
        daily_available = [
            _time(f"{row.trade_date}T15:01:00+08:00") for row in daily
        ]
        alt_history = {
            field: sorted(rows.get(instrument, ()), key=lambda row: _time(row.available_at))
            for field, rows in alternative_by_field.items()
        }
        alt_available = {
            field: [_time(row.available_at) for row in rows]
            for field, rows in alt_history.items()
        }
        for anchor in sorted(
            anchors_by_instrument[instrument], key=lambda row: _time(row.execution_at)
        ):
            decision = _time(anchor.execution_at)
            inputs: dict[str, FormulaInput] = {}
            usable = anchor.eligible
            latest_effective = anchor.signal_at
            latest_available = anchor.signal_available_at
            for field in definition.required_fields:
                if field in DAILY_FIELDS:
                    offset = bisect_left(daily_available, decision)
                    if offset < definition.minimum_observations:
                        usable = False
                        break
                    selected = daily[offset - definition.minimum_observations : offset]
                    inputs[field] = FormulaInput(
                        values=tuple(getattr(row, field) for row in selected),
                        available_at=tuple(
                            f"{row.trade_date}T15:01:00+08:00" for row in selected
                        ),
                    )
                    continue
                history = alt_history.get(field, ())
                offset = bisect_left(alt_available.get(field, ()), decision)
                if offset < definition.minimum_observations:
                    usable = False
                    break
                latest = history[offset - 1]
                expected_date = (
                    anchor.execution_at[:10]
                    if kinds_by_field[field] == "auction"
                    else anchor.signal_at[:10]
                )
                if latest.trade_date != expected_date:
                    usable = False
                    break
                selected = history[offset - definition.minimum_observations : offset]
                inputs[field] = FormulaInput(
                    values=tuple(row.value(field) for row in selected),
                    available_at=tuple(row.available_at for row in selected),
                )
                if _time(latest.available_at) > _time(latest_available):
                    latest_effective = latest.effective_at
                    latest_available = latest.available_at
            signal = 0.0
            if usable:
                try:
                    signal = evaluate_formula(
                        definition.formula, inputs, decision_at=anchor.execution_at
                    )
                except ResearchAgentError:
                    usable = False
            built.append(
                BaselineObservation(
                    instrument=anchor.instrument,
                    signal=signal,
                    signal_at=latest_effective,
                    signal_available_at=latest_available,
                    average_daily_value=anchor.average_daily_value,
                    liquidity_available_at=anchor.liquidity_available_at,
                    execution_at=anchor.execution_at,
                    return_end_at=anchor.return_end_at,
                    forward_return=anchor.forward_return,
                    can_buy_open=anchor.can_buy_open,
                    can_sell_open=anchor.can_sell_open,
                    tradability_reason=anchor.tradability_reason,
                    eligible=usable,
                )
            )
    if not built:
        raise QmtDataError(f"factor {definition.key} produced no point-in-time observations")
    built.sort(key=lambda row: (row.execution_at, row.instrument))
    return tuple(built)
