"""Bounded immutable research extracts; selection never queries future labels."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import asdict
from datetime import date
from pathlib import Path

from stephen_quant.baseline.stateful import StatefulBar
from stephen_quant.discovery.reliable_research import ResearchDay
from stephen_quant.discovery.search_power_dsl import sha256_json

from .data_warehouse import _duckdb
from .multisource_warehouse import _quote
from .qd_alternative import SOURCE_FIELDS
from .qd_csv_adapter import _open_tradability


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def freeze_inputs(root: Path, output: Path, *, start="2021-10-01", end="2024-12-31"):
    if date.fromisoformat(end) >= date(2025, 1, 1) or date.fromisoformat(start) < date(2021, 1, 1):
        raise ValueError("research extract outside authorized historical dates")
    output.mkdir(parents=True, exist_ok=False)
    conn = _duckdb().connect(str(root / "catalog/warehouse.duckdb"), read_only=True)
    ledger = []

    def extract(name, query, parameters):
        path = output / f"{name}.parquet"
        # COPY to a new artifact only; current warehouse and source archives remain read-only.
        escaped = str(path).replace("'", "''")
        conn.execute(
            f"COPY ({query}) TO '{escaped}' (FORMAT PARQUET, COMPRESSION ZSTD)", parameters
        )
        count, low, high = conn.execute(
            "SELECT count(*),min(trade_date),max(trade_date) FROM read_parquet(?)", [str(path)]
        ).fetchone()
        if count and (str(low) < start or str(high) > end):
            raise ValueError("extract exposed unauthorized dates")
        item = {
            "source": name,
            "file": path.name,
            "sha256": file_sha(path),
            "rows": count,
            "min_date": str(low),
            "max_date": str(high),
            "authorized_start": start,
            "authorized_end": end,
            "query_sha256": hashlib.sha256(query.encode()).hexdigest(),
        }
        ledger.append(item)
        print(json.dumps({"stage": "snapshot", **item}), flush=True)

    try:
        extract(
            "daily",
            "SELECT trade_date,instrument,name,open,close,amount,volume,"
            "adjustment_factor,available_at FROM qd_daily_current "
            "WHERE trade_date BETWEEN ? AND ? ORDER BY trade_date,instrument",
            [start, end],
        )
        extract(
            "minute",
            "SELECT trade_date,instrument,late_30_return,realized_volatility,"
            "amihud_intraday FROM qd_minute_features_current "
            "WHERE trade_date BETWEEN ? AND ? AND NOT sealed ORDER BY trade_date,instrument",
            [start, end],
        )
        wanted = {
            "fund_flow": ("net_inflow_amount",),
            "chip": ("chip_cost_15", "chip_cost_85", "chip_weighted_cost"),
            "auction": ("auction_return",),
        }
        for kind, fields in wanted.items():
            paths = [
                str(root / row[0])
                for row in conn.execute(
                    "SELECT parquet_relative_path FROM multisource_partitions WHERE active "
                    "AND dataset=? AND min_date<=? AND max_date>=? ORDER BY parquet_relative_path",
                    [f"qd_{kind}", end, start],
                ).fetchall()
            ]
            if not paths:
                raise ValueError(f"missing source partitions: {kind}")
            projections = []
            for field in fields:
                spec = SOURCE_FIELDS[kind][field]
                projections.append(
                    f"try_cast({_quote(spec.column)} AS DOUBLE)*{spec.scale} AS {field}"
                )
            extract(
                kind,
                "SELECT _trade_date AS trade_date,upper(_entity_id) AS instrument,"
                "_available_at AS available_at,"
                + ",".join(projections)
                + " FROM read_parquet(?,union_by_name=true) WHERE _trade_date BETWEEN ? AND ? "
                "ORDER BY _trade_date,instrument",
                [paths, start, end],
            )
    finally:
        conn.close()
    manifest = {
        "sources": ledger,
        "snapshot_sha256": sha256_json(ledger),
        "exposed_sealed_rows": sum(x["rows"] for x in ledger if x["max_date"] > end),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def load_frozen_days(folder: Path):
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if sha256_json(manifest["sources"]) != manifest["snapshot_sha256"]:
        raise ValueError("frozen manifest hash changed")
    if {s["source"] for s in manifest["sources"]} != {
        "daily",
        "minute",
        "fund_flow",
        "chip",
        "auction",
    }:
        raise ValueError("unexpected source set")
    for source in manifest["sources"]:
        if source["file"] != source["source"] + ".parquet":
            raise ValueError("unexpected source filename")
        if file_sha(folder / source["file"]) != source["sha256"]:
            raise ValueError("frozen source hash changed")
    conn = _duckdb().connect(":memory:")
    for source in manifest["sources"]:
        escaped = str(folder / source["file"]).replace("'", "''")
        conn.execute(f"CREATE VIEW {source['source']} AS SELECT * FROM read_parquet('{escaped}')")
    for source in manifest["sources"]:
        high = conn.execute(f"SELECT max(trade_date) FROM {source['source']}").fetchone()[0]
        if high is not None and str(high) >= "2025-01-01":
            raise ValueError("frozen input contains restricted dates")
        duplicate = conn.execute(
            f"SELECT count(*) FROM (SELECT trade_date,instrument FROM "
            f"{source['source']} GROUP BY ALL HAVING count(*)>1)"
        ).fetchone()[0]
        if duplicate:
            raise ValueError(f"duplicate daily keys in {source['source']}")
    query = """
    WITH d AS (
      SELECT *,lag(close,1) OVER w previous_raw_close,
        close*adjustment_factor / nullif(lag(close*adjustment_factor,20) OVER w,0) -1 ret_20,
        ln(CASE WHEN close*adjustment_factor>0 AND lag(close*adjustment_factor,1) OVER w>0
           THEN close*adjustment_factor / lag(close*adjustment_factor,1) OVER w END) log_return,
        avg(amount*1000) OVER w60 adv60,count(amount) OVER w60 history
      FROM daily WINDOW w AS(PARTITION BY instrument ORDER BY trade_date),
        w60 AS(PARTITION BY instrument ORDER BY trade_date ROWS BETWEEN59 PRECEDING AND CURRENT ROW)
    ), features AS (
      SELECT *,stddev_samp(log_return) OVER(PARTITION BY instrument ORDER BY trade_date
        ROWS BETWEEN19 PRECEDING AND CURRENT ROW) volatility_20,
        lag(adv60,1) OVER(PARTITION BY instrument ORDER BY trade_date) execution_adv
      FROM d
    )
    SELECT CAST(d.trade_date AS VARCHAR),d.instrument,d.name,d.open,d.close,d.adjustment_factor,
      d.amount,d.volume,d.previous_raw_close,d.execution_adv,d.adv60,d.history,d.ret_20,
      d.volatility_20,f.net_inflow_amount / nullif(d.amount*1000,0),
      (c.chip_cost_85-c.chip_cost_15)/nullif(c.chip_weighted_cost,0),
      m.late_30_return,m.realized_volatility,m.amihud_intraday,a.auction_return,
      d.available_at,f.available_at,c.available_at,a.available_at
    FROM features d LEFT JOIN fund_flow f USING(trade_date,instrument)
      LEFT JOIN chip c USING(trade_date,instrument)
      LEFT JOIN minute m USING(trade_date,instrument)
      LEFT JOIN auction a USING(trade_date,instrument)
    WHERE d.trade_date>=DATE '2022-01-01' ORDER BY d.trade_date,d.instrument
    """.replace("BETWEEN59", "BETWEEN 59").replace("BETWEEN19", "BETWEEN 19")
    cursor = conn.execute(query)
    frames = []
    day, features, bars = "", {}, []
    quality = defaultdict(int)
    # All features are used no earlier than next-session open. Vendor timestamps remain
    # provenance, not evidence of live first-seen availability.
    from datetime import datetime, timezone

    for batch in iter(lambda: cursor.fetchmany(25_000), []):
        for row in batch:
            row = row[:3] + tuple(float(v) if v is not None else None for v in row[3:20]) + row[20:]
            (
                dt,
                symbol,
                name,
                op,
                close,
                factor,
                amount,
                volume,
                prior,
                execution_adv,
                adv,
                history,
            ) = row[:12]
            if day and dt != day:
                if not bars:
                    raise ValueError("empty market session")
                frames.append(ResearchDay(day, features, tuple(bars)))
                features, bars = {}, []
            day = dt
            valid = all(v is not None and math.isfinite(v) and v > 0 for v in (op, close, factor))
            if valid:
                buy = sell = False
                reason = "missing_metadata"
                if prior and name:
                    code = (
                        symbol
                        if "." in symbol
                        else symbol
                        + (
                            ".SH"
                            if symbol.startswith("6")
                            else ".BJ"
                            if symbol[0] in "48"
                            else ".SZ"
                        )
                    )
                    try:
                        buy, sell, reason = _open_tradability(code, name, dt, op, prior)
                    except ValueError:
                        reason = "unsupported_board"
                    if reason == "no_price_limit_inferred":
                        buy = sell = False
                        reason = "uncertain_price_limit_reference"
                if not volume or not amount:
                    buy = sell = False
                    reason = "no_reported_trades"
                cap = max(0.0, (execution_adv or 0.0) * 0.05)
                bars.append(
                    StatefulBar(
                        dt,
                        symbol,
                        op * factor,
                        close * factor,
                        cap,
                        f"{dt}T08:00:00+08:00",
                        buy,
                        sell,
                        False,
                        reason,
                    )
                )
                quality[reason] += 1
            else:
                quality["invalid_bar_accounted_as_missing"] += 1
            # Entry eligibility uses current/past observed features, never execution/exit prices.
            if adv is None or adv < 10_000_000 or history < 20 or not name or "ST" in name.upper():
                continue
            cutoff = datetime.fromisoformat(f"{dt}T23:59:59+08:00")
            times = row[20:24]
            available = []
            for timestamp in times:
                if timestamp is None:
                    available.append(False)
                else:
                    if isinstance(timestamp, datetime):
                        value = timestamp
                    else:
                        text = timestamp.replace(" ", "T")
                        if len(text) >= 3 and text[-3] in "+-":
                            text += ":00"
                        value = datetime.fromisoformat(text)
                    if value.tzinfo is None:
                        value = value.replace(tzinfo=timezone.utc)
                    available.append(value <= cutoff)
            if not available[0]:
                quality["daily_not_available"] += 1
                continue
            vals = {
                "ret_20": row[12],
                "volatility_20": row[13],
                "liquidity": adv,
                "net_inflow_ratio": row[14] if available[1] else None,
                "concentration": row[15] if available[2] else None,
                "late_30_return": row[16],
                "realized_volatility": row[17],
                "amihud_intraday": row[18],
                "auction_return": row[19] if available[3] else None,
            }
            features[symbol] = {
                k: float(v) for k, v in vals.items() if v is not None and math.isfinite(v)
            }
    if bars:
        frames.append(ResearchDay(day, features, tuple(bars)))
    conn.close()
    return tuple(frames), dict(quality)


def daily_evidence(report):
    """Bounded machine evidence without raw source rows."""
    for period in report.periods:
        yield {
            "date": period.trade_date,
            "nav": period.end_nav,
            "return": period.net_return,
            "cash": period.cash,
            "cost": period.total_cost,
            "stale_positions": period.stale_position_days,
            "writeoff_loss": period.writeoff_loss,
            "positions": [asdict(m) for m in period.marks],
            "orders": [asdict(o) for o in period.orders],
        }
