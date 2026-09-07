"""Independent frozen model score -> global target -> saved-account audit.

No production predictor, global selector, sleeve combiner or execution engine is
called by the mathematical reference. Shared native/hash/source-audit utilities
remain intact. This numerical audit is not empirical launch authority or Alpha.
"""

from __future__ import annotations

import math
from pathlib import Path

from stephen_quant.qmt.reliable_panel import file_sha

from .flow_response_epoch_audit import audit_saved_accounts, read_bound_file
from .flow_response_launch import ReadOnlyRegistry, _bound, read
from .flow_response_source_audit import audit_source_history
from .search_power_dsl import sha256_json
from .signal_construction import POLICIES, VERSION, contract
from .signal_construction_runtime import check_native, open_inputs


def independent_scores(model, rows, policy, year):
    fields = ["volatility_20", "ret_20", "liquidity"]
    if policy == "global_response":
        fields += ["flow_surprise", "price_response_residual"]
    elif policy != "global_risk":
        raise ValueError("two independent bridge score references only")
    if (
        model["version"] != "11.21-response-predictor-1"
        or model["year"] != year
        or model["policy"] != policy.removeprefix("global_")
        or model["l2"] != 0.01
        or model["parameter_count"] != len(fields)
        or len(model["weights"]) != len(fields)
        or any(not math.isfinite(w) for w in model["weights"])
    ):
        raise ValueError("independent frozen model contract differs")
    required = {
        "volatility_20",
        "ret_20",
        "liquidity",
        "flow_ratio",
        "close_return",
        "flow_surprise",
        "standardized_own_return",
        "price_response_residual",
    }
    result = {}
    for name, row in rows.items():
        if set(row["ranks"]) != required or any(
            type(x) not in (int, float) or not math.isfinite(x) or not -1 <= x <= 1
            for x in row["ranks"].values()
        ):
            raise ValueError("independent full original support required")
        # Frozen Python3.10 left-to-right binary64 addition, no extra normalization.
        value = 0.0
        for index, field in enumerate(fields):
            value += row["ranks"][field] * model["weights"][index]
        result[name] = value
    return result


def independent_targets(history, policy, models):
    if policy not in POLICIES or set(models) != {2023, 2024}:
        raise ValueError("fixed two-policy/two-year bridge required")
    calendar = list(history["calendar"])
    if (
        not calendar
        or calendar != sorted(set(calendar))
        or any(not "2022-01-01" <= d <= "2024-12-31" for d in calendar)
    ):
        raise ValueError("independent ordered historical calendar required")
    days = [d for d in calendar if d >= "2023-01-01"]
    if not days:
        raise ValueError("independent execution dates required")
    states = [() for _ in range(4)]
    targets, diagnostics = [], []
    for index, day in enumerate(days):
        signal = days[index - 1] if index else None
        refresh = False
        for sleeve, phase in enumerate((0, 5, 10, 15)):
            if index < phase + 1 or (index - phase - 1) % 20:
                continue
            refresh = True
            rows = history["ranks"][signal]
            scores = independent_scores(models[int(day[:4])], rows, policy, int(day[:4]))
            ranked = sorted(rows, key=lambda n: (-scores[n], n))
            prior = set(states[sleeve])
            chosen = set([n for n in ranked[:60] if n in prior][:40])
            for name in ranked:
                if len(chosen) >= 40:
                    break
                chosen.add(name)
            ordered = tuple(sorted(chosen))
            diagnostics.append(
                {
                    "date": signal,
                    "execution_date": day,
                    "phase": phase,
                    "eligible": len(rows),
                    "selected": len(ordered),
                    "new_members": len(chosen - prior),
                    "scores_sha256": sha256_json(scores),
                    "selected_names_sha256": sha256_json(ordered),
                    "selected_mean_vol": sum(rows[n]["vol"] for n in ordered) / len(ordered)
                    if ordered
                    else None,
                    "selected_cell_counts": [
                        sum(rows[n]["cell"] == c for n in ordered) for c in range(20)
                    ],
                }
            )
            states[sleeve] = ordered
        weights = {}
        if refresh:
            for cohort in states:
                for name in cohort:
                    weights[name] = weights.get(name, 0.0) + 0.00625
        targets.append(
            {
                "trade_date": day,
                "decided_at": f"{signal}T23:59:59+08:00" if signal else f"{day}T08:00:00+08:00",
                "weights": weights,
                "rebalance": refresh,
                "forced_exits": [],
            }
        )
    diagnostics.sort(key=lambda d: (d["phase"], d["execution_date"]))
    return targets, diagnostics


def audit_targets(root, result, history, models):
    bound = {}
    for policy in POLICIES:
        targets, diagnostic = independent_targets(
            history, policy, models[policy.removeprefix("global_")]
        )
        expected = result["targets_sha256"][policy]
        actual = read_bound_file(root, f"targets/{policy}.json", expected)
        if sha256_json(targets) != sha256_json(actual) or sha256_json(diagnostic) != sha256_json(
            result["diagnostics"][policy]
        ):
            raise ValueError("independent score/retention/calendar/target/style mismatch")
        bound[policy] = expected
    return bound


def audit_complete_accounts(*, operation, input_folder):
    root = Path(operation).resolve(strict=True)
    before = {
        name: _bound(root, name) for name in ("RESULT.json", "frozen_spec.json", "registry.sqlite3")
    }
    result, spec = read(root / "RESULT.json"), read(root / "frozen_spec.json")
    registry = ReadOnlyRegistry(root / "registry.sqlite3")
    check_native(registry, root, spec, result["trial_ids"], result)
    old, inherited, models, _paths, fingerprints, cache, history, proof = open_inputs(spec, root)
    if result["models_sha256"] != fingerprints:
        raise ValueError("actual inherited model evidence differs")
    consumer = spec["inherited"]["trial_ids"]["response-82"]
    source = audit_source_history(
        old,
        consumer,
        history_path=inherited / "history/history.json",
        input_folder=input_folder,
        cache=cache,
    )
    targets = audit_targets(root, result, history, models)
    accounts, reports = audit_saved_accounts(
        root, result, result["trial_ids"], history, contract()["accounts"]
    )
    if any(
        sha256_json(a) != sha256_json(result["records"][k]["audit"]) for k, a in accounts.items()
    ):
        raise ValueError("saved native account audit differs from independent reconstruction")
    cache.get(old, consumer, inherited / "history/history.json")
    _bound(inherited, "registry.sqlite3", spec["inherited"]["files"]["registry.sqlite3"])
    if any(file_sha(root / name) != digest for name, digest in before.items()):
        raise ValueError("completed evidence changed during independent audit")
    return {
        "version": VERSION,
        "pipeline_audit_pass": True,
        "validated_alpha": False,
        "launch_authorization_verified": False,
        "new_native_accounts_checked": 4,
        "raw_global_trial_lower_bound": 3737,
        "new_fits": 0,
        "result_sha256": before["RESULT.json"],
        "native_registry_sha256": before["registry.sqlite3"],
        "spec_file_sha256": before["frozen_spec.json"],
        "spec_sha256": sha256_json(spec),
        "history_sha256": proof["history_artifact_sha256"],
        "models_sha256": fingerprints,
        "calendar": spec["calendar"],
        "completed_parent_evidence_sha256": spec["completed_parent_evidence_sha256"],
        "source_audit": source,
        "independent_target_sha256": targets,
        "accounts": accounts,
        "full_account_report_sha256": reports,
        "statistics": contract()["statistics"],
    }
