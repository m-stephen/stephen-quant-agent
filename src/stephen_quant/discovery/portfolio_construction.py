"""Finite no-fit construction diagnostic, not a new Alpha or launch authority.

The completed response experiment must remain immutable. These pure functions
do not read files, reserve Trials, construct accounts, or authorize empirical use.
A future runner must bind consumed evidence and reserve all four attempts first.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping

from .flow_response_predictor import INPUTS

VERSION = "11.22-construction-diagnostic-1"
PRIOR_DEBT = 3729
BUDGET = 4
POLICIES = ("global_lowvol", "global_hash")
PARENT_PLAN = "85005460b6e3d6128cf7e3a1ea9ebfb09fc6f59b78ae8ac458d71a22f3e03c9f"
PARENT_RESULT = "42967cab1f0463974244a3a3393678be558a33924377f3369825fb43e9b0432c"
PARENT_AUDIT = "0846c919950f1aae395b692897349c21274d12d7cf63b8b270ff82b716c7467f"
PARENT_ASSESSMENT = "f948d68cf807f2870f791e6db6917e527e762af95f9eacd00ff8eb6be957e27b"


def contract():
    """A fixed diagnostic proposal; debt changes only upon actual reservation."""
    return {
        "version": VERSION,
        "role": "construction_diagnostic_only",
        "primary_alpha_candidates": [],
        "prior_trial_lower_bound": PRIOR_DEBT,
        "budget": BUDGET,
        "projected_after_reservation": PRIOR_DEBT + BUDGET,
        "new_fits": 0,
        "parent_plan_sha256": PARENT_PLAN,
        "parent_result_sha256": PARENT_RESULT,
        "parent_audit_sha256": PARENT_AUDIT,
        "parent_assessment_sha256": PARENT_ASSESSMENT,
        "accounts": [
            {"key": f"{p}-{c}", "policy": p, "roundtrip_bps": c}
            for p in POLICIES
            for c in (82, 164)
        ],
        "sources": "same frozen daily/fund_flow2022-2024 and audited inherited history only",
        "source_support": "identical same-date eight-finite-feature response common support",
        "execution_window": ["2023-01-03", "2024-12-31"],
        "capital_cny": 3_000_000,
        "horizon_sessions": 20,
        "phases": [0, 5, 10, 15],
        "construction": "global40/top60 retention;2.5% per sleeve name;vacancies cash",
        "hash_identity": "same SHA256 v11.21:184:name descending;not a new lucky seed",
        "execution": "unchanged target_changes,capacity,stale writeoff/recovery,costs and B3 bars",
        "comparators": ["lowvol-82", "lowvol-164", "hash-82", "hash-164"],
        "comparator_use": "completed parent accounts read-only;never replay or relabel as new",
        "report": "all4 accounts/bothyears/bothcosts,full audit,style/membership/execution diagnostics",
        "decision": "diagnostic only;do not choose a new Alpha or optimal buffer from this batch",
        "interpretation": "construction changes risk allocation and retention jointly;not pure causal attribution",
        "statistics": {"DSR": None, "PBO": None, "placebo": None, "status": "NOT_RUN_DIAGNOSTIC"},
        "court": "unchanged DSR>=.95,PBO<=.05,placebo<=.05,path/capacity/independent evidence",
        "automatic_retry": False,
        "validated_alpha": False,
    }


def select_global(rows, policy, previous=()):
    """Select only from an already time/eligibility-audited current cross-section.

    A caller cannot use this function's validation as proof that raw fields were
    actually available. Only the source-to-target audit establishes that boundary.
    Existing holding identities are not allowed to expand today's support.
    """
    if policy not in POLICIES:
        raise ValueError("fixed no-fit global diagnostic policy required")
    if len(previous) != len(set(previous)) or any(not isinstance(n, str) for n in previous):
        raise ValueError("unique previous holding identities required")
    if not isinstance(rows, Mapping):
        raise TypeError("explicit current common-support mapping required")
    for name, row in rows.items():
        if (
            not isinstance(name, str)
            or not name
            or set(row) != {"cell", "ranks", "vol"}
            or type(row["cell"]) is not int
            or row["cell"] not in range(20)
            or type(row["vol"]) not in (int, float)
            or not math.isfinite(row["vol"])
            or row["vol"] < 0
            or set(row["ranks"]) != set(INPUTS)
            or any(
                type(v) not in (int, float) or not math.isfinite(v) or not -1 <= v <= 1
                for v in row["ranks"].values()
            )
        ):
            raise ValueError("complete finite current common support required; no silent drops")
    if policy == "global_lowvol":
        order = sorted(rows, key=lambda n: (rows[n]["vol"], n))
    else:
        order = sorted(
            rows,
            key=lambda n: (-int(hashlib.sha256(f"v11.21:184:{n}".encode()).hexdigest(), 16), n),
        )
    old = set(previous)
    chosen = [n for n in order[:60] if n in old][:40]
    retained = set(chosen)
    chosen += [n for n in order if n not in retained][: 40 - len(chosen)]
    return tuple(sorted(chosen))
