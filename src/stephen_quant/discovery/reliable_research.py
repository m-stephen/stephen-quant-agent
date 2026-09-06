"""Shared, bounded research semantics. No data source or experiment state is hidden here."""

from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass
from datetime import timedelta
from statistics import mean, median, stdev

from stephen_quant.baseline.stateful import (
    StatefulBar,
    StatefulExecutionConfig,
    TargetAllocation,
    run_stateful_execution,
)
from stephen_quant.cross_validation.engine import generate_cpcv_manifest
from stephen_quant.cross_validation.models import SampleInterval, SplitLineage
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.evaluation import average_ranks
from stephen_quant.falsification import deflated_sharpe_ratio

RELIABLE_VERSION = "11.6.0"
FIELDS = (
    "ret_20",
    "volatility_20",
    "liquidity",
    "net_inflow_ratio",
    "concentration",
    "late_30_return",
    "realized_volatility",
    "amihud_intraday",
    "auction_return",
)


@dataclass(frozen=True)
class ResearchCandidate:
    name: str
    fields: tuple[str, ...]
    operator: str = "rank"
    direction: int = 1
    horizon: int = 20
    gate_field: str | None = None
    gate_side: str | None = None
    parent: str = "predeclared_baseline"

    @property
    def identity(self) -> str:
        return sha256_json(
            {
                "version": RELIABLE_VERSION,
                **asdict(self),
                "universe": "prior_60d_ADV_ge_10m_history_ge_20",
                "execution": "signal_close_to_next_open",
                "minute_alignment": "latest_available_by_signal_close_max_7_calendar_days",
                "portfolio": "Top40_buffer10_cash_unfilled",
                "cost_pair_round_trip_bps": [41, 82],
            }
        )


@dataclass(frozen=True)
class ResearchDay:
    date: str
    features: dict[str, dict[str, float]]
    bars: tuple[StatefulBar, ...]


def candidate_pack() -> tuple[ResearchCandidate, ...]:
    items = [
        ResearchCandidate("reversal20", ("ret_20",), direction=-1),
        ResearchCandidate("momentum20", ("ret_20",)),
        ResearchCandidate("low_volatility", ("volatility_20",), direction=-1),
        ResearchCandidate("positive_flow", ("net_inflow_ratio",), horizon=10),
        ResearchCandidate("negative_flow", ("net_inflow_ratio",), direction=-1, horizon=10),
        ResearchCandidate("wide_chip", ("concentration",)),
        ResearchCandidate("narrow_chip", ("concentration",), direction=-1),
        ResearchCandidate(
            "legacy_majority",
            ("amihud_intraday", "concentration", "realized_volatility"),
            "majority",
        ),
        ResearchCandidate(
            "reversal_chip_divergence",
            ("ret_20", "concentration"),
            "divergence",
            -1,
            parent="reversal20",
        ),
        ResearchCandidate(
            "reversal_liquidity_joint", ("ret_20", "liquidity"), "maximum", -1, parent="reversal20"
        ),
    ]
    for field in ("net_inflow_ratio", "concentration", "volatility_20", "liquidity"):
        for side in ("high", "low"):
            items.append(
                ResearchCandidate(
                    f"reversal_given_{field}_{side}",
                    ("ret_20",),
                    direction=-1,
                    gate_field=field,
                    gate_side=side,
                    parent="reversal20",
                )
            )
    for field in ("late_30_return", "auction_return"):
        for direction in (-1, 1):
            items.append(
                ResearchCandidate(
                    f"{field}_{direction:+d}", (field,), direction=direction, horizon=5
                )
            )
    items += [
        ResearchCandidate(
            "linear_shrinkage",
            ("ret_20", "volatility_20", "net_inflow_ratio"),
            "linear",
            horizon=10,
            parent="fixed_training_2022",
        ),
        ResearchCandidate(
            "shallow_stump", ("ret_20",), "stump", horizon=10, parent="fixed_training_2022"
        ),
    ]
    assert len(items) == 24 and len({x.identity for x in items}) == len(items)
    return tuple(items)


