"""Finite, date-balanced response predictor; still requires a complete epoch runner.

The ridge score estimates relative gross returns, not executable net returns or
a causal effect. All controls consume exactly the same eligible feature rows.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

import numpy as np

from stephen_quant.evaluation import average_ranks
from stephen_quant.integrity.fit_lineage import FitStage

from .flow_response_series import validate_calendar
from .pairwise_ranking import leg_label
from .search_power_dsl import sha256_json

VERSION = "11.21-response-predictor-1"
HORIZON, STRIDE, EMBARGO, L2 = 20, 5, 5, 0.01
RISK = ("volatility_20", "ret_20", "liquidity")
INPUTS = RISK + (
    "flow_ratio",
    "close_return",
    "flow_surprise",
    "standardized_own_return",
    "price_response_residual",
)
POLICIES = (
    "response",
    "response_interaction",
    "risk",
    "raw_flow_return",
    "standardized_flow_return",
    "old_absorption",
    "shuffle",
)


def stages():
    return tuple(
        FitStage(str(y), "2022-01-01", f"{y - 1}-12-31", f"{y}-01-01", f"{y}-12-31")
        for y in (2023, 2024)
    )


def prefix(calendar, year):
    validate_calendar(calendar)
    if year not in (2023, 2024):
        raise ValueError("registered predictor year required")
    days = [d for d in calendar if d < f"{year}-01-01"]
    if len(days) <= HORIZON + EMBARGO + 1:
        raise ValueError("insufficient mature training prefix")
    return days[:-EMBARGO]


def ranked_rows(features):
    """Current support intersection before any outcome inspection, same for all policies."""
    names = sorted(
        n for n, row in features.items() if all(k in row and math.isfinite(row[k]) for k in INPUTS)
    )
    bins, cells = defaultdict(list), defaultdict(list)
    for i, n in enumerate(sorted(names, key=lambda n: (features[n]["volatility_20"], n))):
        bins[5 * i // len(names)].append(n)
    for v, members in bins.items():
        members.sort(key=lambda n: (features[n]["liquidity"], n))
        for i, n in enumerate(members):
            cells[v * 4 + 4 * i // len(members)].append(n)
    result = {}
    for cell, members in cells.items():
        members.sort()
        ranked = {
            k: dict(
                zip(
                    members,
                    (
                        2 * r / (len(members) + 1) - 1
                        for r in average_ranks([features[n][k] for n in members])
                    ),
                    strict=True,
                )
            )
            for k in INPUTS
        }
        for n in members:
            result[n] = {
                "cell": cell,
                "ranks": {k: ranked[k][n] for k in INPUTS},
                "vol": features[n]["volatility_20"],
            }
    return result


def vector(row, policy):
    if policy not in POLICIES:
        raise ValueError("unregistered response policy")
    r = row["ranks"]
    if set(r) != set(INPUTS) or not all(math.isfinite(v) and -1 <= v <= 1 for v in r.values()):
        raise ValueError("complete bounded common-support ranks required")
    common = [r[k] for k in RISK]
    extras = {
        "risk": [],
        "raw_flow_return": [r["flow_ratio"], r["close_return"]],
        "standardized_flow_return": [r["flow_surprise"], r["standardized_own_return"]],
        "old_absorption": [-r["flow_ratio"] * r["ret_20"]],
        "response": [r["flow_surprise"], r["price_response_residual"]],
    }
    interaction = extras["response"] + [r["flow_surprise"] * r["price_response_residual"]]
    return common + (
        interaction if policy in ("response_interaction", "shuffle") else extras[policy]
    )


def pairs_for_year(calendar, feature_rows, bars, year):
    days = prefix(calendar, year)  # No label or feature construction outside this prefix.
    bar_prefix = [bars[d] for d in days]
    result = []
    for i in range(0, len(days) - HORIZON - 1, STRIDE):
        dt = days[i]
        rows = feature_rows[dt]
        groups = defaultdict(list)
        for n, row in rows.items():
            groups[row["cell"]].append(n)
        for cell, members in sorted(groups.items()):
            ordered = sorted(
                members, key=lambda n: (hashlib.sha256(f"v11.21:184:{n}".encode()).hexdigest(), n)
            )[:64]
            for j in range(0, len(ordered) - 1, 2):
                a, b = ordered[j : j + 2]
                left, right = leg_label(bar_prefix, i, a), leg_label(bar_prefix, i, b)
                result.append(
                    {
                        "date": dt,
                        "entry_date": days[i + 1],
                        "label_end": days[i + HORIZON + 1],
                        "cell": cell,
                        "left": a,
                        "right": b,
                        "left_row": rows[a],
                        "right_row": rows[b],
                        "left_label": left,
                        "right_label": right,
                        "supported": left["entry_valid"] and right["entry_valid"],
                    }
                )
    return result


def fit_predictor(pairs, calendar, year, policy):
    if policy not in POLICIES:
        raise ValueError("unregistered response policy")
    days = prefix(calendar, year)
    allowed, cutoff = set(days), days[-1]
    indices = {d: i for i, d in enumerate(days)}
    rows = []
    for row in pairs:
        # Maturity filtering must precede numeric values, including poisoned future labels.
        if row["date"] < "2022-01-01" or row["date"] > cutoff or row["label_end"] > cutoff:
            continue
        if not row["date"] < row["entry_date"] < row["label_end"]:
            raise ValueError("invalid training pair chronology")
        if any(row[k] not in allowed for k in ("date", "entry_date", "label_end")):
            raise ValueError("training pair outside explicit global calendar")
        i = indices[row["date"]]
        if (
            row["entry_date"] != days[i + 1]
            or i + HORIZON + 1 >= len(days)
            or row["label_end"] != days[i + HORIZON + 1]
            or i % STRIDE
        ):
            raise ValueError("pair label horizon/stride changed")
        if not row["supported"]:
            continue
        if not row["left_label"]["entry_valid"] or not row["right_label"]["entry_valid"]:
            raise ValueError("supported label lacks valid entry")
        if (
            row["left"] == row["right"]
            or row["cell"] not in range(20)
            or any(row[k]["cell"] != row["cell"] for k in ("left_row", "right_row"))
        ):
            raise ValueError("pair cell/identity mismatch")
        rows.append(row)
    keys = [(r["date"], r["left"], r["right"]) for r in rows]
    legs = [(r["date"], n) for r in rows for n in (r["left"], r["right"])]
    if (
        len(set(keys)) != len(keys)
        or len(set(legs)) != len(legs)
        or [r["date"] for r in rows] != sorted(r["date"] for r in rows)
    ):
        raise ValueError("duplicate/overlapping/unordered training pairs")
    counts = Counter(r["date"] for r in rows)
    if len(counts) < 30:
        raise ValueError("minimum30 actual mature training dates required")
    x = np.asarray(
        [
            [
                a - b
                for a, b in zip(
                    vector(r["left_row"], policy), vector(r["right_row"], policy), strict=True
                )
            ]
            for r in rows
        ]
    )
    outcomes = [[r["left_label"]["return"], r["right_label"]["return"]] for r in rows]
    if not all(v is not None and math.isfinite(v) and v >= -1 for pair in outcomes for v in pair):
        raise ValueError("finite mature leg returns required")
    if policy == "shuffle":
        grouped = defaultdict(list)
        for i, r in enumerate(rows):
            grouped[r["date"], r["cell"]].append(i)
        for indices in grouped.values():
            flat = [v for i in indices for v in outcomes[i]]
            shift = len(flat) // 3
            flat = flat[-shift:] + flat[:-shift] if shift else flat
            for j, i in enumerate(indices):
                outcomes[i] = flat[2 * j : 2 * j + 2]
    y = np.asarray([a - b for a, b in outcomes])
    weights = np.asarray([1 / (len(counts) * counts[r["date"]]) for r in rows])
    beta = np.linalg.solve(
        x.T @ (weights[:, None] * x) + L2 * np.eye(x.shape[1]), x.T @ (weights * y)
    )
    if not np.isfinite(beta).all():
        raise ValueError("nonfinite response predictor")
    gradient = x.T @ (weights * (x @ beta - y)) + L2 * beta
    if float(np.max(np.abs(gradient))) > 1e-9:
        raise ValueError("response ridge normal equations failed")
    return {
        "version": VERSION,
        "year": year,
        "policy": policy,
        "l2": L2,
        "fit_cutoff": cutoff,
        "maximum_label_end": max(r["label_end"] for r in rows),
        "training_signal_sessions": sorted(counts),
        "training_signal_dates": len(counts),
        "training_pairs": len(rows),
        "training_rows_sha256": sha256_json(rows),
        "training_design_sha256": sha256_json(
            {"x": x.tolist(), "y": y.tolist(), "weights": weights.tolist()}
        ),
        "weights": beta.tolist(),
        "parameter_count": len(beta),
        "gradient_max": float(np.max(np.abs(gradient))),
        "date_weight": 1 / len(counts),
        "not_causal": True,
        "validated_alpha": False,
    }


def assert_predictor_contract(
    registry, trial_id, provider_id, year, policy, artifact_path, *, new_artifact=True
):
    sources = registry.feature_sources(trial_id)  # Before reading pairs or fitting anything.
    if sources["providers"] != [provider_id]:
        raise ValueError("exact response provider required before supervised fit")
    stage = next((s for s in stages() if s.stage_id == str(year)), None)
    with registry.connect() as conn:
        row = conn.execute(
            "SELECT f.stages_json,t.hyperparams,t.result_json FROM trial_fit_contracts f JOIN trials t USING(trial_id) WHERE trial_id=?",
            (trial_id,),
        ).fetchone()
        already = conn.execute(
            "SELECT 1 FROM trial_model_fits WHERE trial_id=? AND stage_id=?", (trial_id, str(year))
        ).fetchone()
    if (
        row is None
        or stage is None
        or asdict(stage) not in json.loads(row[0])
        or json.loads(row[1]).get("response_policy") != policy
        or row[2] is not None
        or already
    ):
        raise ValueError("unfitted predeclared supervised stage/policy required")
    path = Path(artifact_path)
    if new_artifact and path.exists():
        raise FileExistsError(path.name)
    return sources


def fit_and_bind_predictor(
    registry,
    trial_id,
    provider_id,
    *,
    pairs,
    calendar,
    year,
    policy,
    artifact_path,
    training_provenance=None,
):
    sources = assert_predictor_contract(
        registry, trial_id, provider_id, year, policy, artifact_path
    )
    path = Path(artifact_path)
    model = fit_predictor(pairs, calendar, year, policy)
    model["feature_sources_sha256"] = sources["sha256"]
    if training_provenance is not None:
        model["training_provenance"] = training_provenance
    # Generated fit artifact, exclusive and never a hand-supplied model digest.
    with path.open("x", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(model, sort_keys=True, allow_nan=False))
    registry.record_model_fit(trial_id, str(year), model=model, artifact_path=path)
    return model


def predict(model, rows):
    if (
        model["version"] != VERSION
        or model["l2"] != L2
        or not all(math.isfinite(v) for v in model["weights"])
    ):
        raise ValueError("response predictor identity/weights changed")
    result = {}
    for name, row in rows.items():
        x = vector(row, model["policy"])
        if len(x) != model["parameter_count"] or len(x) != len(model["weights"]):
            raise ValueError("response parameter count mismatch")
        result[name] = sum(a * b for a, b in zip(x, model["weights"], strict=True))
    return result


def guarded_predict(registry, trial_id, *, model, path, signal_date, execution_date, rows):
    sources = registry.feature_sources(trial_id)
    if sources["sha256"] != model["feature_sources_sha256"]:
        raise ValueError("predictor feature-source evidence changed")
    registry.assert_prediction_fit(
        trial_id,
        model=model,
        artifact_path=path,
        signal_date=signal_date,
        prediction_date=execution_date,
    )
    return predict(model, rows)
