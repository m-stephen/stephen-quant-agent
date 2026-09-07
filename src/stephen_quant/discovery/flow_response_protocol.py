"""Finite V11.21 response study: two hypotheses, twenty-two accounts, one provider.

Constructing this contract does not reserve an empirical Trial or authorize a read.
The runner must freeze its exact source/card/code/ledger/preregistration evidence.
"""

from __future__ import annotations

import json
import math

from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest
from stephen_quant.mechanism_inventory import freeze_lineage_packet

from .flow_response_history import VERSION as HISTORY_VERSION
from .flow_response_predictor import INPUTS, POLICIES, RISK, stages
from .flow_response_series import DAILY_SUPPORT, response_stages, validate_calendar
from .pairwise_ranking import screen
from .search_power_dsl import sha256_json

VERSION = "11.21-response-epoch-2"
BASE_DEBT = 3660
FAILED_ATTEMPTS = 23  # Verified consumed epoch-1 evidence; not discarded on failure.
DEBT = BASE_DEBT + FAILED_ATTEMPTS
COSTS = (82, 164)
PRIMARY = ("response", "response_interaction")
CONTROLS = tuple(p for p in POLICIES if p not in PRIMARY) + (
    "hash",
    "lowvol",
    "original_lowvol",
    "original_stable",
)
BUDGET = 23


def plans():
    return [
        {
            "key": "response-provider",
            "role": "feature_provider",
            "response_policy": None,
            "roundtrip_bps": None,
            "execution_mode": None,
        }
    ] + [
        {
            "key": f"{p}-{c}",
            "role": "primary" if p in PRIMARY else "control",
            "response_policy": p,
            "roundtrip_bps": c,
            "execution_mode": "full_target" if p.startswith("original_") else "target_changes",
        }
        for p in POLICIES + ("hash", "lowvol", "original_lowvol", "original_stable")
        for c in COSTS
    ]


def candidate_packet(*, policy_tombstones=(), family_tombstones=(), legacy_tombstone_aliases=None):
    # This symbolic call represents a mature-label ridge fit, NOT a unit-weight sum.
    # Direction+1 means selecting the higher predicted relative return, not choosing
    # a post-hoc sign on any individual input. Coefficients are prefix-learned.
    common = [f"rank({k})" for k in RISK + ("flow_surprise", "price_response_residual")]
    entries = [
        {
            "name": policy,
            "family": "flow_response_residual",
            "expression": "ridge_rank_score(0.01,"
            + ",".join(
                common
                + (
                    ["rank(flow_surprise)*rank(price_response_residual)"]
                    if policy == "response_interaction"
                    else []
                )
            )
            + ")",
            "required_fields": INPUTS,
            "sources": ("daily", "fund_flow"),
            "lookback": 60,
            "forecast_sessions": 20,
            "direction": 1,
            "execution_timing": "T+1_OPEN",
            "legacy_ids": (),
            "narrative": "Inherited liquidity-impact family; estimator novelty not established",
        }
        for policy in PRIMARY
    ]
    entries = [
        {"name": e["name"], "lineage": {k: v for k, v in e.items() if k != "name"}} for e in entries
    ]
    return freeze_lineage_packet(
        entries,
        budget=2,
        policy_tombstones=policy_tombstones,
        family_tombstones=family_tombstones,
        legacy_tombstone_aliases=legacy_tombstone_aliases,
    )


