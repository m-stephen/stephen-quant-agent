"""Append actual yearly-fit lineage; preserve legacy static registry columns."""

import json
import sqlite3
from pathlib import Path

from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.qmt.reliable_panel import file_sha
from stephen_quant.workflows.v114_reliable_epoch import write_json

ROOT = Path("artifacts/residual-mechanisms/epoch-001")


def run():
    result = json.loads((ROOT / "RESULT.json").read_text(encoding="utf-8"))
    reservations = json.loads((ROOT / "first_read_reservations.json").read_text(encoding="utf-8"))
    plans = {p["identity"]: p for p in reservations["trials"]}
    registry_path = ROOT / "registry.sqlite3"
    with sqlite3.connect(f"file:{registry_path.as_posix()}?mode=ro", uri=True) as con:
        trials = con.execute(
            "SELECT trial_id,factor_set,hyperparams,train_start,train_end FROM trials"
        ).fetchall()
    bindings = []
    for tid, identity, params, start, end in trials:
        plan = plans[identity]
        if json.loads(params) != plan:
            raise ValueError("trial plan binding changed")
        years = [str(plan["year"])] if plan["kind"] == "fit" else ["2023", "2024"]
        bindings.append(
            {
                "trial_id": tid,
                "plan_identity": identity,
                "policy": plan["policy"],
                "kind": plan["kind"],
                "legacy_train_start": start,
                "legacy_train_end": end,
                "actual_fit_components": [
                    {
                        "deployment_year": y,
                        "training_start": "2022-01-01",
                        "fit_cutoff": result["models"][y]["fit_cutoff"],
                        "maximum_label_end": result["models"][y]["maximum_label_end"],
                        "model_artifact_sha256": file_sha(ROOT / "models" / f"{y}.json"),
                    }
                    for y in years
                ]
                if plan["policy"] in result["checks"]
                else [],
                "uses_fitted_model": plan["policy"] in result["checks"],
            }
        )
    if len(bindings) != 21:
        raise ValueError("complete trial bindings required")
    document = {
        "status": "APPEND_ONLY_LINEAGE_CLARIFICATION",
        "trial_delta": 0,
        "source_result_sha256": file_sha(ROOT / "RESULT.json"),
        "source_registry_sha256": file_sha(registry_path),
        "limitation": "legacy static2022 training columns do not represent2024 expanding fit;use these artifact-bound components,not scalar registry columns,for fit-lineage audits",
        "raw_registry_unchanged": True,
        "financial_results_unchanged": True,
        "bindings": sorted(bindings, key=lambda x: x["plan_identity"]),
    }
    document["bindings_sha256"] = sha256_json(document["bindings"])
    write_json(ROOT / "MODEL_FIT_LINEAGE.json", document)
    write_json(Path("docs/V11_10_FIT_LINEAGE.json"), document)
    print(
        json.dumps(
            {
                "bindings": len(bindings),
                "bindings_sha256": document["bindings_sha256"],
                "registry_unchanged": file_sha(registry_path) == document["source_registry_sha256"],
            }
        )
    )


if __name__ == "__main__":
    run()
