from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from itertools import combinations

SEARCH_POWER_DSL_VERSION = "11.3.0"


@dataclass(frozen=True)
class SearchField:
    name: str
    source: str
    unit: str
    availability: str = "T+1_OPEN"


@dataclass(frozen=True)
class SearchCandidate:
    candidate_id: str
    canonical_ast: str
    domain: str
    operator: str
    fields: tuple[SearchField, ...]
    direction: int
    horizon: int
    universe: str
    portfolio_mapping: str
    holding_rule: str
    execution_rule: str
    cost_model: str
    complexity: int
    parent_ids: tuple[str, ...] = ()

    @property
    def expression(self) -> str:
        sign = "" if self.direction > 0 else "-"
        return f"{sign}{self.canonical_ast}"


@dataclass(frozen=True)
class StaticCatalog:
    version: str
    generated_count: int
    unique_count: int
    duplicate_count: int
    catalog_sha256: str
    candidates: tuple[SearchCandidate, ...]


FIELDS = {
    field.name: field
    for field in (
        SearchField("ret_20", "qd_daily", "return"),
        SearchField("volatility_20", "qd_daily", "volatility"),
        SearchField("amount_rank_20", "qd_daily", "ratio"),
        SearchField("intraday_return", "minute_features", "return"),
        SearchField("late_30_return", "minute_features", "return"),
        SearchField("realized_volatility", "minute_features", "volatility"),
        SearchField("vwap_deviation", "minute_features", "return"),
        SearchField("opening_volume_share", "minute_features", "ratio"),
        SearchField("closing_volume_share", "minute_features", "ratio"),
        SearchField("amihud_intraday", "minute_features", "impact"),
        SearchField("net_inflow_ratio", "qd_fund_flow", "ratio"),
        SearchField("main_inflow_ratio", "qd_fund_flow", "ratio"),
        SearchField("net_inflow_ratio_change", "qd_fund_flow", "change"),
        SearchField("main_inflow_ratio_change", "qd_fund_flow", "change"),
        SearchField("net_inflow_ratio_persistence", "qd_fund_flow", "ratio"),
        SearchField("main_inflow_ratio_persistence", "qd_fund_flow", "ratio"),
        SearchField("auction_return", "qd_auction", "return", "T_OPEN"),
        SearchField("auction_amount_ratio", "qd_auction", "ratio", "T_OPEN"),
        SearchField("profit_ratio", "qd_chip", "ratio"),
        SearchField("concentration", "qd_chip", "ratio"),
        SearchField("profit_ratio_change", "qd_chip", "change"),
        SearchField("concentration_change", "qd_chip", "change"),
    )
}


DOMAIN_FIELDS = {
    "price_liquidity_state": (
        "ret_20", "volatility_20", "amount_rank_20", "intraday_return",
        "late_30_return", "realized_volatility", "vwap_deviation",
        "opening_volume_share", "closing_volume_share", "amihud_intraday",
        "net_inflow_ratio", "main_inflow_ratio", "concentration",
    ),
    "industry_relative_flow": (
        "ret_20", "volatility_20", "amount_rank_20", "intraday_return",
        "vwap_deviation", "closing_volume_share", "net_inflow_ratio",
        "main_inflow_ratio", "net_inflow_ratio_change", "main_inflow_ratio_change",
        "net_inflow_ratio_persistence", "main_inflow_ratio_persistence", "concentration_change",
    ),
    "auction_close_chip_gate": (
        "ret_20", "volatility_20", "intraday_return", "late_30_return",
        "realized_volatility", "vwap_deviation", "opening_volume_share",
        "closing_volume_share", "auction_return", "auction_amount_ratio",
        "profit_ratio", "concentration", "concentration_change",
    ),
}


DOMAIN_POLICY = {
    "price_liquidity_state": (20, "LIQUID_TOP800", "TOP40_BUFFER10"),
    "industry_relative_flow": (10, "LIQUID_TOP800", "INDUSTRY_CAPPED_TOP40_BUFFER10"),
    "auction_close_chip_gate": (5, "LIQUID_TOP800", "STATE_GATED_TOP40_BUFFER10"),
}

COMMUTATIVE = {
    "centered_sum", "centered_interaction", "joint_min", "joint_max",
    "triple_sum", "triple_interaction", "majority_state",
}
PAIR_OPERATORS = (
    "divergence", "centered_sum", "centered_interaction", "joint_min", "joint_max",
    "absolute_contrast",
)
TRIPLE_OPERATORS = (
    "triple_sum", "triple_interaction", "gate_high", "gate_low", "majority_state",
)


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _ast(operator: str, names: tuple[str, ...]) -> str:
    ordered = tuple(sorted(names)) if operator in COMMUTATIVE else names
    return f"{operator}({','.join(ordered)})"


