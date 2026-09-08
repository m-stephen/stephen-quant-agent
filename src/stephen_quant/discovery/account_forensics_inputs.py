"""Bounded read-only frozen daily-row lookup; no ingestion, fitting or execution."""

from pathlib import Path

from stephen_quant.qmt.data_warehouse import _duckdb

from .account_forensics import day
from .account_forensics_evidence import bind_files
from .search_power_dsl import sha256_json

FIELDS = ("trade_date", "instrument", "name", "open", "close", "amount", "volume",
          "adjustment_factor", "available_at")


def execution_calendar(calendar, *, frozen):
    """Match every date to the plan hash, not merely the length and endpoints."""
    dates = [day(d) for d in calendar]
    if (dates != sorted(set(dates)) or len(dates) != 726
            or type(frozen["count"]) is not int or frozen["count"] != 726
            or sha256_json(dates) != frozen["sha256"]):
        raise ValueError("exact frozen726-session source calendar required")
    execution = [d for d in dates if d >= "2023-01-01"]
    if len(execution) != 484 or execution[0] != "2023-01-03" or execution[-1] != "2024-12-31":
        raise ValueError("exact frozen484-session execution calendar required")
    return execution


def event_source_keys(chain_reports):
    """Deduplicate source queries only; never deduplicate events across accounts."""
    keys = set()
    for report in chain_reports:
        for event in report["events"]:
            name, chain = event["instrument"], event["stale_chain"]
            keys.add((chain["last_marked_date"], name))
            keys.update((r["date"], name) for r in chain["missing_sessions"])
            if event["event_type"] == "recovery":
                keys.add((event["date"], name))
        for tail in report.get("open_stale_chains", []):
            name, chain = tail["instrument"], tail["stale_chain"]
            keys.add((chain["last_marked_date"], name))
            keys.update((r["date"], name) for r in chain["missing_sessions"])
    return sorted(keys)


def read_daily_lookups(binding, requested):
    """Actual row existence is established by a left-complete explicit query index.

    This function may run only inside the reviewed frozen forensic runtime. Its
    tests use synthetic Parquet. Returned None is verified query absence; missing
    columns or duplicate requested-source keys fail closed. It does not touch any
    other source file's values or scan directories.
    """
    if not requested:
        return {}, {"requested_keys": 0, "matched_rows": 0, "absent_keys": 0}
    if len(requested) > 50000 or len(set(requested)) != len(requested):
        raise ValueError("unique bounded explicit source keys required")
    for dt, name in requested:
        day(dt)
        if not isinstance(name, str) or not name or name.strip() != name:
            raise ValueError("canonical requested instrument required")
    if set(binding["files"]) != {"daily.parquet", "fund_flow.parquet", "manifest.json"}:
        raise ValueError("fixed daily/flow/manifest source bindings required")
    bind_files(binding["root"], binding["files"])
    path = Path(binding["root"]) / "daily.parquet"
    found, matched = dict.fromkeys(requested), set()
    with _duckdb().connect(":memory:") as db:
        db.execute("SET threads=1")
        db.execute("SET memory_limit='512MB'")
        db.execute("SET max_temp_directory_size='0B'")
        db.execute("CREATE TEMP TABLE requested(trade_date VARCHAR, instrument VARCHAR)")
        db.executemany("INSERT INTO requested VALUES (?,?)", requested)
        projection = ",".join('p."' + c + '"' for c in FIELDS)
        cursor = db.execute(
            f"SELECT {projection} FROM read_parquet(?) p JOIN requested r "
            "ON cast(p.trade_date AS VARCHAR)=r.trade_date AND p.instrument=r.instrument "
            "ORDER BY p.trade_date,p.instrument", [str(path)])
        while chunk := cursor.fetchmany(2048):
            for values in chunk:
                row = dict(zip(FIELDS, values, strict=True))
                row["trade_date"] = str(row["trade_date"])
                key = row["trade_date"], row["instrument"]
                if key not in found or key in matched:
                    raise ValueError("unrequested or duplicate frozen source key")
                found[key] = row
                matched.add(key)
    bind_files(binding["root"], binding["files"])
    return found, {"requested_keys": len(requested), "matched_rows": len(matched),
                   "absent_keys": len(requested) - len(matched),
                   "query_projection": list(FIELDS), "input_bytes_unchanged": True}