def validate_proposal(proposal: dict) -> ResearchCandidate:
    """Structured LLM proposals only. No eval, implicit execution, or future fields."""
    if not proposal.get("mechanism") or not proposal.get("falsifier"):
        raise ValueError("proposal requires a mechanism and falsifier")
    value = dict(proposal["candidate"])
    value["fields"] = tuple(value["fields"])
    candidate = ResearchCandidate(**value)
    if candidate.operator not in {"rank", "divergence", "maximum", "majority"}:
        raise ValueError("unsupported proposal operator")
    arity = {"rank": 1, "divergence": 2, "maximum": 2, "majority": 3}
    if len(candidate.fields) != arity[candidate.operator]:
        raise ValueError("operator arity mismatch")
    dependencies = candidate.fields + ((candidate.gate_field,) if candidate.gate_field else ())
    if not set(dependencies) <= set(FIELDS) or candidate.direction not in (-1, 1):
        raise ValueError("unsupported field or direction")
    if candidate.horizon not in (5, 10, 20):
        raise ValueError("unsupported holding period")
    if (candidate.gate_field is None) != (candidate.gate_side is None):
        raise ValueError("gate field and side must be paired")
    if candidate.gate_side not in (None, "high", "low"):
        raise ValueError("unsupported gate side")
    return candidate


def screen_proposals(proposals: list[dict], *, maximum=30) -> list[dict]:
    """Label-free proposal/rejection ledger; accepted proposals are not automatically run."""
    if not 1 <= maximum <= 30:
        raise ValueError("proposal budget must be between 1 and 30")
    seen = set()
    ledger = []
    for index, proposal in enumerate(proposals):
        record = {"index": index, "proposal": proposal, "uses_labels": False}
        try:
            candidate = validate_proposal(proposal)
            if candidate.identity in seen:
                raise ValueError("duplicate proposal")
            if len(seen) >= maximum:
                raise ValueError("frozen proposal budget exhausted")
            seen.add(candidate.identity)
            record.update(
                status="ACCEPTED_NOT_EXECUTED", identity=candidate.identity, parent=candidate.parent
            )
        except (ValueError, TypeError, KeyError) as exc:
            record.update(status="REJECTED", reason=str(exc))
        ledger.append(record)
    return ledger


def candidate_scores(
    features: dict[str, dict[str, float]], candidate: ResearchCandidate, model: dict | None = None
) -> tuple[dict[str, float], int]:
    required = candidate.fields + ((candidate.gate_field,) if candidate.gate_field else ())
    names = sorted(
        name
        for name, cells in features.items()
        if all(key in cells and math.isfinite(cells[key]) for key in required)
    )
    ranks = {
        field: dict(
            zip(
                names,
                (x / (len(names) + 1) for x in average_ranks([features[n][field] for n in names])),
                strict=True,
            )
        )
        for field in set(required)
    }
    scores = {}
    for name in names:
        if candidate.gate_field:
            gate = ranks[candidate.gate_field][name]
            if candidate.gate_side == "high" and gate < 0.7:
                continue
            if candidate.gate_side == "low" and gate > 0.3:
                continue
        cells = [2 * ranks[f][name] - 1 for f in candidate.fields]
        if candidate.operator == "linear":
            if model is None:
                raise ValueError("linear model must be fit on declared training prefix")
            score = sum(a * b for a, b in zip(cells, model["weights"], strict=True))
        elif candidate.operator == "stump":
            if model is None:
                raise ValueError("stump must be fit on declared training prefix")
            score = model["left"] if cells[0] <= model["threshold"] else model["right"]
        elif candidate.operator == "rank":
            score = cells[0]
        elif candidate.operator == "divergence":
            score = cells[0] - cells[1]
        elif candidate.operator == "maximum":
            score = max(cells)
        elif candidate.operator == "majority":
            score = sum(1 if x >= 0 else -1 for x in cells) / len(cells)
        else:
            raise ValueError("unsupported candidate operator")
        scores[name] = score * candidate.direction
    return scores, len(names)


