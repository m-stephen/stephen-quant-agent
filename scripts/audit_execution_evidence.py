"""Single-use, registered diagnostics of two frozen accounts; no new backtest."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from stephen_quant.baseline.execution_quantity import audit_saved_account
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest
from stephen_quant.qmt.reliable_panel import file_sha
from stephen_quant.workflows.v114_reliable_epoch import (
    protected_digest,
    runtime_code_hash,
    write_json,
)

VERSION = "11.12.0"
DEBT = 3320
PARENT_SHA = "2b8385034514cab167470982d780fceac6eacf97478c74d220a664c4c7cca407"
CARD_SHA = "c854fad704e08902051a3c4f2f25fdaeb8c9e7d32cda6b69bb76bf3fc6302134"
SNAPSHOT_SHA = "b813a94d5342013488b8192e8ecf940c898ce984e47fbe2fdcb95a3c570c5a51"
POLICIES = ("stable_lowrisk", "lowvol")
CLAIM_ROOT = Path(__file__).resolve().parents[1] / "artifacts/execution-evidence/claims"
PRICE_SQL = """
WITH raw AS (
 SELECT trade_date,instrument,open,adjustment_factor AS factor,
   lag(adjustment_factor) OVER w AS previous_factor,
   lag(trade_date) OVER w AS previous_date
 FROM read_parquet(?)
 WINDOW w AS (PARTITION BY instrument ORDER BY trade_date)
)
SELECT CAST(r.trade_date AS VARCHAR) AS date,r.instrument,r.open,r.factor,r.previous_factor,
       CAST(r.previous_date AS VARCHAR) AS previous_date
