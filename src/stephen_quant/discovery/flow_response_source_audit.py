"""Read-only independent source/mathematical audit; no automatic promotion.

Native/hash verification shares infrastructure. Numerical source projection,
response/risk/rank/bar calculations are separate from production. Current history
loading is not bounded-memory; the *reference source scan* uses bounded batches.
"""

from __future__ import annotations

import hashlib
import json
import math
from contextlib import contextmanager
from pathlib import Path

import duckdb

from stephen_quant.qmt.reliable_panel import file_sha

from .flow_response_history import read_verified_history
from .flow_response_reference import reference_history
from .search_power_dsl import sha256_json

PROJECTION = {
    "daily": "trade_date,instrument,name,open,close,amount,volume,adjustment_factor,available_at",
    "fund_flow": "trade_date,instrument,net_inflow_amount,available_at",
}


@contextmanager
def source_streams(folder, *, manifest_sha256):
    root = Path(folder).resolve(strict=True)
    manifest_file = root / "manifest.json"
    if manifest_file.resolve(strict=True).parent != root:
        raise ValueError("audit manifest escaped source root")
    manifest = json.loads(manifest_file.read_bytes())
    declared = {s["source"]: s for s in manifest["sources"]}
    if (
        len(manifest["sources"]) != 5
        or set(declared) != {"daily", "fund_flow", "auction", "chip", "minute"}
        or sha256_json(manifest["sources"]) != manifest_sha256
        or manifest["snapshot_sha256"] != manifest_sha256
        or manifest["exposed_sealed_rows"] != 0
    ):
        raise ValueError("audit source manifest mismatch")
    files = {}
    for source in PROJECTION:
        item = declared[source]
        path = root / f"{source}.parquet"
        if (
            item["file"] != path.name
            or path.resolve(strict=True).parent != root
            or file_sha(path) != item["sha256"]
        ):
            raise ValueError("audit source path or bytes changed")
        files[source] = path
    db = duckdb.connect(":memory:")
    cursors = []
    try:
        for source, path in files.items():
            n, lo, hi, bad = db.execute(
                "SELECT count(*),min(trade_date),max(trade_date),"
                "count(*) FILTER(WHERE trade_date IS NULL OR instrument IS NULL) FROM read_parquet(?)",
                [str(path)],
            ).fetchone()
            meta = declared[source]
            if (
                n != meta["rows"]
                or not n
                or bad
                or str(lo) != meta["min_date"]
                or str(hi) != meta["max_date"]
                or not "2021-01-01" <= str(lo) <= str(hi) < "2025-01-01"
                or str(lo) < meta["authorized_start"]
                or str(hi) > meta["authorized_end"]
            ):
                raise ValueError("audit coverage metadata mismatch or restricted date")
            duplicates = db.execute(
                "SELECT count(*) FROM (SELECT trade_date,instrument,count(*) n FROM read_parquet(?) "
                "GROUP BY trade_date,instrument HAVING count(*)!=1)",
                [str(path)],
            ).fetchone()[0]
            if duplicates:
                raise ValueError("audit duplicate source key")
        streams = {}
        for source, columns in PROJECTION.items():
            cur = db.cursor()
            cursors.append(cur)
            cur.execute(
                f"SELECT {columns} FROM read_parquet(?) "
                "WHERE trade_date>=DATE '2022-01-01' AND trade_date<DATE '2025-01-01' "
                "ORDER BY trade_date,instrument",
                [str(files[source])],
            )
            streams[source] = _rows(cur, columns.split(","))
        yield streams, {s: declared[s]["sha256"] for s in files}
        for source, path in files.items():
            if file_sha(path) != declared[source]["sha256"]:
                raise ValueError("audit source changed during read")
    finally:
        for cur in cursors:
            cur.close()
        db.close()


def _rows(cursor, columns):
    while batch := cursor.fetchmany(2048):
        for row in batch:
            yield dict(zip(columns, row, strict=True))


