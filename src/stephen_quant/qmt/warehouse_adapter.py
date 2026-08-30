from __future__ import annotations

from datetime import date
from pathlib import Path

from .data_warehouse import _duckdb, verify_snapshot
from .models import QmtDailyBar, QmtDataAudit, QmtDataError, QmtDataset
from .qd_csv_adapter import (
    AMOUNT_THOUSAND_CNY_TO_CNY,
    VOLUME_LOT_TO_SHARE,
    _open_tradability,
    _validate_bar,
)

WAREHOUSE_ADAPTER_VERSION = "qd-duckdb-research-adapter-1.0.0"


def _require_current_snapshot_reference(warehouse: Path, snapshot_id: str) -> None:
    connection = _duckdb().connect(
        str(warehouse / "catalog" / "warehouse.duckdb"), read_only=True
    )
    try:
        row = connection.execute(
            "SELECT snapshot_id FROM snapshots ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    finally:
        connection.close()
    if row is None or str(row[0]) != snapshot_id:
        raise QmtDataError("verified_snapshot_id is not the current warehouse snapshot")


def latest_warehouse_snapshot(warehouse_root: str | Path) -> str:
    warehouse = Path(warehouse_root).expanduser().resolve()
    catalog = warehouse / "catalog" / "warehouse.duckdb"
    if not catalog.is_file():
        raise QmtDataError(f"warehouse catalog is missing: {catalog}")
    connection = _duckdb().connect(str(catalog), read_only=True)
    try:
        row = connection.execute(
            "SELECT snapshot_id FROM snapshots ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise QmtDataError("warehouse contains no frozen snapshot")
    snapshot_id = str(row[0])
    verification = verify_snapshot(warehouse, snapshot_id)
    if not verification["passed"]:
        raise QmtDataError(
            "warehouse snapshot verification failed: " + "; ".join(verification["failures"])
        )
    return snapshot_id


def select_prior_liquidity_universe(
    warehouse_root: str | Path,
    *,
    start_date: str,
    end_date: str,
    top_n: int,
    minimum_sessions: int = 120,
    verified_snapshot_id: str | None = None,
) -> tuple[str, ...]:
    if date.fromisoformat(start_date) > date.fromisoformat(end_date):
        raise QmtDataError("universe start_date must not be after end_date")
    if top_n < 2 or minimum_sessions < 1:
        raise QmtDataError("top_n must be at least 2 and minimum_sessions must be positive")
    warehouse = Path(warehouse_root).expanduser().resolve()
    if verified_snapshot_id is None:
        latest_warehouse_snapshot(warehouse)
    else:
        _require_current_snapshot_reference(warehouse, verified_snapshot_id)
    connection = _duckdb().connect(
        str(warehouse / "catalog" / "warehouse.duckdb"), read_only=True
    )
    try:
        rows = connection.execute(
            'SELECT instrument, avg(amount) mean_amount FROM qd_daily_current '
            'WHERE trade_date BETWEEN ? AND ? AND amount > 0 '
            'GROUP BY instrument HAVING count(DISTINCT trade_date) >= ? '
            'ORDER BY mean_amount DESC, instrument LIMIT ?',
            [start_date, end_date, minimum_sessions, top_n],
        ).fetchall()
    finally:
        connection.close()
    if len(rows) < 2:
        raise QmtDataError("prior liquidity window produced fewer than two instruments")
    return tuple(str(row[0]).upper() for row in rows)


def load_qd_warehouse_daily(
    warehouse_root: str | Path,
    *,
    start_date: str,
    end_date: str,
    instruments: tuple[str, ...],
    adjustment: str = "back_ratio",
    verified_snapshot_id: str | None = None,
) -> QmtDataset:
    """Read a frozen QD daily snapshot through DuckDB without touching source archives."""

    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if start > end:
        raise QmtDataError("start_date must not be after end_date")
    declared_adjustment = adjustment.strip().lower()
    if declared_adjustment not in {"none", "back_ratio"}:
        raise QmtDataError("warehouse daily adapter supports only none or back_ratio adjustment")
    wanted = tuple(sorted({item.strip().upper() for item in instruments if item.strip()}))
    if not wanted:
        raise QmtDataError("warehouse daily adapter requires an explicit instrument universe")

    warehouse = Path(warehouse_root).expanduser().resolve()
    snapshot_id = verified_snapshot_id or latest_warehouse_snapshot(warehouse)
    if verified_snapshot_id is not None:
        _require_current_snapshot_reference(warehouse, verified_snapshot_id)
    connection = _duckdb().connect(
        str(warehouse / "catalog" / "warehouse.duckdb"), read_only=True
    )
    try:
        rows = connection.execute(
            'WITH selected AS (SELECT *, lag("close") OVER '
            '(PARTITION BY instrument ORDER BY trade_date) previous_close '
            'FROM qd_daily_current WHERE instrument IN (SELECT * FROM unnest(?))) '
            'SELECT instrument, CAST(trade_date AS VARCHAR), name, "open", high, low, '
            '"close", volume, amount, adjustment_factor, previous_close '
            'FROM selected WHERE trade_date BETWEEN ? AND ? ORDER BY trade_date, instrument',
            [list(wanted), start_date, end_date],
        ).fetchall()
    finally:
        connection.close()
    if not rows:
        raise QmtDataError("warehouse selection contains no daily bars")

    bars: list[QmtDailyBar] = []
    found: set[str] = set()
    unavailable = 0
    for number, row in enumerate(rows, start=1):
        instrument, trade_day, name = str(row[0]).upper(), str(row[1]), str(row[2] or "")
        raw_open = float(row[3])
        factor = float(row[9])
        if factor <= 0:
            raise QmtDataError(f"warehouse row {number}: adjustment_factor must be positive")
        scale = factor if declared_adjustment == "back_ratio" else 1.0
        previous_close = row[10]
        if previous_close is None or not name:
            can_buy, can_sell, reason = False, False, "missing_point_in_time_metadata"
            unavailable += 1
        else:
            limit_instrument = instrument
            if "." not in limit_instrument:
                exchange = "SH" if instrument.startswith("6") else "BJ" if instrument.startswith(("4", "8")) else "SZ"
                limit_instrument = f"{instrument}.{exchange}"
            can_buy, can_sell, reason = _open_tradability(
                limit_instrument, name, trade_day, raw_open, float(previous_close)
            )
        bar = QmtDailyBar(
            instrument=instrument,
            trade_date=trade_day,
            open=raw_open * scale,
            high=float(row[4]) * scale,
            low=float(row[5]) * scale,
            close=float(row[6]) * scale,
            volume=float(row[7]) * VOLUME_LOT_TO_SHARE,
            amount=float(row[8]) * AMOUNT_THOUSAND_CNY_TO_CNY,
            adjustment_factor=factor,
            can_buy_open=can_buy,
            can_sell_open=can_sell,
            tradability_reason=reason,
        )
        _validate_bar(bar, row_number=number)
        bars.append(bar)
        found.add(instrument)
    missing = sorted(set(wanted) - found)
    if missing:
        raise QmtDataError(f"warehouse is missing requested instruments: {missing}")
    days = [bar.trade_date for bar in bars]
    warnings = (
        "The instrument universe must be selected using information available before evaluation.",
        "Suspended sessions are sparse and must be handled by dynamic eligibility.",
    )
    return QmtDataset(
        tuple(bars),
        QmtDataAudit(
            adapter_version=WAREHOUSE_ADAPTER_VERSION,
            source_path=str(warehouse),
            source_sha256=snapshot_id,
            encoding="duckdb/parquet",
            adjustment=declared_adjustment,
            column_mapping={
                key: key
                for key in ("instrument", "trade_date", "open", "high", "low", "close", "volume", "amount")
            },
            rows=len(bars),
            instruments=len(found),
            start_date=min(days),
            end_date=max(days),
            zero_volume_bars=sum(bar.volume == 0 or bar.amount == 0 for bar in bars),
            warnings=warnings,
            source_files=1,
            unit_conversions={
                "volume_lot_to_share": VOLUME_LOT_TO_SHARE,
                "amount_thousand_cny_to_cny": AMOUNT_THOUSAND_CNY_TO_CNY,
            },
            open_upper_limit_bars=sum(bar.tradability_reason == "open_at_upper_limit" for bar in bars),
            open_lower_limit_bars=sum(bar.tradability_reason == "open_at_lower_limit" for bar in bars),
            tradability_unavailable_bars=unavailable,
            no_price_limit_bars=sum(bar.tradability_reason == "no_price_limit" for bar in bars),
        ),
    )
