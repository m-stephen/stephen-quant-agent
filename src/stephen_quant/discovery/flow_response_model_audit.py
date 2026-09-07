"""Independent mature-pair regression and target reconstruction.

Audit uses already source-audited persisted ranks/bars. The reference constructs
labels and the design separately and solves an augmented least-squares problem,
not the production normal equations. No production scoring or selector is called.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from stephen_quant.qmt.reliable_panel import file_sha

from .flow_response_history import read_verified_history
from .flow_response_reference import FIELDS, validate_days
from .flow_response_source_audit import compare
from .search_power_dsl import sha256_json

POLICIES = (
    "response",
    "response_interaction",
    "risk",
    "raw_flow_return",
    "standardized_flow_return",
    "old_absorption",
    "shuffle",
)


def name_hash(name):
    return hashlib.sha256(f"v11.21:184:{name}".encode()).hexdigest()


def reference_vector(row, policy):
    r = row["ranks"]
    if set(r) != set(FIELDS) or policy not in POLICIES:
        raise ValueError("reference scoring contract mismatch")
    result = [r["volatility_20"], r["ret_20"], r["liquidity"]]
    if policy == "risk":
        return result
    if policy == "raw_flow_return":
        return result + [r["flow_ratio"], r["close_return"]]
    if policy == "standardized_flow_return":
        return result + [r["flow_surprise"], r["standardized_own_return"]]
    if policy == "old_absorption":
        return result + [-r["flow_ratio"] * r["ret_20"]]
    result.extend((r["flow_surprise"], r["price_response_residual"]))
    if policy != "response":
        result.append(r["flow_surprise"] * r["price_response_residual"])
    return result


def reference_pairs(history, year):
    validate_days(history["calendar"])
    if year not in (2023, 2024):
        raise ValueError("reference frozen fit year required")
    days = [d for d in history["calendar"] if d < f"{year}-01-01"][:-5]
    if len(days) < 27:
        raise ValueError("reference lacks mature prefix")

    def label(i, n):
        entry = history["bars"][days[i + 1]].get(n)
        if not entry or not np.isfinite(entry["open_price"]) or entry["open_price"] <= 0:
            return {
                "entry_valid": False,
                "return": None,
                "entry_price": None,
                "end_price": None,
                "mark_date": None,
                "fresh_end": False,
            }
        final = history["bars"][days[i + 21]].get(n)
        if final and np.isfinite(final["open_price"]) and final["open_price"] > 0:
            price, mark_date, fresh = final["open_price"], days[i + 21], True
        else:
            price, mark_date, fresh = entry["open_price"], days[i + 1], False
            for j in reversed(range(i + 1, i + 21)):
                prior = history["bars"][days[j]].get(n)
                if prior and np.isfinite(prior["close_price"]) and prior["close_price"] > 0:
                    price, mark_date = prior["close_price"], days[j]
                    break
        return {
            "entry_valid": True,
            "return": price / entry["open_price"] - 1,
            "entry_price": entry["open_price"],
            "end_price": price,
            "mark_date": mark_date,
            "fresh_end": fresh,
        }

    rows = []
    for i in range(0, len(days) - 21, 5):
        day = days[i]
        groups = defaultdict(list)
        for n, value in history["ranks"][day].items():
            groups[value["cell"]].append(n)
        for cell in sorted(groups):
            members = sorted(groups[cell], key=lambda n: (name_hash(n), n))[:64]
            for a, b in zip(members[::2], members[1::2]):
                left, right = label(i, a), label(i, b)
                if left["entry_valid"] and right["entry_valid"]:
                    rows.append(
                        {
                            "date": day,
                            "entry_date": days[i + 1],
                            "label_end": days[i + 21],
                            "cell": cell,
                            "left": a,
                            "right": b,
                            "left_row": history["ranks"][day][a],
                            "right_row": history["ranks"][day][b],
                            "left_label": left,
                            "right_label": right,
                            "supported": True,
                        }
                    )
    return days, rows


def reference_fit(history, year, policy):
    days, rows = reference_pairs(history, year)
    counts = Counter(r["date"] for r in rows)
    if len(counts) < 30:
        raise ValueError("reference needs30 mature dates")
    x = np.asarray(
        [
            [
                a - b
                for a, b in zip(
                    reference_vector(r["left_row"], policy),
                    reference_vector(r["right_row"], policy),
                    strict=True,
                )
            ]
            for r in rows
        ]
    )
    outcomes = [[r["left_label"]["return"], r["right_label"]["return"]] for r in rows]
    if policy == "shuffle":
        groups = defaultdict(list)
        for i, r in enumerate(rows):
            groups[r["date"], r["cell"]].append(i)
        for group in groups.values():
            flat = [value for i in group for value in outcomes[i]]
            count, offset = len(flat), len(flat) // 3
            for j, index in enumerate(group):
                outcomes[index] = [flat[(2 * j + k - offset) % count] for k in (0, 1)]
    y = np.asarray([a - b for a, b in outcomes])
    weight = np.asarray([1 / (len(counts) * counts[r["date"]]) for r in rows])
    if not all(np.isfinite(v).all() for v in (x, y, weight)):
        raise ValueError("reference nonfinite supervised design")
    # Augmented system solved by SVD, not copied production normal equations.
    augmented = np.vstack((np.sqrt(weight)[:, None] * x, 0.1 * np.eye(x.shape[1])))
    outcome = np.concatenate((np.sqrt(weight) * y, np.zeros(x.shape[1])))
    beta, _, rank, _ = np.linalg.lstsq(augmented, outcome, rcond=None)
    if rank != x.shape[1] or not np.isfinite(beta).all():
        raise ValueError("reference unidentified supervised fit")
    return {
        "year": year,
        "policy": policy,
        "l2": 0.01,
        "fit_cutoff": days[-1],
        "maximum_label_end": max(r["label_end"] for r in rows),
        "training_signal_sessions": sorted(counts),
        "training_signal_dates": len(counts),
        "training_pairs": len(rows),
        "training_rows_sha256": sha256_json(rows),
        "training_design_sha256": sha256_json(
            {"x": x.tolist(), "y": y.tolist(), "weights": weight.tolist()}
        ),
        "weights": beta.tolist(),
        "parameter_count": len(beta),
        "date_weight": 1 / len(counts),
        "gradient_max": float(np.max(np.abs(x.T @ (weight * (x @ beta - y)) + 0.01 * beta))),
    }


def reference_targets(history, policy, models=None):
    if policy not in POLICIES + ("hash", "lowvol"):
        raise ValueError("reference target policy not registered")
    days = [d for d in history["calendar"] if d >= "2023-01-01"]
    live = [() for _ in range(4)]
    result, diagnostics = [], []
    for i, day in enumerate(days):
        signal, refreshed = days[i - 1] if i else None, False
        for slot, phase in enumerate((0, 5, 10, 15)):
            if i < phase + 1 or (i - phase - 1) % 20:
                continue
            refreshed = True
            rows = history["ranks"][signal]
            values = {}
            for n, row in rows.items():
                if policy == "hash":
                    values[n] = int(name_hash(n), 16)
                elif policy == "lowvol":
                    values[n] = -row["vol"]
                else:
                    score = 0.0
                    for a, b in zip(
                        reference_vector(row, policy), models[int(day[:4])]["weights"], strict=True
                    ):
                        score += a * b
                    values[n] = score
            chosen = []
            for cell in range(20):
                names = sorted(
                    (n for n in rows if rows[n]["cell"] == cell), key=lambda n: (-values[n], n)
                )
                keep = [n for n in names[:3] if n in live[slot]][:2]
                for n in names:
                    if len(keep) == 2:
                        break
                    if n not in keep:
                        keep.append(n)
                chosen.extend(keep)
            chosen.sort()
            diagnostics.append(
                {
                    "date": signal,
                    "execution_date": day,
                    "phase": phase,
                    "eligible": len(rows),
                    "selected": len(chosen),
                    "new_members": len(set(chosen) - set(live[slot])),
                    "scores_sha256": sha256_json(values),
                }
            )
            live[slot] = tuple(chosen)
        weights = {}
        if refreshed:
            for sleeve in live:
                for n in sleeve:
                    weights[n] = weights.get(n, 0.0) + 0.025 / 4
        result.append(
            {
                "trade_date": day,
                "decided_at": f"{signal}T23:59:59+08:00" if signal else f"{day}T08:00:00+08:00",
                "weights": weights,
                "rebalance": refreshed,
                "forced_exits": [],
            }
        )
    return result, sorted(diagnostics, key=lambda d: (d["phase"], d["date"]))


def audit_models_targets(registry, tids, *, history_path, operation):
    """Read-only completed-epoch audit. Must be combined with source/account audits."""
    root = Path(operation).resolve(strict=True)
    if Path(registry.db_path).resolve() != root / "registry.sqlite3":
        raise ValueError("audit registry must belong to the operation")
    epoch_result = json.loads((root / "RESULT.json").read_bytes())
    history, proof = read_verified_history(registry, tids["response-82"], history_path)
    models, fingerprints = {}, {}
    for policy in POLICIES:
        models[policy] = {}
        for year in (2023, 2024):
            path = root / f"models/{policy}-{year}.json"
            if root not in path.resolve(strict=True).parents:
                raise ValueError("audited model escaped operation")
            model = json.loads(path.read_bytes())
            dates = [d for d in history["calendar"] if d.startswith(str(year))]
            for cost in (82, 164):
                registry.assert_prediction_fit(
                    tids[f"{policy}-{cost}"],
                    model=model,
                    artifact_path=path,
                    signal_date=dates[0],
                    prediction_date=dates[1],
                )
            if (
                model["training_provenance"]["history_artifact_sha256"]
                != proof["history_artifact_sha256"]
            ):
                raise ValueError("model belongs to different history")
            expected = reference_fit(history, year, policy)
            prefix_days, _ = reference_pairs(history, year)
            expected_provenance = proof | {
                "training_prefix_sha256": sha256_json(
                    {
                        "calendar": prefix_days,
                        "ranks": {d: history["ranks"][d] for d in prefix_days},
                        "bars": {d: history["bars"][d] for d in prefix_days},
                        "days": {
                            d: history["days"][d] for d in prefix_days if d in history["days"]
                        },
                    }
                )
            }
            compare(
                model["training_provenance"],
                expected_provenance,
                label=f"training-provenance:{policy}:{year}",
            )
            compare({k: model[k] for k in expected}, expected, label=f"supervised:{policy}:{year}")
            models[policy][year] = model
            fingerprints[f"{policy}-{year}"] = file_sha(path)
    target_hashes = {}
    for policy in POLICIES + ("hash", "lowvol"):
        expected, diagnostic = reference_targets(history, policy, models.get(policy))
        compare(epoch_result["diagnostics"][policy], diagnostic, label=f"diagnostics:{policy}")
        path = root / f"targets/{policy}.json"
        if root not in path.resolve(strict=True).parents:
            raise ValueError("audited targets escaped operation")
        actual = json.loads(path.read_bytes())
        compare(actual, expected, label=f"targets:{policy}")
        for cost in (82, 164):
            with registry.connect() as conn:
                result = json.loads(
                    conn.execute(
                        "SELECT result_json FROM trials WHERE trial_id=?",
                        (tids[f"{policy}-{cost}"],),
                    ).fetchone()[0]
                )
            if result["target_sha256"] != file_sha(path):
                raise ValueError("native account targets changed")
        target_hashes[policy] = file_sha(path)
    return {
        "supervised_model_target_audit_pass": True,
        "complete_pipeline_audit_pass": False,
        "validated_alpha": False,
        "models_checked": len(fingerprints),
        "native_bindings_checked": 28,
        "policies_checked": len(target_hashes),
        "models_sha256": fingerprints,
        "targets_sha256": target_hashes,
        **proof,
        "independent_solver": "augmented weighted ridge SVD least-squares",
        "pending": "combine independent source proof,original anchors and execution scheduling/fills audit",
    }
