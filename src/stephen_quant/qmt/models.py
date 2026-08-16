from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class QmtDailyBar:
    instrument: str
    trade_date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    adjustment_factor: float = 1.0
    can_buy_open: bool = True
    can_sell_open: bool = True
    tradability_reason: str = "unrestricted"


@dataclass(frozen=True)
class QmtDataAudit:
    adapter_version: str
    source_path: str
    source_sha256: str
    encoding: str
    adjustment: str
    column_mapping: dict[str, str]
    rows: int
    instruments: int
    start_date: str
    end_date: str
    zero_volume_bars: int
    warnings: tuple[str, ...]
    source_files: int = 1
    unit_conversions: dict[str, float] = field(default_factory=dict)
    open_upper_limit_bars: int = 0
    open_lower_limit_bars: int = 0
    tradability_unavailable_bars: int = 0
    no_price_limit_bars: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)


@dataclass(frozen=True)
class QmtDataset:
    bars: tuple[QmtDailyBar, ...]
    audit: QmtDataAudit


class QmtDataError(ValueError):
    """Raised when a QMT export cannot satisfy the daily-bar data contract."""