def contract():
    return {
        "version": VERSION,
        "budget": BUDGET,
        "prior_trial_debt": DEBT,
        "after_full_reservation_debt": DEBT + BUDGET,
        "primary": PRIMARY,
        "controls_per_cost": CONTROLS,
        "costs_bps": COSTS,
        "accounts": 22,
        "shared_feature_providers": 1,
        "actual_supervised_models": 14,
        "supervised_native_bindings": 28,
        "provider_models": "one native bundle per signal index61..len(calendar)-2; per-asset fits in bundle",
        "fit_sharing": "one annual model per policy, exact same bytes bound to both cost Trials; not independent fits",
        "fit": "2023 on2022,2024 on2022-23;20session next-open labels,stride5,5session prefix embargo,ridge.01,>=30mature dates",
        "source_scope": "frozen daily/fund_flow,2022-2024 only;no2021 numeric warmup or2025/26",
        "source_support_policy": DAILY_SUPPORT,
        "source_support_exclusions": "same-date key-only exclusions with exact identity hashes;no numeric imputation,calendar compression or future-presence filtering",
        "features": INPUTS,
        "risk": "21consecutive global closes;20sample log-return volatility;20return;up-to60mean CNY ADV>=10m;nonempty non-ST name",
        "capacity": "5% immediately preceding global-session visible ADV;missing adjacent ADV=>0",
        "units": "daily amount thousands->CNY;flow CNY;source-adjusted open/close;numeric projection DOUBLE",
        "availability": "aware timestamps,own-day EOD exclusion before math,no retroactive backfill;not live first-seen",
        "support": "same8finite-feature/risk-eligible intersection for7learned+hash+lowvol;no future survival filtering",
        "targets": "5vol by4ADV cells,within-cell ranks,2stocks/cell,top3retention,2.5% each,4phases0/5/10/15;vacancies cash",
        "anchors": "original lowvol/stable target bytes unmodified;full_target;replayed on disclosed conservative B3 bars,not same old account claim",
        "account": "CNY3m,82/164bps,20session stale writeoff,source-adjusted fractional shares;not broker-certified",
        "coverage_min": 0.95,
        "screen": "bothyearspositive,SR>=.7,MDD>=-.25,totalincrement>=.03 and eachannual>=-.05 vsEVERY9control atbothcosts,coverage>=.95,completeaudit",
        "multiplicity": "3660 verified parent +23 consumed failed epoch =3683 prior;new23 reservations=>3706;no debt reset",
        "gross_diagnostics": "no zero-cost account or new calibration in this budget",
        "shuffle": "fixed training date/cell label rotation;control only,not placebo p-value",
        "statistics": {
            "DSR": None,
            "PBO": None,
            "placebo": None,
            "status": "NOT_RUN_EXPLORATORY_REUSED_HISTORY",
        },
        "court": "unchangedDSR>=.95,PBO<=.05,placebo<=.05,path/capacity/independent-evidence requirements",
        "validated_alpha": False,
    }


