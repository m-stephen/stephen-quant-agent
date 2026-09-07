"""Bind the native chart to an actually executed, public-safe SQL extraction."""

import json
from pathlib import Path

import duckdb

from stephen_quant.workflows.v114_reliable_epoch import write_json

ROOT = Path("artifacts/temporal-increments/epoch-001")
QUERY = """
SELECT a.* EXCLUDE (start,"end"), CAST(a.start AS VARCHAR) AS start,
    CAST(a."end" AS VARCHAR) AS "end",
    CASE a.policy
      WHEN 'flow_consistency' THEN '资金流持续性 / Flow consistency'
      WHEN 'auction_tail_balance' THEN '竞价尾部 / Auction tail'
      WHEN 'chip_path_efficiency' THEN '筹码路径 / Chip path'
    END || ' · ' || CAST(a.roundtrip_bps AS VARCHAR) || 'bps' AS label
FROM (SELECT unnest(rows) AS a FROM read_json_auto('docs/V11_11_RESULT.summary.json'))
WHERE a.policy IN ('flow_consistency','auction_tail_balance','chip_path_efficiency')
ORDER BY a.policy,a.roundtrip_bps
""".strip()


def build():
    artifact = json.loads((ROOT / "report-artifact.json").read_text(encoding="utf-8"))
    with duckdb.connect() as con:
        cursor = con.execute(QUERY)
        columns = [d[0] for d in cursor.description]
        rows = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    if len(rows) != 9:
        raise ValueError("complete9-comparison source required")
    source = artifact["sources"][0]
    source["query"].update(
        sql=QUERY, language="sql", engine="DuckDB", tables_used=["docs/V11_11_RESULT.summary.json"]
    )
    artifact["manifest"]["sources"] = [source]
    artifact["manifest"]["charts"][0]["source"] = source
    artifact["snapshot"]["datasets"]["accounts"] = rows
    json.dumps(artifact, allow_nan=False)  # Validate serialization before exclusive create.
    write_json(ROOT / "report-artifact.v3.json", artifact)
    print(json.dumps({"chart_rows": len(rows), "query_executed": True}))


if __name__ == "__main__":
    build()
