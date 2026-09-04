from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from .data_warehouse import _atomic_json, _duckdb, _sha256
from .minute_warehouse import _minute_relation_sql, verify_minute_snapshot
from .models import QmtDataError

MINUTE_FEATURE_VERSION = "10.0.0"


@dataclass(frozen=True)
class MinuteFeatureSpec:
    feature_id: str
    family: str
    unit: str
    description: str
    observation_cutoff: str = "15:00:00+08:00"
    earliest_trade: str = "next_session_open"
    fitted: bool = False


FEATURE_REGISTRY = (
    MinuteFeatureSpec("intraday_return", "price_path", "return", "Full-session open-to-close return."),
    MinuteFeatureSpec("open_30_return", "price_path", "return", "Opening 30-minute return."),
    MinuteFeatureSpec("late_30_return", "price_path", "return", "Closing 30-minute return."),
    MinuteFeatureSpec("realized_volatility", "volatility", "volatility", "Square-root sum of one-minute log-return squares."),
    MinuteFeatureSpec("downside_volatility", "volatility", "volatility", "Downside one-minute realized volatility."),
    MinuteFeatureSpec("upside_volatility", "volatility", "volatility", "Upside one-minute realized volatility."),
    MinuteFeatureSpec("path_efficiency", "price_path", "ratio", "Net move divided by absolute one-minute path length."),
    MinuteFeatureSpec("vwap_deviation", "liquidity", "return", "Close relative to session VWAP."),
    MinuteFeatureSpec("opening_volume_share", "volume_shape", "ratio", "Share of volume traded through 10:00."),
    MinuteFeatureSpec("closing_volume_share", "volume_shape", "ratio", "Share of volume traded from 14:30."),
    MinuteFeatureSpec("amihud_intraday", "liquidity", "impact", "Average absolute one-minute return per CNY amount."),
    MinuteFeatureSpec("multiscale_divergence", "multiscale", "return", "Dispersion of 1/5/15/30/60-minute session returns."),
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def initialize_minute_feature_store(warehouse_root: str | Path) -> None:
    root = Path(warehouse_root).expanduser().resolve()
    (root / "minute-feature-snapshots").mkdir(parents=True, exist_ok=True)
    (root / "parquet" / "minute_features").mkdir(parents=True, exist_ok=True)
    connection = _duckdb().connect(str(root / "catalog" / "warehouse.duckdb"))
    try:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS minute_feature_snapshots ("
            "feature_snapshot_id VARCHAR PRIMARY KEY, minute_snapshot_id VARCHAR, method_version VARCHAR, "
            "start_date DATE, end_date DATE, parquet_relative_path VARCHAR, parquet_sha256 VARCHAR, "
            "parquet_size_bytes BIGINT, row_count BIGINT, created_at TIMESTAMPTZ, manifest_relative_path VARCHAR)"
        )
    finally:
        connection.close()


def _refresh_view(connection, root: Path) -> None:
    paths = connection.execute(
        "SELECT parquet_relative_path FROM minute_feature_snapshots ORDER BY created_at, feature_snapshot_id"
    ).fetchall()
    if not paths:
        return
    literals = ",".join(
        "'" + str(root / str(row[0])).replace("'", "''") + "'" for row in paths
    )
    connection.execute(
        "CREATE OR REPLACE VIEW qd_minute_feature_revisions AS "
        f"SELECT * FROM read_parquet([{literals}], union_by_name=true)"
    )
    connection.execute(
        "CREATE OR REPLACE VIEW qd_minute_features_current AS SELECT * EXCLUDE(rn) FROM ("
        "SELECT *, row_number() OVER(PARTITION BY trade_date,instrument ORDER BY "
        "feature_snapshot_id DESC) rn FROM qd_minute_feature_revisions) WHERE rn=1"
    )


def build_minute_feature_mart(
    warehouse_root: str | Path,
    *,
    minute_snapshot_id: str,
    start_date: date,
    end_date: date,
    source_preverified: bool = False,
) -> dict[str, object]:
    if start_date > end_date:
        raise QmtDataError("minute feature date range is invalid")
    root = Path(warehouse_root).expanduser().resolve()
    if not source_preverified:
        verification = verify_minute_snapshot(root, minute_snapshot_id)
        if not verification["passed"]:
            raise QmtDataError("minute feature source snapshot failed verification")
    initialize_minute_feature_store(root)
    policy = {
        "method_version": MINUTE_FEATURE_VERSION,
        "minute_snapshot_id": minute_snapshot_id,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "registry": [asdict(item) for item in FEATURE_REGISTRY],
        "decision_time": "next_session_open",
        "fit_policy": "all fitted transforms must run inside training folds",
    }
    feature_snapshot_id = hashlib.sha256(_canonical(policy)).hexdigest()
    connection = _duckdb().connect(str(root / "catalog" / "warehouse.duckdb"))
    existing = connection.execute(
        "SELECT row_count FROM minute_feature_snapshots WHERE feature_snapshot_id=?",
        [feature_snapshot_id],
    ).fetchone()
    if existing:
        connection.close()
        return {**policy, "feature_snapshot_id": feature_snapshot_id, "row_count": int(existing[0]), "status": "REPLAY_NOOP"}
    staging = root / "staging" / f"minute-features-{uuid.uuid4().hex}"
    staging.mkdir(parents=True, exist_ok=False)
    staged = staging / "features.parquet"
    try:
        partition_rows = connection.execute(
            "SELECT parquet_relative_path FROM minute_partitions WHERE trade_date BETWEEN ? AND ? "
            "UNION ALL SELECT parquet_relative_path FROM minute_range_partitions "
            "WHERE min_date<=? AND max_date>=? ORDER BY 1",
            [start_date, end_date, end_date, start_date],
        ).fetchall()
        if not partition_rows:
            raise QmtDataError("minute snapshot has no partitions in requested feature range")
        literals = ",".join(
            "'" + str(root / str(row[0])).replace("'", "''") + "'" for row in partition_rows
        )
        relation = _minute_relation_sql(connection, literals, revision_mode="stored")
        connection.execute(
            "CREATE OR REPLACE TEMP VIEW v10_minute_selected AS SELECT * EXCLUDE(rn) FROM ("
            "SELECT *,row_number() OVER(PARTITION BY interval_minutes,bar_at,instrument ORDER BY "
            "ingested_at DESC,archive_sha256 DESC,member_sha256 DESC,member_path DESC) rn FROM ("
            f"{relation}) WHERE trade_date BETWEEN DATE '{start_date.isoformat()}' "
            f"AND DATE '{end_date.isoformat()}') WHERE rn=1"
        )
        target_literal = str(staged).replace("'", "''")
        query = f"""
        COPY (
          WITH selected AS (
            SELECT trade_date, bar_at, interval_minutes, instrument, "open", "close", volume, amount,
                   ln("close" / lag("close") OVER(
                     PARTITION BY trade_date,instrument,interval_minutes ORDER BY bar_at)) minute_log_return
            FROM v10_minute_selected
            WHERE trade_date BETWEEN DATE '{start_date.isoformat()}' AND DATE '{end_date.isoformat()}'
          ), interval_stats AS (
            SELECT trade_date,instrument,interval_minutes,
                   arg_min("open",bar_at) first_open,arg_min("close",bar_at) first_close,
                   arg_max("close",bar_at) last_close,
                   arg_max("close",bar_at) FILTER(WHERE hour(bar_at)<10 OR (hour(bar_at)=10 AND minute(bar_at)=0)) open_30_close,
                   arg_min("close",bar_at) FILTER(WHERE hour(bar_at)>14 OR (hour(bar_at)=14 AND minute(bar_at)>=30)) late_30_open,
                   sum(volume) total_volume,sum(amount) total_amount,count(*) bar_count,
                   sum(volume) FILTER(WHERE hour(bar_at)<10 OR (hour(bar_at)=10 AND minute(bar_at)=0)) opening_volume,
                   sum(volume) FILTER(WHERE hour(bar_at)>14 OR (hour(bar_at)=14 AND minute(bar_at)>=30)) closing_volume,
                   sqrt(sum(coalesce(minute_log_return*minute_log_return,0))) realized_volatility,
                   sqrt(sum(CASE WHEN minute_log_return<0 THEN minute_log_return*minute_log_return ELSE 0 END)) downside_volatility,
                   sqrt(sum(CASE WHEN minute_log_return>0 THEN minute_log_return*minute_log_return ELSE 0 END)) upside_volatility,
                   sum(abs(coalesce(minute_log_return,0))) absolute_path,
                   avg(abs(coalesce(minute_log_return,0))/(amount+1.0)) amihud_intraday
            FROM selected GROUP BY trade_date,instrument,interval_minutes
          ), one_minute AS (
            SELECT * FROM interval_stats WHERE interval_minutes=1
          ), scales AS (
            SELECT trade_date,instrument,stddev_pop(last_close/first_open-1.0) multiscale_divergence,
                   count(*) multiscale_intervals
            FROM interval_stats WHERE interval_minutes IN (1,5,15,30,60)
            GROUP BY trade_date,instrument
          )
          SELECT o.trade_date,o.instrument,
                 o.last_close/o.first_open-1.0 intraday_return,
                 o.open_30_close/o.first_open-1.0 open_30_return,
                 o.last_close/o.late_30_open-1.0 late_30_return,
                 o.realized_volatility,o.downside_volatility,o.upside_volatility,
                 (o.last_close/o.first_close-1.0)/(o.absolute_path+1e-12) path_efficiency,
                 o.last_close/(o.total_amount/nullif(o.total_volume,0))-1.0 vwap_deviation,
                 o.opening_volume/nullif(o.total_volume,0) opening_volume_share,
                 o.closing_volume/nullif(o.total_volume,0) closing_volume_share,
                 o.amihud_intraday,s.multiscale_divergence,
                 o.bar_count bar_count_1m,s.multiscale_intervals,
                 CASE WHEN o.bar_count>=220 THEN 'COMPLETE' WHEN o.bar_count>=60 THEN 'PARTIAL' ELSE 'SPARSE' END quality_state,
                 CAST(o.trade_date AS TIMESTAMPTZ)+INTERVAL 15 HOUR effective_at,
                 CAST(o.trade_date AS TIMESTAMPTZ)+INTERVAL 1 DAY+INTERVAL 9 HOUR+INTERVAL 30 MINUTE available_at,
                 '{feature_snapshot_id}' feature_snapshot_id,
                 '{minute_snapshot_id}' minute_snapshot_id,
                 '{MINUTE_FEATURE_VERSION}' method_version,
                 o.trade_date>=DATE '2025-01-01' sealed
          FROM one_minute o JOIN scales s USING(trade_date,instrument)
          ORDER BY o.trade_date,o.instrument
        ) TO '{target_literal}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
        connection.execute(query)
        row_count = int(connection.execute("SELECT count(*) FROM read_parquet(?)", [str(staged)]).fetchone()[0])
        if row_count < 1:
            raise QmtDataError("minute feature query produced no rows")
        parquet_sha = _sha256(staged)
        relative = f"parquet/minute_features/snapshot={feature_snapshot_id}/{parquet_sha}.parquet"
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=False)
        staged.replace(target)
        manifest = {**policy, "feature_snapshot_id": feature_snapshot_id, "parquet_relative_path": relative, "parquet_sha256": parquet_sha, "parquet_size_bytes": target.stat().st_size, "row_count": row_count}
        manifest_relative = f"minute-feature-snapshots/{feature_snapshot_id}.json"
        _atomic_json(root / manifest_relative, manifest)
        connection.execute("BEGIN TRANSACTION")
        connection.execute(
            "INSERT INTO minute_feature_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [feature_snapshot_id, minute_snapshot_id, MINUTE_FEATURE_VERSION, start_date, end_date, relative, parquet_sha, target.stat().st_size, row_count, datetime.now(timezone.utc), manifest_relative],
        )
        _refresh_view(connection, root)
        connection.execute("COMMIT")
        return {**manifest, "status": "COMPLETED"}
    finally:
        try:
            connection.close()
        finally:
            staged.unlink(missing_ok=True)
            try:
                staging.rmdir()
            except OSError:
                pass


def verify_minute_feature_snapshot(
    warehouse_root: str | Path, feature_snapshot_id: str
) -> dict[str, object]:
    root = Path(warehouse_root).expanduser().resolve()
    manifest_path = root / "minute-feature-snapshots" / f"{feature_snapshot_id}.json"
    if not manifest_path.is_file():
        raise QmtDataError(f"minute feature snapshot does not exist: {feature_snapshot_id}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    policy_keys = (
        "method_version",
        "minute_snapshot_id",
        "start_date",
        "end_date",
        "registry",
        "decision_time",
        "fit_policy",
    )
    computed = hashlib.sha256(_canonical({key: manifest[key] for key in policy_keys})).hexdigest()
    failures: list[str] = []
    if computed != feature_snapshot_id or manifest.get("feature_snapshot_id") != feature_snapshot_id:
        failures.append("feature manifest identity mismatch")
    parquet = (root / str(manifest["parquet_relative_path"])).resolve()
    if root not in parquet.parents or not parquet.is_file():
        failures.append("feature parquet missing or escaping warehouse")
        return {"feature_snapshot_id": feature_snapshot_id, "passed": False, "failures": failures}
    if parquet.stat().st_size != int(manifest["parquet_size_bytes"]) or _sha256(parquet) != manifest["parquet_sha256"]:
        failures.append("feature parquet integrity mismatch")
    connection = _duckdb().connect()
    try:
        rows, duplicates, timing, sealed = connection.execute(
            "SELECT count(*),count(*)-count(DISTINCT (trade_date,instrument)),"
            "count(*) FILTER(WHERE effective_at>available_at),"
            "count(*) FILTER(WHERE trade_date>=DATE '2025-01-01' AND sealed=false) "
            "FROM read_parquet(?)",
            [str(parquet)],
        ).fetchone()
    finally:
        connection.close()
    if int(rows) != int(manifest["row_count"]):
        failures.append("feature row count mismatch")
    if duplicates:
        failures.append("duplicate feature keys")
    if timing:
        failures.append("feature timing violation")
    if sealed:
        failures.append("feature sealed-state violation")
    return {
        "feature_snapshot_id": feature_snapshot_id,
        "passed": not failures,
        "failures": failures,
        "row_count": int(rows),
        "duplicate_keys": int(duplicates),
        "timing_violations": int(timing),
        "sealed_violations": int(sealed),
    }