def holdings(scores: dict[str, float], previous: tuple[str, ...]) -> tuple[str, ...]:
    ranked = sorted(scores, key=lambda n: (-scores[n], hashlib.sha256(n.encode()).hexdigest()))
    retained = [n for n in previous if n in set(ranked[:50])]
    return tuple(retained + [n for n in ranked if n not in retained])[:40]


def build_targets(
    days: tuple[ResearchDay, ...],
    candidate: ResearchCandidate,
    model: dict | None = None,
    *,
    benchmark: bool = False,
):
    previous: tuple[str, ...] = ()
    targets, coverages = [], []
    for offset, day in enumerate(days):
        signal = days[offset - 1] if offset else None
        rebalance = offset > 0 and (offset - 1) % candidate.horizon == 0
        weights = {}
        if rebalance:
            scores, complete = candidate_scores(signal.features, candidate, model)
            strata = {"10m_50m": 0, "50m_200m": 0, "200m_plus": 0}
            for name in scores:
                adv = signal.features[name].get("liquidity")
                if adv is not None:
                    strata[
                        "10m_50m" if adv < 50e6 else "50m_200m" if adv < 200e6 else "200m_plus"
                    ] += 1
            coverages.append(
                {
                    "date": signal.date,
                    "base": len(signal.features),
                    "complete": complete,
                    "active": len(scores),
                    "active_liquidity_strata": strata,
                }
            )
            if benchmark:
                # Unconditional matched-availability control: same feature dependencies,
                # calendar and execution costs, with no outcome-conditioned universe.
                control = ResearchCandidate(
                    "control", candidate.fields, "rank", horizon=candidate.horizon
                )
                if candidate.gate_field:
                    control = ResearchCandidate(
                        "control",
                        candidate.fields + (candidate.gate_field,),
                        "maximum",
                        horizon=candidate.horizon,
                    )
                names, _ = candidate_scores(signal.features, control)
                # Equal-weight control invests only the coverage-supported fraction.
                weight = min(1.0, len(names) / 40) / len(names) if names else 0.0
                weights = {n: weight for n in names}
            else:
                previous = holdings(scores, previous)
                weights = {n: 1 / 40 for n in previous}
        targets.append(
            TargetAllocation(
                day.date,
                f"{signal.date if signal else day.date}T23:59:59+08:00"
                if signal
                else f"{day.date}T08:00:00+08:00",
                weights,
                rebalance,
            )
        )
    return tuple(targets), coverages


def sharpe(values):
    return (
        mean(values) / stdev(values) * math.sqrt(252) if len(values) > 1 and stdev(values) else 0.0
    )


def compound(values):
    return math.prod(1 + v for v in values) - 1


def moments(values):
    center = mean(values)
    v = mean((x - center) ** 2 for x in values)
    return (
        (
            mean((x - center) ** 3 for x in values) / v**1.5,
            mean((x - center) ** 4 for x in values) / v**2 - 3,
        )
        if v
        else (0.0, 0.0)
    )


def effective_n(values, lag=20):
    center = mean(values)
    denominator = sum((x - center) ** 2 for x in values)
    if not denominator:
        return 2
    inflation = 1 + 2 * sum(
        (1 - k / (lag + 1))
        * sum((values[i] - center) * (values[i - k] - center) for i in range(k, len(values)))
        / denominator
        for k in range(1, min(lag + 1, len(values)))
    )
    return max(2, min(len(values), int(len(values) / max(1.0, inflation))))


