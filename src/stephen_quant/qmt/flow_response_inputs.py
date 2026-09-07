"""Read only the two explicitly scoped files from the inherited frozen extract.

This reader is not an epoch authorization. The runner must reserve all Trials and
verify its preregistration before calling it. Tests use synthetic Parquet only.
"""

from __future__ import annotations

import json
from pathlib import Path

from stephen_quant.discovery.flow_response_series import validate_calendar
from stephen_quant.discovery.search_power_dsl import sha256_json

from .data_warehouse import _duckdb
from .reliable_panel import file_sha

FIELDS = {
    "daily": (
        "trade_date",
        "instrument",
        "name",
        "open",
        "close",
        "amount",
        "volume",
        "adjustment_factor",
        "available_at",
    ),
    "fund_flow": ("trade_date", "instrument", "net_inflow_amount", "available_at"),
}
MANIFEST_SOURCES = {"daily", "fund_flow", "auction", "chip", "minute"}


def load_response_sources(folder, *, expected_manifest_sha256, calendar):
    validate_calendar(calendar)
    if (
        not isinstance(expected_manifest_sha256, str)
        or len(expected_manifest_sha256) != 64
        or any(c not in "0123456789abcdef" for c in expected_manifest_sha256)
    ):
        raise ValueError("frozen parent manifest SHA256 required")
    root = Path(folder).resolve(strict=True)
    manifest_path = root / "manifest.json"
    if manifest_path.resolve(strict=True).parent != root:
        raise ValueError("manifest escaped frozen input directory")
    manifest = json.loads(manifest_path.read_bytes())
    sources = manifest["sources"]
    if (
        len(sources) != len(MANIFEST_SOURCES)
        or {s["source"] for s in sources} != MANIFEST_SOURCES
        or sha256_json(sources) != expected_manifest_sha256
        or manifest["snapshot_sha256"] != expected_manifest_sha256
        or manifest["exposed_sealed_rows"] != 0
    ):
        raise ValueError("inherited source manifest mismatch")
    declared = {s["source"]: s for s in sources}
    selected, files = {}, {}
    # Verify both allowed files before projecting any source values. No directory scan
    # and no existence/hash/open operation on auction, chip or minute files.
    for source in FIELDS:
        item = declared[source]
        if item["file"] != f"{source}.parquet":
            raise ValueError("unexpected response source filename")
        path = root / item["file"]
        if path.resolve(strict=True).parent != root or file_sha(path) != item["sha256"]:
            raise ValueError("response source path/hash changed")
        files[source] = path
    conn = _duckdb().connect(":memory:")
    try:
        for source, path in files.items():
            count, low, high, null_keys = conn.execute(
                "SELECT count(*),min(trade_date),max(trade_date),"
                "count(*) FILTER(WHERE trade_date IS NULL OR instrument IS NULL) "
                "FROM read_parquet(?)",
                [str(path)],
            ).fetchone()
            item = declared[source]
            if (
                count != item["rows"]
                or not count
                or null_keys
                or str(low) != item["min_date"]
                or str(high) != item["max_date"]
                or str(low) < item["authorized_start"]
                or str(high) > item["authorized_end"]
                or str(high) >= "2025-01-01"
                or str(low) < "2021-01-01"
            ):
                raise ValueError("frozen source coverage metadata mismatch/restricted dates")
            duplicates = conn.execute(
                "SELECT count(*) FROM (SELECT trade_date,instrument FROM read_parquet(?) "
                "GROUP BY ALL HAVING count(*)>1)",
                [str(path)],
            ).fetchone()[0]
            if duplicates:
                raise ValueError("duplicate frozen source key")
        for source, path in files.items():
            columns = FIELDS[source]
            projection = ",".join(
                c
                if c in {"trade_date", "instrument", "name", "available_at"}
                else f"CAST({c} AS DOUBLE) AS {c}"
                for c in columns
            )
            # The inherited file may contain 2021 warmup: do not project those
            # numeric values under this bounded 2022-2024 response protocol.
            values = conn.execute(
                f"SELECT {projection} FROM read_parquet(?) "
                "WHERE trade_date BETWEEN DATE '2022-01-01' AND DATE '2024-12-31' "
                "ORDER BY trade_date,instrument",
                [str(path)],
            ).fetchall()
            rows = [dict(zip(columns, row, strict=True)) for row in values]
            for row in rows:
                row["trade_date"] = str(row["trade_date"])
            selected[source] = rows
    finally:
        conn.close()
    days = sorted({r["trade_date"] for r in selected["daily"]})
    allowed_dates = set(calendar)
    if days != list(calendar) or any(
        r["trade_date"] not in allowed_dates for r in selected["fund_flow"]
    ):
        raise ValueError("source rows disagree with explicit global calendar")
    return selected, {
        "parent_snapshot_sha256": expected_manifest_sha256,
        "read_sources": list(FIELDS),
        "source_sha256": {s: declared[s]["sha256"] for s in FIELDS},
        "projected_rows": {s: len(selected[s]) for s in FIELDS},
        "numeric_projection": "DOUBLE; source Decimal/integers normalized for finite math",
        "calendar_sha256": sha256_json(list(calendar)),
        "warmup_numeric_rows_read": 0,
        "sealed_numeric_rows_read": 0,
        "validated_alpha": False,
    }