def reserve_trials(output, spec):
    """New operation database only; failures cannot be hidden by deterministic replay."""
    from stephen_quant.integrity.registry import ExperimentRegistry

    calendar = spec["calendar"]
    validate_calendar(calendar)
    packet = candidate_packet(**spec.get("tombstones", {}))
    if (
        sha256_json(spec["contract"]) != sha256_json(contract())
        or spec["plans"] != plans()
        or sha256_json(spec["packet"]) != sha256_json(packet)
        or len(packet["accepted"]) != 2
        or packet["rejected"]
        or {d[:4] for d in calendar} != {"2022", "2023", "2024"}
        or not isinstance(spec.get("failed_epoch_evidence_sha256"), str)
        or len(spec["failed_epoch_evidence_sha256"]) != 64
        or any(c not in "0123456789abcdef" for c in spec["failed_epoch_evidence_sha256"])
    ):
        raise ValueError("exact finite response protocol and all3calendar years required")
    db_path = output / "registry.sqlite3"
    if db_path.exists():
        raise FileExistsError("response operation database exists; never re-reserve")
    registry = ExperimentRegistry(db_path)
    sid = registry.register_snapshot(
        build_composite_snapshot_manifest(
            {
                "inputs": spec["manifest_sha256"],
                "anchor_card": spec["anchor_card_sha256"],
                "failed_epoch_evidence": spec["failed_epoch_evidence_sha256"],
            }
        )
    )
    eid = registry.create_experiment_deterministic(
        ExperimentSpec(
            "flow_response",
            "frozen within-stock response estimates versus own-return/risk controls",
            sid,
            spec["runtime_code_sha256"],
            json.dumps(spec, sort_keys=True),
        ),
        sha256_json(spec),
    )
    params = {
        "response_history_version": HISTORY_VERSION,
        "response_manifest_sha256": spec["manifest_sha256"],
        "response_calendar_sha256": sha256_json(calendar),
        "response_support_policy": DAILY_SUPPORT,
        "failed_epoch_evidence_sha256": spec["failed_epoch_evidence_sha256"],
    }
    tids = {}
    for p in plans():
        fit_stages = (
            response_stages(calendar)
            if p["role"] == "feature_provider"
            else (stages() if p["response_policy"] in POLICIES else ())
        )
        tid, _ = registry.create_trial_deterministic(
            TrialSpec(
                eid,
                p["key"],
                packet["packet_sha256"],
                json.dumps(params | p, sort_keys=True),
                184,
                "2022-01-01",
                "2023-12-31",
                "2023-01-01",
                "2024-12-31",
                "unused",
                "unused",
                fit_stages=fit_stages,
            ),
            sha256_json(p),
        )
        tids[p["key"]] = tid
        providers = (
            ()
            if p["role"] == "feature_provider" or p["response_policy"].startswith("original_")
            else (tids["response-provider"],)
        )
        registry.declare_feature_sources(tid, providers)
    if registry.global_trial_count() != BUDGET:
        raise ValueError("complete native23Trial reservation required")
    return registry, tids


def check_complete_reservations(registry, tids):
    if set(tids) != {p["key"] for p in plans()} or len(set(tids.values())) != BUDGET:
        raise ValueError("all23 unique native Trial identities required")
    with registry.connect() as conn:
        for p in plans():
            row = conn.execute(
                "SELECT hyperparams,result_json FROM trials WHERE trial_id=?", (tids[p["key"]],)
            ).fetchone()
            if (
                row is None
                or row[1] is not None
                or any(json.loads(row[0]).get(k) != v for k, v in p.items())
            ):
                raise ValueError("incomplete or changed pre-read reservation")
            if conn.execute(
                "SELECT 1 FROM trial_model_fits WHERE trial_id=?", (tids[p["key"]],)
            ).fetchone():
                raise ValueError("numerical fit preceded complete operation preflight")
    return {
        "reserved": BUDGET,
        "prior_debt": DEBT,
        "debt": DEBT + BUDGET,
        "native_trial_ids_sha256": sha256_json(tids),
    }


def screen_records(records, diagnostics, *, independent_audit_pass):
    expected = {p["key"] for p in plans() if p["role"] != "feature_provider"}
    if set(records) != expected:
        raise ValueError("all22 candidate/control accounts required; no selective report")
    for row in records.values():
        if (
            set(row["years"]) != {"2023", "2024"}
            or type(row["audit"]["pass"]) is not bool
            or not all(
                math.isfinite(v)
                for v in (
                    *row["years"].values(),
                    row["pooled_sharpe"],
                    row["metrics"]["net_total_return"],
                    row["metrics"]["max_drawdown"],
                )
            )
        ):
            raise ValueError("finite complete account evidence required")
    checks = {}
    for primary in PRIMARY:
        checks[primary] = {}
        for cost in COSTS:
            row = records[f"{primary}-{cost}"]
            controls = [records[f"{control}-{cost}"] for control in CONTROLS]
            checks[primary][str(cost)] = screen(row, controls, diagnostics[primary]) | {
                "independent_audit": independent_audit_pass is True,
            }
    return {
        "checks": checks,
        "screen_survived": {
            p: all(all(x.values()) for x in costs.values()) for p, costs in checks.items()
        },
        "validated_alpha": False,
    }
