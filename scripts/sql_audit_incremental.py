"""An independent DuckDB aggregation of the saved accounting evidence, no new search."""

import json
import math
from pathlib import Path

import duckdb

from stephen_quant.workflows.v114_reliable_epoch import write_json

root = Path("artifacts/incremental-alpha/epoch-001")
query = Path("scripts/incremental_account_audit.sql").read_text(encoding="utf-8")
conn = duckdb.connect()
cursor = conn.execute(query)
columns = [c[0] for c in cursor.description]
rows = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
lookup = {(r["account"], r["year"], str(r["cost"])): r for r in rows}
report = json.loads((root / "RESULT.json").read_text(encoding="utf-8"))
compared = 0
for c in report["batches"][0]["candidates"]:
    for year, costs in c["years"].items():
        for cost, m in costs.items():
            actual = lookup[c["name"], year, cost]
            for field, metric in (
                ("net", "absolute_return"),
                ("profit_cny", "profit_cny"),
                ("fees_cny", "cost_cny"),
                ("drawdown", "max_drawdown"),
            ):
                if not math.isclose(actual[field], m[metric], rel_tol=1e-10, abs_tol=1e-6):
                    raise ValueError(f"SQL evidence mismatch: {c['name']} {year} {cost} {field}")
            compared += 1
write_json(
    root / "SQL_RECONCILIATION.json",
    {"pass": True, "annual_rows": len(rows), "candidate_windows_compared": compared, "rows": rows},
)
print(json.dumps({"pass": True, "annual_rows": len(rows), "candidate_windows_compared": compared}))