def _candidate(
    domain: str,
    operator: str,
    names: tuple[str, ...],
    direction: int,
) -> SearchCandidate:
    if direction not in {-1, 1}:
        raise ValueError("candidate direction must be -1 or 1")
    if not 1 <= len(names) <= 3 or len(set(names)) != len(names):
        raise ValueError("candidate requires one to three unique fields")
    fields = tuple(FIELDS[name] for name in names)
    horizon, universe, mapping = DOMAIN_POLICY[domain]
    ast = _ast(operator, names)
    identity = {
        "dsl_version": SEARCH_POWER_DSL_VERSION,
        "canonical_signal_ast": ast,
        "direction": direction,
        "domain": domain,
        "universe": universe,
        "portfolio_mapping": mapping,
        "holding_rule": f"HOLD_{horizon}_SESSIONS",
        "execution_rule": "NEXT_SESSION_OPEN",
        "cost_model": "ROUND_TRIP_41BPS_DOUBLE_82BPS",
        "feature_availability": sorted({field.availability for field in fields}),
    }
    return SearchCandidate(
        sha256_json(identity), ast, domain, operator, fields, direction, horizon,
        universe, mapping, f"HOLD_{horizon}_SESSIONS", "NEXT_SESSION_OPEN",
        "ROUND_TRIP_41BPS_DOUBLE_82BPS", 1 + len(fields),
    )


def generate_static_catalog() -> StaticCatalog:
    raw: list[SearchCandidate] = []
    for domain, field_names in DOMAIN_FIELDS.items():
        for name in field_names:
            for direction in (-1, 1):
                raw.append(_candidate(domain, "rank", (name,), direction))
        for names in combinations(field_names, 2):
            for operator in PAIR_OPERATORS:
                for direction in (-1, 1):
                    raw.append(_candidate(domain, operator, names, direction))
        for names in combinations(field_names, 3):
            for operator in TRIPLE_OPERATORS:
                for direction in (-1, 1):
                    raw.append(_candidate(domain, operator, names, direction))
    unique = {candidate.candidate_id: candidate for candidate in raw}
    candidates = tuple(unique[key] for key in sorted(unique))
    if len(candidates) < 10_000:
        raise RuntimeError("V11.3 static catalog must contain at least 10,000 identities")
    return StaticCatalog(
        SEARCH_POWER_DSL_VERSION,
        len(raw),
        len(candidates),
        len(raw) - len(candidates),
        sha256_json([asdict(item) for item in candidates]),
        candidates,
    )


def select_label_budget(
    catalog: StaticCatalog, budget: int = 1_000
) -> tuple[SearchCandidate, ...]:
    if budget < 1 or budget > 1_000:
        raise ValueError("V11.3 initial real-label budget is capped at 1,000")
    groups: dict[tuple[str, str], list[SearchCandidate]] = {}
    for candidate in catalog.candidates:
        groups.setdefault((candidate.domain, candidate.operator), []).append(candidate)
    selected: list[SearchCandidate] = []
    depth = 0
    strata = tuple(sorted(groups))
    while len(selected) < budget:
        added = False
        for key in strata:
            values = groups[key]
            if depth < len(values):
                selected.append(values[depth])
                added = True
                if len(selected) == budget:
                    break
        if not added:
            break
        depth += 1
    if len(selected) != budget:
        raise RuntimeError("static catalog cannot satisfy the frozen label budget")
    return tuple(selected)


def score_vector(candidate: SearchCandidate, ranks: Mapping[str, Sequence[float]]) -> list[float]:
    values = [ranks[field.name] for field in candidate.fields]
    lengths = {len(item) for item in values}
    if len(lengths) != 1:
        raise ValueError("candidate field arrays have inconsistent lengths")
    result: list[float] = []
    for cells in zip(*values, strict=True):
        centered = tuple(2.0 * value - 1.0 for value in cells)
        if candidate.operator == "rank":
            score = cells[0]
        elif candidate.operator == "divergence":
            score = cells[0] - cells[1]
        elif candidate.operator == "centered_sum":
            score = sum(centered) / len(centered)
        elif candidate.operator == "centered_interaction":
            score = math.prod(centered)
        elif candidate.operator == "joint_min":
            score = min(centered)
        elif candidate.operator == "joint_max":
            score = max(centered)
        elif candidate.operator == "absolute_contrast":
            score = -abs(cells[0] - cells[1])
        elif candidate.operator == "triple_sum":
            score = sum(centered) / 3.0
        elif candidate.operator == "triple_interaction":
            score = math.prod(centered)
        elif candidate.operator == "gate_high":
            score = (centered[0] + centered[1]) / 2.0 if cells[2] >= 0.70 else -1.0
        elif candidate.operator == "gate_low":
            score = (centered[0] + centered[1]) / 2.0 if cells[2] <= 0.30 else -1.0
        elif candidate.operator == "majority_state":
            score = sum(1.0 if value >= 0.5 else -1.0 for value in cells) / 3.0
        else:
            raise ValueError(f"unsupported Search Power operator: {candidate.operator}")
        result.append(candidate.direction * score)
    return result


def validate_candidate(candidate: SearchCandidate) -> None:
    if candidate.domain not in DOMAIN_FIELDS:
        raise ValueError("unknown mechanism domain")
    if any(field.name not in DOMAIN_FIELDS[candidate.domain] for field in candidate.fields):
        raise ValueError("candidate field is outside its mechanism domain")
    if candidate.execution_rule == "T_OPEN" and any(
        field.availability == "T+1_OPEN" for field in candidate.fields
    ):
        raise ValueError("candidate leaks unavailable feature data")
    expected = _candidate(
        candidate.domain,
        candidate.operator,
        tuple(field.name for field in candidate.fields),
        candidate.direction,
    )
    if expected != candidate:
        raise ValueError("candidate identity does not match its complete research hypothesis")
