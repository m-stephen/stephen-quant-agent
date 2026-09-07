"""Replayable, day-bounded bar projections over an already verified history.

These adapters do not verify or authorize source data. Callers retain the native
and actual-byte checks before use. No returns, filters or allocation are computed
here: the same StatefulBar constructor is applied in the original record order.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from stephen_quant.baseline.stateful import StatefulBar


class _DayBars(Mapping):
    __slots__ = ("_rows",)

    def __init__(self, rows):
        self._rows = rows

    def __getitem__(self, name):
        return StatefulBar(**self._rows[name])

    def __iter__(self):
        return iter(self._rows)

    def __len__(self):
        return len(self._rows)


class HistoricalBarMapping(Mapping):
    """Expose only explicit prefix dates without materializing a second panel."""

    __slots__ = ("_allowed", "_bars", "_days")

    def __init__(self, bars, days):
        self._bars, self._days = bars, tuple(days)
        self._allowed = frozenset(self._days)
        if len(self._allowed) != len(self._days):
            raise ValueError("unique explicit bar-view dates required")
        if any(d not in bars for d in self._days):
            raise ValueError("bar-view date missing from history")

    def __getitem__(self, day):
        if day not in self._allowed:
            raise KeyError(day)  # Before accessing an out-of-prefix numeric row.
        return _DayBars(self._bars[day])

    def __iter__(self):
        return iter(self._days)

    def __len__(self):
        return len(self._days)


class HistoricalSessions(Sequence):
    """Repeatable execution sessions; no retained second matrix of bar objects.

    Iterators can briefly hold the previous and current day at once. Callers
    which explicitly collect this sequence can still materialize the full panel.
    The underlying verified history itself remains in memory.
    """

    __slots__ = ("_days", "_mapping")

    def __init__(self, bars, days):
        self._mapping = HistoricalBarMapping(bars, days)
        self._days = self._mapping._days

    def __getitem__(self, index):
        if isinstance(index, slice):
            return HistoricalSessions(self._mapping._bars, self._days[index])
        rows = self._mapping[self._days[index]]
        return tuple(rows.values())

    def __len__(self):
        return len(self._days)

    def __eq__(self, other):
        if not isinstance(other, Sequence):
            return NotImplemented
        return len(self) == len(other) and all(a == b for a, b in zip(self, other, strict=True))
