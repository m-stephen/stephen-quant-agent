"""Independent frozen-target/lineage, source-price, cost-path and account verification."""

import argparse
import json
import math
import sqlite3
from pathlib import Path

import duckdb
from audit_conditional_risk import compare, market_account_check, quote, read
from audit_pairwise_ranking import native_check
from sparse_account_audit import audit_accounts, near

from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.qmt.reliable_panel import file_sha
from stephen_quant.workflows.v114_reliable_epoch import protected_digest, write_json


def reference_differences(records):
    rows, increments = [], []
    identities = [
        (b, k) for b in ("linear", "quadratic") for k in ("full", "risk", "shuffle", "regression")
    ]
    identities += [("control", k) for k in ("hash", "lowvol", "original_lowvol", "original_stable")]
    expected = {f"{b}-{p}-{c}" for b, p in identities for c in (0, 82, 164)}
    if set(records) != expected:
        raise ValueError("full36-account comparison required")
    for b, k in identities:
        tk = f"{b}-{k}"
        z = records[tk + "-0"]
        for cost in (82, 164):
            p = records[tk + f"-{cost}"]
            gross, net = z["metrics"]["final_nav"] / 3e6 - 1, p["metrics"]["final_nav"] / 3e6 - 1
            direct = p["metrics"]["total_cost"] / 3e6
            rows.append(
                {
                    "identity": b,
                    "policy": k,
                    "target_key": tk,
                    "roundtrip_bps": cost,
                    "zero_cost_return": gross,
                    "paid_return": net,
                    "cost_path_drag": gross - net,
                    "direct_cost_fraction_initial_capital": direct,
                    "addback_error": gross - net - direct,
                    "drag2023": z["years"]["2023"] - p["years"]["2023"],
                    "drag2024": z["years"]["2024"] - p["years"]["2024"],
                }
            )
    for b in ("linear", "quadratic"):
        controls = [f"{b}-{k}" for k in ("risk", "shuffle", "regression")]
        controls += [
            f"control-{k}" for k in ("hash", "lowvol", "original_lowvol", "original_stable")
        ]
        for peer in controls:
            gross = (
                records[b + "-full-0"]["metrics"]["final_nav"]
                - records[peer + "-0"]["metrics"]["final_nav"]
            ) / 3e6
            for cost in (0, 82, 164):
                c, p = records[f"{b}-full-{cost}"], records[f"{peer}-{cost}"]
                cr, pr = c["metrics"]["final_nav"] / 3e6 - 1, p["metrics"]["final_nav"] / 3e6 - 1
                increments.append(
                    {
                        "identity": b,
                        "control": peer,
                        "roundtrip_bps": cost,
                        "candidate_return": cr,
                        "control_return": pr,
                        "increment": cr - pr,
                        "gross_increment": gross,
                        "increment_path_drag": gross - cr + pr,
                        "increment2023": c["years"]["2023"] - p["years"]["2023"],
                        "increment2024": c["years"]["2024"] - p["years"]["2024"],
                    }
                )
    return {
        "path_drag": rows,
        "increments": increments,
        "validated_alpha": False,
        "screen_survived": {"linear": False, "quadratic": False},
        "interpretation": "diagnostic_only;counterfactual_cost_paths_are_not_causal_fee_estimates",
    }


