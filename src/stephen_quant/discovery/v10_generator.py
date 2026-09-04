from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from itertools import combinations

V10_GENERATOR_VERSION = "10.0.0"


@dataclass(frozen=True)
class V10Field:
    name: str
    source: str
    unit: str
    availability: str


@dataclass(frozen=True)
class V10Candidate:
    candidate_id: str
    operator: str
    fields: tuple[V10Field, ...]
    direction: int
    mechanism: str
    expression: str
    maximum_availability: str


@dataclass(frozen=True)
class V10CandidatePacket:
    method_version: str
    policy_sha256: str
    budget: int
    generated: int
    deduplicated: int
    rejected: tuple[str, ...]
    candidates: tuple[V10Candidate, ...]
    labels_read: bool = False


FIELDS = (
    V10Field("ret_20", "qd_daily", "return", "T+1_OPEN"),
    V10Field("volatility_20", "qd_daily", "volatility", "T+1_OPEN"),
    V10Field("amount_rank_20", "qd_daily", "ratio", "T+1_OPEN"),
    V10Field("intraday_return", "minute_features", "return", "T+1_OPEN"),
    V10Field("late_30_return", "minute_features", "return", "T+1_OPEN"),
    V10Field("realized_volatility", "minute_features", "volatility", "T+1_OPEN"),
    V10Field("vwap_deviation", "minute_features", "return", "T+1_OPEN"),
    V10Field("opening_volume_share", "minute_features", "ratio", "T+1_OPEN"),
    V10Field("closing_volume_share", "minute_features", "ratio", "T+1_OPEN"),
    V10Field("amihud_intraday", "minute_features", "impact", "T+1_OPEN"),
    V10Field("multiscale_divergence", "minute_features", "return", "T+1_OPEN"),
    V10Field("net_inflow_ratio", "qd_fund_flow", "ratio", "T+1_OPEN"),
    V10Field("main_inflow_ratio", "qd_fund_flow", "ratio", "T+1_OPEN"),
    V10Field("auction_return", "qd_auction", "return", "T_OPEN"),
    V10Field("auction_amount_ratio", "qd_auction", "ratio", "T_OPEN"),
    V10Field("profit_ratio", "qd_chip", "ratio", "T+1_OPEN"),
    V10Field("concentration", "qd_chip", "ratio", "T+1_OPEN"),
)

MECHANISMS = {
    frozenset({"minute_features", "qd_fund_flow"}): "flow_persistence_vs_intraday_absorption",
    frozenset({"minute_features", "qd_auction"}): "auction_price_discovery_vs_session_path",
    frozenset({"minute_features", "qd_chip"}): "crowding_reversal_with_intraday_liquidity",
    frozenset({"qd_daily", "minute_features"}): "daily_intraday_multiscale_divergence",
    frozenset({"qd_daily", "qd_fund_flow"}): "flow_price_divergence",
    frozenset({"qd_fund_flow", "qd_chip"}): "flow_crowding_interaction",
}


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _candidate(operator: str, fields: tuple[V10Field, ...], direction: int, mechanism: str) -> V10Candidate:
    ordered = tuple(sorted(fields, key=lambda item: (item.source, item.name)))
    if operator == "rank":
        expression = f"rank({ordered[0].name})"
    elif operator == "divergence":
        expression = f"rank({ordered[0].name})-rank({ordered[1].name})"
    elif operator == "interaction":
        expression = "*".join(f"rank({item.name})" for item in ordered)
    else:
        raise ValueError(f"unsupported V10 operator: {operator}")
    identity = _sha(
        {"operator": operator, "fields": [asdict(item) for item in ordered], "direction": direction}
    )
    availability = "T+1_OPEN" if any(item.availability == "T+1_OPEN" for item in ordered) else "T_OPEN"
    return V10Candidate(identity, operator, ordered, direction, mechanism, expression, availability)


def generate_v10_candidates(
    *,
    budget: int,
    enabled_sources: tuple[str, ...] = (
        "qd_daily",
        "minute_features",
        "qd_fund_flow",
        "qd_auction",
        "qd_chip",
    ),
    historical_candidate_ids: frozenset[str] = frozenset(),
) -> V10CandidatePacket:
    if budget < 1 or budget > 10_000:
        raise ValueError("V10 candidate budget must be between 1 and 10000")
    enabled = frozenset(enabled_sources)
    fields = tuple(item for item in FIELDS if item.source in enabled)
    raw: list[V10Candidate] = []
    for field in fields:
        for direction in (-1, 1):
            raw.append(_candidate("rank", (field,), direction, f"single_source_{field.source}"))
    for left, right in combinations(fields, 2):
        sources = frozenset({left.source, right.source})
        mechanism = MECHANISMS.get(sources)
        if mechanism is None or left.source == right.source:
            continue
        for operator in ("divergence", "interaction"):
            for direction in (-1, 1):
                raw.append(_candidate(operator, (left, right), direction, mechanism))
    triads = (
        ("ret_20", "late_30_return", "net_inflow_ratio", "trend_absorption_flow"),
        ("vwap_deviation", "auction_return", "profit_ratio", "price_discovery_crowding"),
    )
    by_name = {item.name: item for item in fields}
    for left, middle, right, mechanism in triads:
        if {left, middle, right} <= set(by_name):
            for direction in (-1, 1):
                raw.append(
                    _candidate(
                        "interaction",
                        (by_name[left], by_name[middle], by_name[right]),
                        direction,
                        mechanism,
                    )
                )
    policy = {
        "version": V10_GENERATOR_VERSION,
        "budget": budget,
        "enabled_sources": sorted(enabled),
        "field_catalog": [asdict(item) for item in fields],
        "mechanisms": sorted(MECHANISMS.values()),
        "operators": ["rank", "divergence", "interaction"],
        "directions": [-1, 1],
    }
    unique: dict[str, V10Candidate] = {}
    rejected: list[str] = []
    for candidate in raw:
        if candidate.candidate_id in historical_candidate_ids:
            rejected.append(f"HISTORICAL_DUPLICATE:{candidate.candidate_id}")
            continue
        unique.setdefault(candidate.candidate_id, candidate)
    selected = tuple(unique[key] for key in sorted(unique)[:budget])
    return V10CandidatePacket(
        V10_GENERATOR_VERSION,
        _sha(policy),
        budget,
        len(raw),
        len(raw) - len(unique),
        tuple(sorted(rejected)),
        selected,
    )


def validate_candidate_availability(candidate: V10Candidate, execution_time: str) -> None:
    if execution_time not in {"T_OPEN", "T+1_OPEN"}:
        raise ValueError("unsupported V10 execution time")
    if execution_time == "T_OPEN" and candidate.maximum_availability == "T+1_OPEN":
        raise ValueError("candidate uses data unavailable at T_OPEN")