def run_candidate(
    days: tuple[ResearchDay, ...],
    candidate: ResearchCandidate,
    model: dict | None = None,
    multiplier: int = 1,
    *,
    benchmark=False,
):
    targets, coverage = build_targets(days, candidate, model, benchmark=benchmark)
    # 3 commission +15 slippage each side +5 sell tax =41bps round trip.
    report = run_stateful_execution(
        tuple(day.bars for day in days),
        targets,
        StatefulExecutionConfig(
            maximum_position_weight=0.025,
            commission_bps=3 * multiplier,
            sell_tax_bps=5 * multiplier,
            slippage_bps=15 * multiplier,
        ),
        initial_nav=3_000_000,
        retain_details=not benchmark,
    )
    return report, coverage, sha256_json([asdict(x) for x in targets])


def metric_bundle(report, benchmark):
    daily = [x.net_return for x in report.periods]
    base = [x.net_return for x in benchmark.periods]
    if any(x is None for x in daily + base):
        raise ValueError("undefined daily return")
    excess = [a - b for a, b in zip(daily, base, strict=True)]
    return {
        "absolute_return": report.metrics.net_total_return,
        "profit_cny": report.metrics.final_nav - report.metrics.initial_nav,
        "final_nav": report.metrics.final_nav,
        "benchmark_return": benchmark.metrics.net_total_return,
        "excess_percentage_points": report.metrics.net_total_return
        - benchmark.metrics.net_total_return,
        "relative_wealth_return": report.metrics.final_nav / benchmark.metrics.final_nav - 1,
        "active_sharpe": sharpe(excess),
        "daily_active": excess,
        "daily_returns": daily,
        "daily_benchmark": base,
        "max_drawdown": report.metrics.max_drawdown,
        "cost_cny": report.metrics.total_cost,
        "blocked_notional_cny": report.metrics.blocked_notional,
        "writeoffs": report.metrics.writeoff_events,
        "stale_position_days": report.metrics.stale_position_days,
        "gross_traded_notional": sum(p.traded_notional_cny for p in report.periods),
    }


def selection_key(values, identity):
    """One simple, fixed economic selector reused inside CPCV and final freezing."""
    return (mean(values), -stdev(values) if len(values) > 1 else 0.0, identity)


def temporal_selection(
    dates: list[str], returns: dict[str, list[float]], raw_trials: int,
    *, holding_period_sessions: int = 20,
):
    if holding_period_sessions < 1:
        raise ValueError("holding period must be positive")
    if not returns or len(dates) < 126 or any(len(v) != len(dates) for v in returns.values()):
        raise ValueError("selection requires aligned daily series and at least126 dates")
    samples = [
        SampleInterval(
            str(i),
            "portfolio",
            f"{d}T08:00:00+08:00",
            f"{d}T09:30:00+08:00",
            f"{dates[min(i + holding_period_sessions, len(dates) - 1)]}T15:00:00+08:00",
        )
        for i, d in enumerate(dates)
    ]
    manifest = generate_cpcv_manifest(
        samples,
        SplitLineage("snapshot", "epoch", "selector", RELIABLE_VERSION),
        n_groups=6,
        n_test_groups=3,
        embargo=timedelta(days=5),
    )
    paths = []
    rankings = set()
    for fold in manifest.folds:
        train, test = [int(x) for x in fold.train_ids], [int(x) for x in fold.test_ids]
        order = sorted(returns, key=lambda c: selection_key([returns[c][i] for i in train], c))
        winner = order[-1]
        test_order = sorted(returns, key=lambda c: selection_key([returns[c][i] for i in test], c))
        rankings.add(tuple(test_order))
        paths.append(
            {
                "fold": fold.fold_id,
                "train_n": len(train),
                "test_n": len(test),
                "purged_n": len(fold.purged_ids),
                "embargoed_n": len(fold.embargoed_ids),
                "winner": winner,
                "test_mean": mean(returns[winner][i] for i in test),
                "below_median": test_order.index(winner) < len(test_order) / 2,
            }
        )
    winner = max(returns, key=lambda c: selection_key(returns[c], c))
    selected = returns[winner]
    skew, kurtosis = moments(selected)
    dsr = deflated_sharpe_ratio(
        observed_sharpe=sharpe(selected) / math.sqrt(252),
        trial_sharpes=[sharpe(v) / math.sqrt(252) for v in returns.values()],
        recorded_trial_count=raw_trials,
        observations=effective_n(selected, lag=holding_period_sessions),
        skewness=skew,
        excess_kurtosis=kurtosis,
    )
    return {
        "winner": winner,
        "pbo": mean(p["below_median"] for p in paths) if len(rankings) > 1 else None,
        "pbo_status": "DIAGNOSTIC" if len(rankings) > 1 else "NOT_IDENTIFIABLE",
        "dsr": dsr.probability,
        "dsr_status": "RAW_COUNT_SENSITIVITY_HISTORICAL_SHARPE_MATRIX_UNAVAILABLE",
        "dsr_trial_sharpe_estimates": len(returns),
        "dsr_raw_trial_count": raw_trials,
        "dsr_benchmark_daily_sharpe": dsr.benchmark_sharpe,
        "dsr_assumption": "current-family Sharpe dispersion extrapolated to all raw trials; not a calibrated full-history DSR",
        "effective_observations": effective_n(selected, lag=holding_period_sessions),
        "daily_observations": len(dates),
        "empirical_skewness": skew,
        "empirical_excess_kurtosis": kurtosis,
        "folds": paths,
        "split_manifest": manifest.to_dict(),
        "selector": "mean daily net active return, lower daily volatility, canonical ID",
    }


