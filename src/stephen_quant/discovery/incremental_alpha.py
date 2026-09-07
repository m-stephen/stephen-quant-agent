"""Issue182: cost-aware incremental hypotheses, never a formal Alpha certificate."""

from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass
from statistics import mean

from stephen_quant.baseline.stateful import (
    StatefulExecutionConfig,
    TargetAllocation,
    run_stateful_execution,
)
from stephen_quant.discovery.reliable_research import compound, holdings, sharpe
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.evaluation import average_ranks

VERSION = "11.7.0"
SIGNALS = (
    "ret_20",
    "liquidity",
    "net_inflow_ratio",
    "concentration",
    "late_30_return",
    "realized_volatility",
    "amihud_intraday",
    "auction_return",
)
CRITERIA = {
    "both_years_positive": True,
    "pooled_sharpe_min": 0.7,
    "annual_drawdown_floor": -0.25,
    "compound_increment_vs_lowvol_min": 0.03,
    "annual_increment_vs_lowvol_floor": -0.05,
    "compound_increment_vs_hash_min_exclusive": 0.0,
    "cost_multiplier": 2,
    "status": "CONTAMINATED_HISTORICAL_LEAD_NOT_VALIDATED_ALPHA",
}


@dataclass(frozen=True)
class IncrementalHypothesis:
    field: str
    direction: int
    method: str
    horizon: int

    def __post_init__(self):
        if self.field not in SIGNALS or self.direction not in (-1, 1):
            raise ValueError("unsupported signal/direction")
        if self.method not in ("blend", "conditional") or self.horizon not in (20, 60):
            raise ValueError("unsupported mechanism/holding horizon")

    @property
    def identity(self):
        return sha256_json({"version": VERSION, **asdict(self), "policy": policy()})

    @property
    def name(self):
        return f"{self.method}_{self.field}_{self.direction:+d}_h{self.horizon}"

    @property
    def mechanism(self):
        return {
            "hypothesis": f"{self.field} direction {self.direction:+d} adds information within a low-risk allocation",
            "falsifier": "net incremental wealth disappears after matched low-vol control and doubled costs",
            "formula": "0.7*(-rank(vol20))+0.3*direction*rank(signal)"
            if self.method == "blend"
            else "direction*rank(signal) within bottom30% volatility",
            "source": "bounded deterministic mechanism grammar; no external LLM call",
        }


def policy():
    return {
        "capital_cny": 3_000_000,
        "top_n": 40,
        "rank_buffer": 10,
        "entry": "previous_close_signal_next_open",
        "universe": "existing_asof_panel_ADV_ge10m_nonST_20session_history",
        "coverage": "finite volatility20 AND candidate field, same for both controls",
        "fees_roundtrip_bps": [0, 41, 82],
        "shares": "adjusted_fractional_NOT_brokerage_ready",
        "buffer": "previous_desired_targets_not_actual_fills",
    }


def batches():
    # All formulas/directions frozen before ANY market labels are loaded.
    return tuple(
        tuple(
            IncrementalHypothesis(field, direction, method, horizon)
            for field in SIGNALS
            for direction in (-1, 1)
        )
        for method, horizon in (("blend", 20), ("conditional", 60))
    )


def matched_ranks(features, field):
    names = sorted(
        n
        for n, f in features.items()
        if all(k in f and math.isfinite(f[k]) for k in (field, "volatility_20"))
    )
    denominator = len(names) + 1
    return {
        key: dict(
            zip(
                names,
                (r / denominator for r in average_ranks([features[n][key] for n in names])),
                strict=True,
            )
        )
        for key in (field, "volatility_20")
    }


def scores_from_ranks(ranks, hypothesis, kind="candidate"):
    if kind not in ("candidate", "lowvol", "hash"):
        raise ValueError("unknown control")
    vol = ranks["volatility_20"]
    if kind == "hash":
        return {
            n: int(hashlib.sha256(("issue182-control:" + n).encode()).hexdigest(), 16) for n in vol
        }
    if kind == "lowvol":
        return {n: -v for n, v in vol.items()}
    signal = ranks[hypothesis.field]
    if hypothesis.method == "blend":
        return {n: -0.7 * v + 0.3 * hypothesis.direction * signal[n] for n, v in vol.items()}
    return {n: hypothesis.direction * signal[n] for n, v in vol.items() if v <= 0.3}


