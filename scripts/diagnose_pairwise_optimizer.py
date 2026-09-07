"""Repeat the frozen training-only arithmetic to diagnose an aborted solver; no new policy."""

import gzip
import json
from pathlib import Path

import numpy as np

from stephen_quant.discovery.pairwise_ranking import design_matrix, objective
from stephen_quant.workflows.v114_reliable_epoch import write_json

root = Path("artifacts/pairwise-ranking/epoch-001")
with gzip.open(root / "training_pairs.json.gz", "rt", encoding="utf-8") as stream:
    pairs = json.load(stream)
calendar = json.loads((root / "calendar.json").read_text())
cutoff = [d for d in calendar if d < "2024-01-01"][-6]
rows = [r for r in pairs if r["supported"] and r["label_end"] <= cutoff]
x, y, weights = design_matrix(rows, "quadratic", "full")
beta = np.zeros(x.shape[1])
trace = []
for i in range(40):
    loss, grad, hessian = objective(beta, x, y, weights)
    row = {"step": i, "loss": loss, "max_gradient": float(max(abs(grad))), "backtracking": []}
    trace.append(row)
    if max(abs(grad)) <= 1e-9:
        break
    step = np.linalg.solve(hessian, grad)
    for backoff in range(32):
        scale = 0.5**backoff
        candidate = beta - scale * step
        new_loss, new_grad, _ = objective(candidate, x, y, weights)
        row["backtracking"].append(
            {
                "scale": scale,
                "loss": new_loss,
                "loss_difference": new_loss - loss,
                "required_decrease": 1e-4 * scale * float(grad @ step),
                "max_gradient": float(max(abs(new_grad))),
            }
        )
        if new_loss <= loss - 1e-4 * scale * float(grad @ step):
            beta = candidate
            break
    else:
        break
write_json(
    root / "OPTIMIZER_DIAGNOSTIC.json",
    {
        "training_only_same_objective": True,
        "no_account_or_hyperparameter_experiment": True,
        "failed_operation_trials_retained": 24,
        "trace": trace,
    },
)
print(json.dumps({"steps": len(trace), "last": trace[-1]}, allow_nan=False))
