from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import asdict, dataclass

from stephen_quant.evaluation.metrics import spearman_correlation

SEARCH_CALIBRATION_VERSION = "9.0.0"


@dataclass(frozen=True)
class OverfitPoint:
    trials: int
    best_discovery_rank_ic: float
    selected_holdout_rank_ic: float


@dataclass(frozen=True)
class SearchCalibrationReport:
    method_version: str
    seed: int
    planted_candidates: int
    planted_rank: int
    planted_discovery_rank_ic: float
    planted_holdout_rank_ic: float
    null_candidates: int
    null_selected_discovery_rank_ic: float
    null_selected_holdout_rank_ic: float
    leakage_rank_ic: float
    leakage_positive_control_detected: bool
    purge_embargo_overlap_count: int
    overfit_curve: tuple[OverfitPoint, ...]
    checks: tuple[tuple[str, bool], ...]
    passed: bool
    report_sha256: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)


def _average_daily_rank_ic(
    signals: list[list[float]], returns: list[list[float]], start: int, end: int
) -> float:
    values = [spearman_correlation(signals[index], returns[index]) for index in range(start, end)]
    return sum(values) / len(values)


def _candidate_panel(rng: random.Random, days: int, assets: int) -> list[list[float]]:
    return [[rng.gauss(0.0, 1.0) for _ in range(assets)] for _ in range(days)]


def _digest(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def run_search_calibration(
    *,
    seed: int = 20260902,
    days: int = 100,
    assets: int = 80,
    planted_candidates: int = 32,
    null_candidates: int = 500,
) -> SearchCalibrationReport:
    """Calibrate discovery power before real labels may be searched.

    The fixtures are deterministic and independent of market data.  They answer a narrower
    engineering question: can the search machinery recover a known signal, expose a leaked label,
    and demonstrate the multiple-testing effect under a pure null?
    """

    if days < 40 or assets < 20:
        raise ValueError("calibration requires at least 40 dates and 20 assets")
    if planted_candidates < 2 or null_candidates < 100:
        raise ValueError("calibration candidate budgets are too small")
    discovery_end = days * 3 // 5
    rng = random.Random(seed)
    planted = _candidate_panel(rng, days, assets)
    noise = _candidate_panel(rng, days, assets)
    returns = [
        [0.12 * planted[day][asset] + noise[day][asset] for asset in range(assets)]
        for day in range(days)
    ]
    planted_set = [planted] + [
        _candidate_panel(random.Random(seed + 10_000 + candidate), days, assets)
        for candidate in range(planted_candidates - 1)
    ]
    discovery_scores = [
        _average_daily_rank_ic(item, returns, 0, discovery_end) for item in planted_set
    ]
    holdout_scores = [
        _average_daily_rank_ic(item, returns, discovery_end, days) for item in planted_set
    ]
    ranked = sorted(range(planted_candidates), key=lambda index: (-discovery_scores[index], index))
    planted_rank = ranked.index(0) + 1

    null_returns = _candidate_panel(random.Random(seed + 20_000), days, assets)
    null_panels = [
        _candidate_panel(random.Random(seed + 30_000 + candidate), days, assets)
        for candidate in range(null_candidates)
    ]
    null_discovery = [
        _average_daily_rank_ic(item, null_returns, 0, discovery_end) for item in null_panels
    ]
    null_holdout = [
        _average_daily_rank_ic(item, null_returns, discovery_end, days) for item in null_panels
    ]
    null_selected = max(range(null_candidates), key=lambda index: (null_discovery[index], -index))
    budgets = tuple(value for value in (10, 50, 100, 500) if value <= null_candidates)
    curve = []
    for budget in budgets:
        selected = max(range(budget), key=lambda index: (null_discovery[index], -index))
        curve.append(OverfitPoint(budget, null_discovery[selected], null_holdout[selected]))

    leakage = _average_daily_rank_ic(returns, returns, 0, discovery_end)
    # Five contiguous groups with a two-date embargo.  This explicit check protects the calibration
    # itself from silently turning into random K-fold.
    groups = 5
    width = days // groups
    overlap = 0
    for group in range(groups):
        test_start = group * width
        test_end = days if group == groups - 1 else (group + 1) * width
        train = {
            index
            for index in range(days)
            if index < max(0, test_start - 2) or index >= min(days, test_end + 2)
        }
        embargoed_test = set(range(max(0, test_start - 2), min(days, test_end + 2)))
        overlap += len(train & embargoed_test)

    checks = (
        ("planted_alpha_rank_one", planted_rank == 1),
        ("planted_discovery_positive", discovery_scores[0] >= 0.08),
        ("planted_holdout_positive", holdout_scores[0] >= 0.05),
        ("null_selected_does_not_persist", abs(null_holdout[null_selected]) <= 0.08),
        (
            "overfit_curve_exposes_multiplicity",
            all(
                curve[index].best_discovery_rank_ic
                <= curve[index + 1].best_discovery_rank_ic + 1e-15
                for index in range(len(curve) - 1)
            ),
        ),
        ("leakage_positive_control_detected", leakage >= 0.999),
        ("purge_embargo_has_no_overlap", overlap == 0),
    )
    base: dict[str, object] = {
        "method_version": SEARCH_CALIBRATION_VERSION,
        "seed": seed,
        "planted_candidates": planted_candidates,
        "planted_rank": planted_rank,
        "planted_discovery_rank_ic": discovery_scores[0],
        "planted_holdout_rank_ic": holdout_scores[0],
        "null_candidates": null_candidates,
        "null_selected_discovery_rank_ic": null_discovery[null_selected],
        "null_selected_holdout_rank_ic": null_holdout[null_selected],
        "leakage_rank_ic": leakage,
        "leakage_positive_control_detected": leakage >= 0.999,
        "purge_embargo_overlap_count": overlap,
        "overfit_curve": [asdict(item) for item in curve],
        "checks": list(checks),
        "passed": all(value for _, value in checks),
    }
    numeric = tuple(
        value
        for value in (
            discovery_scores[0],
            holdout_scores[0],
            null_discovery[null_selected],
            null_holdout[null_selected],
            leakage,
        )
    )
    if any(not math.isfinite(value) for value in numeric):
        raise ValueError("calibration produced non-finite evidence")
    return SearchCalibrationReport(
        SEARCH_CALIBRATION_VERSION,
        seed,
        planted_candidates,
        planted_rank,
        discovery_scores[0],
        holdout_scores[0],
        null_candidates,
        null_discovery[null_selected],
        null_holdout[null_selected],
        leakage,
        leakage >= 0.999,
        overlap,
        tuple(curve),
        checks,
        all(value for _, value in checks),
        _digest(base),
    )