def incremental_targets(days, hypothesis, kind="candidate", rank_cache=None):
    previous = ()
    targets, coverage = [], []
    cache = {} if rank_cache is None else rank_cache
    for i, day in enumerate(days):
        signal = days[i - 1] if i else None
        rebalance = i > 0 and (i - 1) % hypothesis.horizon == 0
        weights = {}
        if rebalance:
            key = (signal.date, hypothesis.field)
            if key not in cache:
                cache[key] = matched_ranks(signal.features, hypothesis.field)
            ranks = cache[key]
            scores = scores_from_ranks(ranks, hypothesis, kind)
            previous = holdings(scores, previous)
            weights = {n: 1 / 40 for n in previous}
            coverage.append(
                {
                    "date": signal.date,
                    "matched": len(ranks["volatility_20"]),
                    "eligible": len(scores),
                    "selected": len(previous),
                }
            )
        targets.append(
            TargetAllocation(
                day.date,
                f"{signal.date}T23:59:59+08:00" if signal else f"{day.date}T08:00:00+08:00",
                weights,
                rebalance,
            )
        )
    return tuple(targets), coverage


def execute(days, targets, cost):
    if cost not in (0, 1, 2):
        raise ValueError("unregistered cost variant")
    return run_stateful_execution(
        tuple(d.bars for d in days),
        targets,
        StatefulExecutionConfig(
            maximum_position_weight=0.025,
            commission_bps=3 * cost,
            sell_tax_bps=5 * cost,
            slippage_bps=15 * cost,
        ),
        initial_nav=3_000_000,
    )


def audit_account(report):
    residual = 0.0
    for p in report.periods:
        error = abs(p.end_nav - p.cash - sum(m.market_value for m in p.marks))
        residual = max(residual, error)
        if error > 1e-5 or p.cash < -1e-7 or not math.isfinite(p.end_nav):
            raise ValueError("account balance failed")
        if not math.isclose(sum(o.total_cost for o in p.orders), p.total_cost, abs_tol=1e-6):
            raise ValueError("order costs do not reconcile")
    if not math.isclose(
        compound([p.net_return for p in report.periods]),
        report.metrics.net_total_return,
        abs_tol=1e-10,
    ):
        raise ValueError("compounded returns do not reconcile")
    return {"pass": True, "maximum_balance_residual_cny": residual}


def suspected_lead(years):
    """A frozen descriptive stop rule, deliberately NOT statistical certification."""
    if set(years) != {"2023", "2024"}:
        raise ValueError("requires exactly the two declared development years")
    rows = [years[y]["2"] for y in ("2023", "2024")]
    annual = [r["absolute_return"] for r in rows]
    base = [r["benchmark_return"] for r in rows]
    hashed = [r["hash_control_return"] for r in rows]
    daily = [v for r in rows for v in r["daily_returns"]]
    increment = compound(annual) - compound(base)
    checks = {
        "positive_both_years": all(v > 0 for v in annual),
        "sharpe": sharpe(daily) >= CRITERIA["pooled_sharpe_min"],
        "drawdown": all(r["max_drawdown"] >= CRITERIA["annual_drawdown_floor"] for r in rows),
        "lowvol_increment": increment >= CRITERIA["compound_increment_vs_lowvol_min"],
        "annual_increment": all(
            a - b >= CRITERIA["annual_increment_vs_lowvol_floor"]
            for a, b in zip(annual, base, strict=True)
        ),
        "hash_increment": compound(annual) > compound(hashed),
        "accounts": all(r["audit"]["pass"] for r in rows),
    }
    return {
        "suspected_lead": all(checks.values()),
        "validated_alpha": False,
        "checks": checks,
        "pooled_sharpe": sharpe(daily),
        "compound_return_reset_accounts": compound(annual),
        "compound_increment_vs_lowvol": increment,
        "compound_increment_vs_hash": compound(annual) - compound(hashed),
        "interpretation": "synthetic chain of annual-reset accounts, not a continuous live account",
    }


def holding_overlap(left, right):
    values = []
    for a, b in zip(left.periods, right.periods, strict=True):
        x = {m.instrument for m in a.marks if m.market_value > 0}
        y = {m.instrument for m in b.marks if m.market_value > 0}
        if x | y:
            values.append(len(x & y) / len(x | y))
    return mean(values) if values else 0.0