FROM raw r JOIN wanted k ON CAST(r.trade_date AS VARCHAR)=k.date AND r.instrument=k.instrument
WHERE r.trade_date BETWEEN DATE '2023-01-01' AND DATE '2024-12-31'
ORDER BY r.trade_date,r.instrument
"""


def saved_keys(accounts):
    keys = set()
    for periods in accounts.values():
        held = set()
        for p in periods:
            keys.update((p["date"], i) for i in held)
            keys.update(
                (p["date"], o["instrument"]) for o in p["orders"] if o["executed_notional"] > 0
            )
            held = {m["instrument"] for m in p["positions"] if m["shares"] > 0}
    return sorted(keys)


def extract_prices(path, keys):
    with duckdb.connect() as c:
        c.execute(
            "CREATE TABLE wanted(date VARCHAR,instrument VARCHAR,PRIMARY KEY(date,instrument))"
        )
        c.executemany("INSERT INTO wanted VALUES (?,?)", keys)
        rows = c.execute(PRICE_SQL, [str(path)]).fetchall()
        names = [col[0] for col in c.description]
    out = {}
    for row in rows:
        item = dict(zip(names, row, strict=True))
        key = (item.pop("date"), item.pop("instrument"))
        if key in out:
            raise ValueError("duplicate raw price key")
        for field in ("open", "factor", "previous_factor"):
            if item[field] is not None:
                item[field] = float(item[field])
                if not 0 < item[field] < float("inf"):
                    raise ValueError("invalid raw price/adjustment value")
        if item["open"] is None or item["factor"] is None:
            raise ValueError("missing raw price/adjustment value")
        out[key] = item
    return out


def run(config_path):
    cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    if type(cfg.get("preregistration_comment")) is not int or cfg["preregistration_comment"] <= 0:
        raise ValueError("positive preregistration comment required")
    parent, inputs, card, output = [
        Path(cfg[n]).resolve() for n in ("parent_dir", "input_dir", "original_card", "output_dir")
    ]
    if output.exists():
        raise FileExistsError("operation exists: inspect, never repeat")
    if any(
        output == p or p in output.parents or output in p.parents
        for p in (parent, inputs, card.parent)
    ):
        raise ValueError("independent output required")
    result_file, manifest_file = parent / "RESULT.json", inputs / "manifest.json"
    if file_sha(result_file) != PARENT_SHA or file_sha(card) != CARD_SHA:
        raise ValueError("parent/card bytes changed")
    previous = json.loads(result_file.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if previous["raw_global_trial_lower_bound"] != DEBT or not previous["engineering_pass"]:
        raise ValueError("prior debt/audit mismatch")
    if not json.loads((parent / "INDEPENDENT_AUDIT.json").read_text(encoding="utf-8"))["pass"]:
        raise ValueError("independent parent audit required")
    if (
        manifest["snapshot_sha256"] != SNAPSHOT_SHA
        or sha256_json(manifest["sources"]) != SNAPSHOT_SHA
    ):
        raise ValueError("snapshot manifest changed")
    sources = []
    for entry in manifest["sources"]:
        path = (inputs / entry["file"]).resolve()
        if path.parent != inputs or entry["max_date"] >= "2025-01-01":
            raise ValueError("snapshot path or date outside scope")
        if file_sha(path) != entry["sha256"]:
            raise ValueError("source snapshot bytes changed")
        sources.append(path)
    account_files = {p: parent / "accounts" / f"baseline_82-{p}.jsonl" for p in POLICIES}
    for p, path in account_files.items():
        if file_sha(path) != previous["records"]["baseline_82"][p]["account_sha256"]:
            raise ValueError("frozen account hash changed")
    protected = [
        result_file,
        manifest_file,
        card,
        parent / "registry.sqlite3",
        parent / "first_read_reservations.json",
        *sources,
        *account_files.values(),
    ]
    before, _ = protected_digest(protected)
    spec = {
        "version": VERSION,
        "issue": 184,
        "kind": "execution_evidence_diagnostic_not_backtest",
        "parent_sha256": PARENT_SHA,
        "card_sha256": CARD_SHA,
        "snapshot_sha256": SNAPSHOT_SHA,
        "raw_debt_before": DEBT,
        "reserved_new_trials": 2,
        "preregistration_comment": cfg["preregistration_comment"],
        "runtime_code_sha256": runtime_code_hash(),
        "driver_sha256": file_sha(Path(__file__)),
        "policies": list(POLICIES),
        "protected_before": before,
        "quantity_scope": "2023-2024 ordinary SH/SZ A-share buys; others explicit unsupported",
        "minimum_commission_cny": 5,
        "commission_bps": 6,
        "broker_confirmed": False,
        "new_accounts": 0,
        "new_fits": 0,
        "interpretation": "post-selection evidence; no PnL/NAV adjustment, no independent Court",
    }
    write_json(
        CLAIM_ROOT / (PARENT_SHA + ".json"),
        {"output": str(output), "spec_sha256": sha256_json(spec)},
    )
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "frozen_spec.json", spec)
    write_json(
        output / "first_read_reservations.json",
        {
            "policies": list(POLICIES),
            "reserved_new_trials": 2,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "spec_sha256": sha256_json(spec),
        },
    )
    try:
        registry = ExperimentRegistry(output / "registry.sqlite3")
        sid = registry.register_snapshot(
            build_composite_snapshot_manifest({"frozen": SNAPSHOT_SHA}), vendor_version=VERSION
        )
        eid = registry.create_experiment_deterministic(
            ExperimentSpec(
                "execution_evidence",
                "raw buy-ticket and held-event gap audit",
                sid,
                spec["runtime_code_sha256"],
                json.dumps(spec),
            ),
            sha256_json(spec),
        )
        tids = {
            p: registry.create_trial_deterministic(
                TrialSpec(
                    eid,
                    p,
                    sha256_json({"policy": p, "spec": spec}),
                    json.dumps({"diagnostic": p}),
                    184,
                    "unused",
                    "unused",
                    "2023-01-01",
                    "2024-12-31",
                    "unused",
                    "unused",
                    fit_stages=(),
                ),
                sha256_json({"policy": p, "spec": spec}),
            )[0]
            for p in POLICIES
        }
        # Native reservations exist before the first parsed account or numerical source read.
        accounts = {
            p: [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            for p, path in account_files.items()
        }
        if any(
            [d["date"] for d in accounts[p]] != previous["records"]["baseline_82"][p]["dates"]
            for p in POLICIES
        ):
            raise ValueError("saved account calendar mismatch")
        keys = saved_keys(accounts)
        prices = extract_prices(inputs / "daily.parquet", keys)
        write_json(
            output / "raw_price_query.json",
            {
                "sql": PRICE_SQL,
                "parameter": "daily.parquet",
                "source_sha256": file_sha(inputs / "daily.parquet"),
                "wanted_keys": len(keys),
                "matched_keys": len(prices),
            },
        )
        # Private bounded evidence supports an independent offline notebook audit.
        write_json(
            output / "raw_price_evidence.json",
            [dict(date=k[0], instrument=k[1], **v) for k, v in prices.items()],
        )
        records, all_review = {}, {}
        for p in POLICIES:
            summary, tickets, review = audit_saved_account(accounts[p], prices)
            lineage = registry.fit_lineage(tids[p])
            if lineage["stages"] or lineage["fits"]:
                raise ValueError("diagnostic must not fit a model")
            summary["fit_lineage_sha256"] = lineage["sha256"]
            records[p] = summary
            write_json(output / f"tickets-{p}.json", tickets)
            write_json(output / f"event-review-{p}.json", review)
            for item in review:
                key = (item["date"], item["instrument"], item["reason"])
                all_review[key] = {
                    **item,
                    "policies": sorted(set(all_review.get(key, {}).get("policies", [])) | {p}),
                }
            registry.record_trial_result(tids[p], json.dumps(summary, sort_keys=True))
        write_json(output / "scoped-event-worklist.json", list(all_review.values()))
        if (
            protected_digest(protected)[0] != before
            or runtime_code_hash() != spec["runtime_code_sha256"]
            or file_sha(Path(__file__)) != spec["driver_sha256"]
        ):
            raise ValueError("source/runtime changed during audit")
        result = {
            "version": VERSION,
            "spec": spec,
            "records": records,
            "reserved_new_trials": 2,
            "completed_diagnostic_trials": 2,
            "new_account_trials": 0,
            "new_model_fits": 0,
            "raw_global_trial_lower_bound": DEBT + 2,
            "restricted_rows_read": 0,
            "source_files_unchanged": True,
            "engineering_pass": True,
            "validated_alpha": False,
            "physical_execution_verified": False,
            "scoped_event_worklist_keys": len(all_review),
            "decision": "FROZEN_ALLOCATION_RETAINED_EXECUTION_EVIDENCE_INCOMPLETE",
        }
        write_json(output / "RESULT.json", result)
        print(
            json.dumps(
                {
                    "records": records,
                    "scoped_event_worklist_keys": len(all_review),
                    "raw_trial_lower_bound": DEBT + 2,
                }
            ),
            flush=True,
        )
        return result
    except Exception as exc:
        write_json(
            output / "ABORTED.json",
            {"error_type": type(exc).__name__, "reservations_preserved": True},
        )
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    run(parser.parse_args().config)