def source_shares(con, folder):
    """Opening fills accumulate adjusted units; writeoffs mark, not dispose, shares."""
    con.execute(
        f"CREATE OR REPLACE VIEW share_accounts AS SELECT * FROM read_json_auto({quote(folder / 'accounts/*.jsonl')})"
    )
    prices = {
        (str(d), n): p
        for d, n, p in con.execute("""
        SELECT DISTINCT d.date::DATE,o.instrument,b.op FROM share_accounts d
        CROSS JOIN unnest(d.orders) x(o) LEFT JOIN valid_bars b
        ON b.date=d.date::DATE AND b.instrument=o.instrument
        WHERE abs(o.executed_notional)>1e-12""").fetchall()
    }
    fills = 0
    for path in sorted((folder / "accounts").glob("*.jsonl")):
        shares = {}
        with path.open(encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                for o in d["orders"]:
                    if abs(o["executed_notional"]) <= 1e-12:
                        continue
                    op = prices.get((d["date"], o["instrument"]))
                    if op is None or not math.isfinite(op) or op <= 0:
                        raise ValueError("executed fill lacks valid source open")
                    n = o["instrument"]
                    shares[n] = shares.get(n, 0) + o["executed_notional"] / op
                    fills += 1
                actual = {m["instrument"]: m["shares"] for m in d["positions"]}
                for n in set(actual) | set(shares):
                    near(
                        actual.get(n, 0), shares.get(n, 0), "source adjusted-share continuity", 1e-7
                    )
    return fills


def native_replays(output, result):
    with sqlite3.connect(
        f"file:{(output / 'registry.sqlite3').as_posix()}?mode=ro", uri=True
    ) as db:
        rows = db.execute(
            "SELECT t.hyperparams,t.result_json,c.stages_json,e.code_version FROM trials t JOIN trial_fit_contracts c USING(trial_id) JOIN experiments e USING(experiment_id)"
        ).fetchall()
        if (
            len(rows) != 12
            or db.execute("SELECT count(*) FROM trial_model_fits").fetchone()[0] != 0
        ):
            raise ValueError("twelve native replays and zero new fits required")
        seen = set()
        for hp, rr, stages, code in rows:
            p, r = json.loads(hp), json.loads(rr)
            if p not in result["spec"]["plans"] or r != result["records"][p["key"]]:
                raise ValueError("native replay identity/result mismatch")
            if json.loads(stages) != [] or code != result["spec"]["runtime_code_sha256"]:
                raise ValueError("native replay contract/code mismatch")
            if r["fit_lineage_sha256"] != sha256_json([]):
                raise ValueError("replay fabricated a new fit")
            if r["inherited_receipt_sha256"] != file_sha(output / "inherited_lineage.json"):
                raise ValueError("inherited receipt not bound")
            seen.add(p["key"])
        if seen != set(result["records"]):
            raise ValueError("replay set mismatch")


def declared_contract(result):
    """Independently enumerate the diagnostic, with no promotion escape hatch."""
    identities = [
        (b, k) for b in ("linear", "quadratic") for k in ("full", "risk", "shuffle", "regression")
    ] + [("control", k) for k in ("hash", "lowvol", "original_lowvol", "original_stable")]
    expected = [
        {
            "key": f"{b}-{k}-0",
            "target_key": f"{b}-{k}",
            "identity": b,
            "basis": b if b != "control" else "none",
            "policy": k,
            "scale": 0,
            "roundtrip_bps": 0,
            "mode": "full_target" if k.startswith("original_") else "target_changes",
            "operation_kind": "frozen_target_replay",
        }
        for b, k in identities
    ]
    compare(result["spec"]["plans"], expected, "frozen twelve plans")
    if (
        result["raw_global_trial_lower_bound"] != 3660
        or result["completed_trials"] != 12
        or result["reserved_trials"] != 12
        or result["spec"]["raw_debt_before"] != 3648
        or result["spec"]["reserved_trials"] != 12
        or result["validated_alpha"] is not False
        or result["engineering_pass"] is not True
        or result["protected_unchanged"] is not True
        or result["restricted_rows_read"] != 0
        or result["screen_survived"] != {"linear": False, "quadratic": False}
        or result["statistics"] != {"dsr": None, "pbo": None, "placebo": None, "status": "NOT_RUN"}
    ):
        raise ValueError("diagnostic completion/debt/scope/promotion contract mismatch")


def audit(output, inputs):
    output, inputs = Path(output).resolve(), Path(inputs).resolve()
    if (output / "INDEPENDENT_AUDIT.json").exists():
        raise FileExistsError("audit already complete; do not repeat")
    result = read(output / "RESULT.json")
    declared_contract(result)
    spec = result["spec"]
    compare(spec, read(output / "frozen_spec.json"), "original frozen specification")
    if str(inputs / "daily.parquet") not in spec["protected_files"]:
        raise ValueError("auditor input path not bound to frozen sources")
    parent = Path(spec["parent_dir"])
    if protected_digest([Path(p) for p in spec["protected_files"]])[0] != spec[
        "protected_before"
    ] or any(file_sha(p) != h for p, h in spec["protected_files"].items()):
        raise ValueError("protected source or prior evidence changed")
    for field, name in (
        ("auditor_sha256", "audit_gross_net_attribution.py"),
        ("audit_query_sha256", "gross_net_source_audit.sql"),
    ):
        if file_sha(Path(__file__).with_name(name)) != spec[field]:
            raise ValueError("frozen audit code/query changed")
    prior = read(parent / "RESULT.json")
    if (
        file_sha(parent / "RESULT.json") != spec["parent_sha256"]
        or result["reference_records"] != prior["records"]
    ):
        raise ValueError("inherited paid evidence mismatch")
    models = {
        f"{b}-{k}": {y: read(parent / f"models/{b}-{k}-{y}.json") for y in (2023, 2024)}
        for b in ("linear", "quadratic")
        for k in ("full", "risk", "shuffle", "regression")
    }
    native_check(parent, prior, models)
    receipt = read(output / "inherited_lineage.json")
    expected_receipt = {
        "operation_kind": "frozen_target_replay",
        "new_fits": 0,
        "inherited_models": 16,
        "inherited_fit_receipts": 32,
        "parent_result_sha256": spec["parent_sha256"],
        "parent_registry_sha256": file_sha(parent / "registry.sqlite3"),
        "models_sha256": prior["models_sha256"],
        "lineages": {k: r["fit_lineage_sha256"] for k, r in prior["records"].items()},
    }
    compare(receipt, expected_receipt, "inherited lineage")
    for p in spec["plans"]:
        tk = p["target_key"]
        if file_sha(output / f"targets/{tk}.json") != file_sha(parent / f"targets/{tk}.json"):
            raise ValueError("target bytes not frozen")
        expected = {
            "maximum_position_weight": 0.025,
            "commission_bps": 0,
            "sell_tax_bps": 0,
            "slippage_bps": 0,
            "stale_writeoff_sessions": 20,
            "rebalance_mode": "full_target"
            if p["policy"].startswith("original_")
            else "target_changes",
        }
        compare(spec["execution_configs"][p["key"]], expected, "unchanged execution configuration")
    query = Path(__file__).with_name("gross_net_source_audit.sql").read_text(encoding="utf-8")
    with duckdb.connect(
        config={"threads": 4, "memory_limit": "4GB", "temp_directory": str(output / "audit-temp")}
    ) as con:
        con.execute(
            f"CREATE VIEW daily_source AS SELECT * FROM read_parquet({quote(inputs / 'daily.parquet')})"
        )
        if con.execute(
            "SELECT count(*) FROM daily_source WHERE trade_date>=DATE '2025-01-01'"
        ).fetchone()[0]:
            raise ValueError("restricted source dates")
        con.execute(query)
        source = {}
        for name, folder in (("new_zero_cost", output), ("inherited_paid", parent)):
            source[name] = {
                **market_account_check(con, folder),
                "source_open_fills": source_shares(con, folder),
            }
    zero_rows, residual = audit_accounts(output, result, expected_accounts=12)
    paid_rows, prior_residual = audit_accounts(parent, prior, expected_accounts=24)
    if any(r["cost_cny"] != 0 for r in zero_rows):
        raise ValueError("zero-cost account has fees")
    native_replays(output, result)
    recomputed = reference_differences({**prior["records"], **result["records"]})
    compare(result["attribution"], recomputed, "independent cost-path differences")
    if (
        result["raw_global_trial_lower_bound"] != 3660
        or result["completed_trials"] != 12
        or result["validated_alpha"]
        or result["screen_survived"] != {"linear": False, "quadratic": False}
    ):
        raise ValueError("debt/completion or promotion mismatch")
    compare(
        read(output / "first_read_reservations.json"),
        {
            "trials": spec["plans"],
            "spec_sha256": sha256_json(spec),
            "stage": "before_numerical_read",
        },
        "first-read reservations",
    )
    summary = {
        "version": result["version"],
        "rows": sorted(zero_rows + paid_rows, key=lambda r: r["account_key"]),
        "attribution": recomputed,
        "raw_trial_lower_bound": 3660,
        "new_trials": 12,
        "new_fits": 0,
        "inherited_models": 16,
        "inherited_fit_receipts": 32,
        "source_checks": source,
        "independent_audit_pass": True,
        "validated_alpha": False,
        "source_result_sha256": file_sha(output / "RESULT.json"),
        "snapshot_sha256": spec["snapshot_sha256"],
        "maximum_balance_residual_cny": max(residual, prior_residual),
        "units": "source-adjusted-fractional;not-raw-broker-shares",
    }
    write_json(
        output / "INDEPENDENT_AUDIT.json",
        {
            "pass": True,
            "summary": summary,
            "source_query": query,
            "evidence_hashes": {
                p.relative_to(output).as_posix(): file_sha(p)
                for p in output.rglob("*")
                if p.is_file()
            },
        },
    )
    print(
        json.dumps(
            {
                "independent_audit": "PASS",
                "new_accounts": 12,
                "inherited_accounts": 24,
                "new_fits": 0,
            }
        ),
        flush=True,
    )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--inputs", required=True)
    args = parser.parse_args()
    audit(args.output, args.inputs)
