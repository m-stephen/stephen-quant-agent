import json

import duckdb
import pytest

from stephen_quant.discovery.flow_response_series import bridge_rows
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.qmt.flow_response_inputs import load_response_sources
from stephen_quant.qmt.reliable_panel import file_sha


def inputs(tmp_path, *, duplicate=False, future=False):
    days = ["2021-12-31", "2022-01-03", "2022-01-04"]
    if duplicate:
        days.append(days[-1])
    if future:
        days.append("2026-01-01")
    sources = []
    conn = duckdb.connect(":memory:")
    try:
        for source in ("daily", "fund_flow"):
            if source == "daily":
                conn.execute(
                    "CREATE TABLE daily(trade_date DATE,instrument VARCHAR,name VARCHAR,open DOUBLE,close DOUBLE,amount DOUBLE,volume DOUBLE,adjustment_factor DOUBLE,available_at TIMESTAMPTZ)"
                )
                conn.executemany(
                    "INSERT INTO daily VALUES(?, 'synthetic','Synthetic',10,11,100000,10000,1,?::TIMESTAMPTZ)",
                    [(d, f"{d} 18:00:00+08:00") for d in days],
                )
            else:
                conn.execute(
                    "CREATE TABLE fund_flow(trade_date DATE,instrument VARCHAR,net_inflow_amount DOUBLE,available_at TIMESTAMPTZ)"
                )
                conn.executemany(
                    "INSERT INTO fund_flow VALUES(?,'synthetic',1000000,?::TIMESTAMPTZ)",
                    [(d, f"{d} 19:00:00+08:00") for d in days],
                )
            path = tmp_path / f"{source}.parquet"
            conn.execute(f"COPY {source} TO ? (FORMAT PARQUET)", [str(path)])
            sources.append(
                {
                    "source": source,
                    "file": path.name,
                    "sha256": file_sha(path),
                    "rows": len(days),
                    "min_date": min(days),
                    "max_date": max(days),
                    "authorized_start": "2021-10-01",
                    "authorized_end": "2024-12-31",
                }
            )
    finally:
        conn.close()
    # These files deliberately do not exist. The reader must not open them.
    sources += [
        {"source": s, "file": s + ".parquet", "sha256": "a" * 64, "rows": 0}
        for s in ("auction", "chip", "minute")
    ]
    document = {
        "sources": sources,
        "snapshot_sha256": sha256_json(sources),
        "exposed_sealed_rows": 0,
    }
    (tmp_path / "manifest.json").write_text(json.dumps(document), encoding="utf-8")
    return document, ["2022-01-03", "2022-01-04"]


def test_reader_projects_only_daily_flow_and_authorized_years(tmp_path):
    manifest, calendar = inputs(tmp_path)
    rows, evidence = load_response_sources(
        tmp_path, expected_manifest_sha256=manifest["snapshot_sha256"], calendar=calendar
    )
    assert set(rows) == {"daily", "fund_flow"}
    assert [r["trade_date"] for r in rows["daily"]] == calendar
    assert evidence["projected_rows"] == {"daily": 2, "fund_flow": 2}
    assert evidence["warmup_numeric_rows_read"] == evidence["sealed_numeric_rows_read"] == 0
    observations, _ = bridge_rows(rows["daily"], rows["fund_flow"], calendar)
    assert observations[calendar[-1]]["synthetic"].flow_ratio == pytest.approx(0.01)


@pytest.mark.parametrize(
    "mutation",
    ["manifest", "file", "filename", "rows", "calendar", "sealed_metadata", "duplicate_source"],
)
def test_reader_contract_mutations_rejected(tmp_path, mutation):
    manifest, calendar = inputs(tmp_path)
    expected = manifest["snapshot_sha256"]
    if mutation == "manifest":
        manifest["snapshot_sha256"] = "b" * 64
    elif mutation == "file":
        (tmp_path / "daily.parquet").write_bytes(b"changed")
    elif mutation == "calendar":
        calendar.pop()
    elif mutation == "sealed_metadata":
        manifest["exposed_sealed_rows"] = 1
    else:
        if mutation == "filename":
            manifest["sources"][0]["file"] = "../daily.parquet"
        elif mutation == "rows":
            manifest["sources"][0]["rows"] += 1
        else:
            manifest["sources"][-1]["source"] = "daily"
        manifest["snapshot_sha256"] = expected = sha256_json(manifest["sources"])
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        load_response_sources(tmp_path, expected_manifest_sha256=expected, calendar=calendar)


@pytest.mark.parametrize("kind", ["duplicate", "future"])
def test_reader_rejects_bad_keys_or_restricted_partition_before_numeric_projection(tmp_path, kind):
    manifest, calendar = inputs(tmp_path, **{kind: True})
    with pytest.raises(ValueError):
        load_response_sources(
            tmp_path, expected_manifest_sha256=manifest["snapshot_sha256"], calendar=calendar
        )