def compare(actual, expected, *, label="reference"):
    """Strict structure/booleans plus finite numeric tolerance, never a pass counter."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(actual) != set(expected):
            raise ValueError(f"{label}: key/support mismatch")
        for key in expected:
            compare(actual[key], expected[key], label=f"{label}.{key}")
    elif isinstance(expected, (tuple, list)):
        if not isinstance(actual, (tuple, list)) or len(actual) != len(expected):
            raise ValueError(f"{label}: sequence mismatch")
        for a, b in zip(actual, expected, strict=True):
            compare(a, b, label=label)
    elif isinstance(expected, (bool, str)) or expected is None:
        if type(actual) is not type(expected) or actual != expected:
            raise ValueError(f"{label}: identity mismatch")
    elif isinstance(expected, (float, int)):
        if (
            type(actual) not in (float, int)
            or not math.isfinite(actual)
            or not math.isfinite(expected)
            or not math.isclose(actual, expected, rel_tol=2e-10, abs_tol=2e-12)
        ):
            raise ValueError(f"{label}: numerical mismatch")
    else:
        raise TypeError("unsupported reference evidence type")


def audit_source_history(registry, consumer, *, history_path, input_folder):
    history, native_proof = read_verified_history(registry, consumer, history_path)
    manifest_sha = history["source_evidence"]["parent_snapshot_sha256"]
    calendar = history["calendar"]
    total_bars, total_ranks, total_models, days = 0, 0, 0, 0
    reference_digests = {}
    support_days, orphan_exclusions = {}, []
    key_hashes = {k: hashlib.sha256() for k in ("daily_only", "flow_only")}
    with source_streams(input_folder, manifest_sha256=manifest_sha) as (streams, source_hashes):
        if source_hashes != history["source_evidence"]["source_sha256"]:
            raise ValueError("native history belongs to different source files")
        for i, (day, reference) in enumerate(
            reference_history(
                streams["daily"],
                streams["fund_flow"],
                calendar,
                support_policy="same-date-daily-supported-v1",
            )
        ):
            d, f = [set(reference["source_keys"][k]) for k in ("daily", "fund_flow")]
            support_days[day] = {
                "daily": len(d),
                "fund_flow": len(f),
                "common": len(d & f),
                "daily_only": len(d - f),
                "flow_only": len(f - d),
            }
            for kind, names in (("daily_only", sorted(d - f)), ("flow_only", sorted(f - d))):
                for name in names:
                    key_hashes[kind].update(
                        (
                            json.dumps([day, name], separators=(",", ":"), ensure_ascii=True) + "\n"
                        ).encode()
                    )
                    if kind == "flow_only":
                        orphan_exclusions.append(
                            {"date": day, "asset": name, "reason": "flow_without_same_date_daily"}
                        )
            compare(history["bars"][day], reference["bars"], label=f"bars:{day}")
            compare(history["ranks"][day], reference["ranks"], label=f"ranks:{day}")
            if 61 <= i < len(calendar) - 1:
                bundle = json.loads(
                    (Path(history_path).parent / f"response-{day}.json").read_bytes()
                )
                if set(bundle["models"]) != set(reference["models"]):
                    raise ValueError("independent past-only fitted stock support mismatch")
                for n, expected in reference["models"].items():
                    compare(
                        {k: bundle["models"][n][k] for k in expected},
                        expected,
                        label=f"response-model:{day}:{n}",
                    )
                total_models += len(reference["models"])
            reference_digests[day] = sha256_json(reference)
            total_bars += len(reference["bars"])
            total_ranks += len(reference["ranks"])
            days += 1
    counts = {
        k: sum(v[k] for v in support_days.values())
        for k in ("daily", "fund_flow", "common", "daily_only", "flow_only")
    }
    expected_support = {
        "policy": "same-date-daily-supported-v1",
        "counts": counts,
        "days": support_days,
        "identity_sha256": {k: h.hexdigest() for k, h in key_hashes.items()},
        "identity_encoding": "sorted-date-instrument compact ASCII JSON pairs, LF",
        "daily_key_coverage": counts["common"] / counts["daily"] if counts["daily"] else None,
        "flow_key_coverage": counts["common"] / counts["fund_flow"]
        if counts["fund_flow"]
        else None,
        "feature_coverage_gate": "separate; key coverage is not eight-feature/risk eligibility",
    }
    actual_exclusions = [
        e for e in history["bridge_exclusions"] if e["reason"] == "flow_without_same_date_daily"
    ]
    if history["source_support"] != expected_support or actual_exclusions != orphan_exclusions:
        raise ValueError("independent exact source support/exclusion identity mismatch")
    if file_sha(history_path) != native_proof["history_artifact_sha256"]:
        raise ValueError("history changed during independent audit")
    return {
        "source_history_audit_pass": True,
        "complete_pipeline_audit_pass": False,
        "supervised_label_model_target_account_audit": "NOT_RUN",
        "validated_alpha": False,
        "sessions_checked": days,
        "source_bars_checked": total_bars,
        "ranked_rows_checked": total_ranks,
        "per_stock_response_fits_checked": total_models,
        "source_sha256": source_hashes,
        "source_support_sha256": sha256_json(expected_support),
        "source_support_counts": counts,
        **native_proof,
        "reference_day_digests_sha256": sha256_json(reference_digests),
        "source_read_batch_rows": 2048,
        "source_numeric_years": [2022, 2023, 2024],
        "numeric_tolerance": {"relative": 2e-10, "absolute": 2e-12},
        "shared_infrastructure": "native/hash verification and canonical JSON only; no production numerical functions",
        "interpretation": "frozen daily-bar model reproduction,not broker/first-seen certification",
    }
