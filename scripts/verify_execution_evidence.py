"""Independent reconciliation of saved diagnostics; no market/account rerun."""

import json
import math
import sqlite3
from collections import Counter
from pathlib import Path

import duckdb

from stephen_quant.qmt.reliable_panel import file_sha
from stephen_quant.workflows.v114_reliable_epoch import write_json

ROOT = Path("artifacts/execution-evidence/epoch-001")
PARENT = Path("../v11.11-temporal-increments/artifacts/stability-challenge/epoch-001")


def verify():
    result = json.loads((ROOT / "RESULT.json").read_text(encoding="utf-8"))
    assert result["raw_global_trial_lower_bound"] == 3322
    assert result["completed_diagnostic_trials"] == 2 and result["new_account_trials"] == 0
    assert not result["physical_execution_verified"] and not result["validated_alpha"]
    assert file_sha(PARENT / "RESULT.json") == result["spec"]["parent_sha256"]
    parent_result = json.loads((PARENT / "RESULT.json").read_text(encoding="utf-8"))
    prices = {
        (r["date"], r["instrument"]): r
        for r in json.loads((ROOT / "raw_price_evidence.json").read_text())
    }
    rows, chart, reviews = [], [], set()
    with duckdb.connect() as c:
        for policy, summary in result["records"].items():
            path = PARENT / "accounts" / ("baseline_82-" + policy + ".jsonl")
            assert (
                file_sha(path) == parent_result["records"]["baseline_82"][policy]["account_sha256"]
            )
            # Independent SQL traverses the original saved tickets, not the audit totals.
            sql = """WITH orders AS (SELECT unnest(orders) o FROM read_json_auto(?))
                SELECT count(*) FILTER(WHERE o.executed_notional>0),
                 count(*) FILTER(WHERE o.executed_notional<0),
                 sum(CASE WHEN o.executed_notional<>0 THEN greatest(0,5-abs(o.executed_notional)*.0006) ELSE 0 END),
                 sum(greatest(o.executed_notional,0)) FROM orders"""
            buy_count, sell_count, fees, buy_sum = c.execute(sql, [str(path)]).fetchone()
            assert buy_count == summary["buy_tickets"] and sell_count == summary["sell_tickets"]
            assert math.isclose(fees, summary["extra_minimum_commission_cny"], abs_tol=1e-6)
            assert math.isclose(buy_sum, summary["buy_notional_cny"], abs_tol=1e-6)
            tickets = json.loads((ROOT / f"tickets-{policy}.json").read_text())
            assert len(tickets) == buy_count
            assert all(t["status"] == "DIAGNOSTIC_ONLY" for t in tickets)
            total_rounded, total_residual, zero = 0.0, 0.0, 0
            for t in tickets:
                price = prices[(t["date"], t["instrument"])]["open"]
                q = t["raw_quantity"]
                assert type(q) is int and 0 <= q <= t["maximum"]
                assert q == 0 or (q >= t["minimum"] and (q - t["minimum"]) % t["increment"] == 0)
                assert math.isclose(q * price, t["rounded_notional"], abs_tol=1e-7)
                original = t["rounded_notional"] + t["unallocated_notional"]
                assert original >= t["rounded_notional"] and t["unallocated_notional"] >= 0
                if q == 0:
                    assert original < t["minimum"] * price + 1e-8
                elif q < t["maximum"]:
                    assert t["unallocated_notional"] < t["increment"] * price + 1e-7
                total_rounded += t["rounded_notional"]
                total_residual += t["unallocated_notional"]
                zero += q == 0
            assert math.isclose(total_rounded, summary["rounded_buy_notional_cny"], abs_tol=1e-6)
            assert math.isclose(
                total_residual, summary["unallocated_buy_notional_cny"], abs_tol=1e-6
            )
            assert zero == summary["below_minimum_buy_tickets"]
            expected, held = set(), set()
            for line in path.read_text().splitlines():
                p = json.loads(line)
                for instrument in held:
                    raw = prices.get((p["date"], instrument))
                    reason = None
                    if raw is None:
                        reason = "held_raw_missing"
                    elif raw["previous_factor"] is None:
                        reason = "prior_factor_missing"
                    elif abs(raw["factor"] - raw["previous_factor"]) > 1e-10 * max(
                        raw["factor"], raw["previous_factor"]
                    ):
                        reason = "held_adjustment_change"
                    if reason:
                        expected.add((p["date"], instrument, reason))
                held = {m["instrument"] for m in p["positions"] if m["shares"] > 0}
            review = json.loads((ROOT / f"event-review-{policy}.json").read_text())
            actual = {(r["date"], r["instrument"], r["reason"]) for r in review}
            assert actual == expected and len(actual) == len(review)
            reviews.update(actual)
            rows.append({"policy": policy, **summary})
            for state, count in (("below_minimum", zero), ("nonzero_rounded", buy_count - zero)):
                chart.append(
                    {
                        "policy": policy,
                        "quantity_status": state,
                        "ticket_count": count,
                        "all_buy_tickets": buy_count,
                        "share_of_buy_tickets": count / buy_count,
                        "cumulative_buy_notional_cny": buy_sum,
                        "period": "2023-2024",
                        "account_start_cny": 3_000_000,
                    }
                )
    worklist = json.loads((ROOT / "scoped-event-worklist.json").read_text())
    assert {(r["date"], r["instrument"], r["reason"]) for r in worklist} == reviews
    assert len(worklist) == len(reviews) == result["scoped_event_worklist_keys"]
    with sqlite3.connect(f"file:{(ROOT / 'registry.sqlite3').as_posix()}?mode=ro", uri=True) as c:
        assert c.execute("SELECT count(*) FROM trials").fetchone()[0] == 2
        assert (
            c.execute("SELECT count(*) FROM trial_fit_contracts WHERE stages_json='[]'").fetchone()[
                0
            ]
            == 2
        )
        assert c.execute("SELECT count(*) FROM trial_model_fits").fetchone()[0] == 0
        ledger_results = c.execute("SELECT result_json FROM trials").fetchall()
        assert len(ledger_results) == 2
        assert sorted(
            json.dumps(json.loads(x[0]), sort_keys=True) for x in ledger_results
        ) == sorted(json.dumps(x, sort_keys=True) for x in result["records"].values())
    artifact_files = [p for p in ROOT.iterdir() if p.is_file()]
    audit = {
        "pass": True,
        "result_sha256": file_sha(ROOT / "RESULT.json"),
        "checked_policies": 2,
        "checked_buy_tickets": sum(r["buy_tickets"] for r in rows),
        "worklist_reason_counts": dict(Counter(r["reason"] for r in worklist)),
        "worklist_unique_instruments": len({r["instrument"] for r in worklist}),
        "source_price_rows": len(prices),
        "native_unfitted_contracts": 2,
        "files_sha256": {p.name: file_sha(p) for p in artifact_files},
        "method": "independent SQL saved-order sums, raw quantity maximality, held-key reconstruction, SQLite results",
        "source_sql": sql,
        "source_parameter_template": "baseline_82-{policy}.jsonl",
    }
    write_json(ROOT / "INDEPENDENT_AUDIT.json", audit)
    write_json(
        Path("docs/V11_12_RESULT.summary.json"),
        {
            "version": "11.12.0",
            "rows": rows,
            "chart_rows": chart,
            "independent_audit_pass": True,
            "result_sha256": audit["result_sha256"],
            "audit_sha256": file_sha(ROOT / "INDEPENDENT_AUDIT.json"),
            "raw_trial_lower_bound": 3322,
            "new_diagnostic_trials": 2,
            "new_accounts": 0,
            "new_fits": 0,
            "restricted_rows_read": 0,
            "validated_alpha": False,
            "scoped_worklist_keys": len(worklist),
            "worklist_reason_counts": audit["worklist_reason_counts"],
            "worklist_unique_instruments": audit["worklist_unique_instruments"],
            "source_price_rows": len(prices),
        },
    )
    print(json.dumps({k: v for k, v in audit.items() if k not in ("files_sha256", "source_sql")}))


if __name__ == "__main__":
    verify()