def fit_prefix_model(days: tuple[ResearchDay, ...], candidate: ResearchCandidate) -> dict:
    """Fit ONLY the declared training prefix. All forward labels end inside it."""
    if not days or days[-1].date > "2022-12-31":
        raise ValueError("model training prefix must end by2022-12-31")
    xs, ys = [], []
    for i in range(0, len(days) - candidate.horizon - 1, 5):
        features = days[i].features
        names = sorted(
            n
            for n, row in features.items()
            if all(f in row and math.isfinite(row[f]) for f in candidate.fields)
        )
        entry = {b.instrument: b.open_price for b in days[i + 1].bars}
        exit_prices = {b.instrument: b.open_price for b in days[i + candidate.horizon + 1].bars}
        ranks = [
            [2 * x / (len(names) + 1) - 1 for x in average_ranks([features[n][f] for n in names])]
            for f in candidate.fields
        ]
        for j, n in enumerate(names):
            if n in entry and n in exit_prices:
                xs.append([r[j] for r in ranks])
                ys.append(exit_prices[n] / entry[n] - 1)
    if len(ys) < 100:
        raise ValueError("insufficient training samples for model")
    if candidate.operator == "stump":
        threshold = median(x[0] for x in xs)
        return {
            "threshold": threshold,
            "left": mean(y for x, y in zip(xs, ys) if x[0] <= threshold),
            "right": mean(y for x, y in zip(xs, ys) if x[0] > threshold),
            "samples": len(ys),
            "fit_end": days[-1].date,
        }
    size = len(candidate.fields)
    matrix = [
        [mean(x[a] * x[b] for x in xs) + (1.0 if a == b else 0.0) for b in range(size)]
        + [mean(x[a] * y for x, y in zip(xs, ys))]
        for a in range(size)
    ]
    for a in range(size):
        scale = matrix[a][a]
        matrix[a] = [v / scale for v in matrix[a]]
        for b in range(size):
            if a != b:
                scale = matrix[b][a]
                matrix[b] = [v - scale * w for v, w in zip(matrix[b], matrix[a])]
    return {
        "weights": [matrix[a][-1] for a in range(size)],
        "ridge": 1.0,
        "samples": len(ys),
        "fit_end": days[-1].date,
    }
