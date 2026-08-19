from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Literal

from .models import SOURCE_FIELDS, FactorSchema

SEMANTIC_CATALOG_VERSION = "5.5.0"
ResearchForm = Literal[
    "continuous_ranking",
    "event_study",
    "portfolio_filter",
    "regime_switch",
]
MissingMeaning = Literal[
    "unknown",
    "not_applicable",
    "structural_zero",
    "source_absence",
]


@dataclass(frozen=True)
class FieldSemantic:
    field: str
    source: str
    value_type: str
    unit: str
    frequency: str
    availability: str
    sparsity: str
    missing_meaning: MissingMeaning
    economic_role: str
    allowed_forms: tuple[ResearchForm, ...]

    def validate(self) -> None:
        if self.source not in SOURCE_FIELDS or self.field not in SOURCE_FIELDS[self.source]:
            raise ValueError(f"field semantic is outside declared source contract: {self.source}.{self.field}")
        if not all(
            value.strip()
            for value in (
                self.value_type,
                self.unit,
                self.frequency,
                self.availability,
                self.sparsity,
                self.economic_role,
            )
        ):
            raise ValueError("field semantic text cannot be empty")
        if not self.allowed_forms or len(set(self.allowed_forms)) != len(self.allowed_forms):
            raise ValueError("field semantic requires unique allowed research forms")


def _field(
    source: str,
    field: str,
    *,
    value_type: str = "continuous",
    unit: str = "ratio",
    frequency: str = "daily",
    availability: str = "after_source_session",
    sparsity: str = "dense",
    missing: MissingMeaning = "unknown",
    role: str = "cross_sectional_measure",
    forms: tuple[ResearchForm, ...] = ("continuous_ranking", "portfolio_filter"),
) -> FieldSemantic:
    result = FieldSemantic(
        field,
        source,
        value_type,
        unit,
        frequency,
        availability,
        sparsity,
        missing,
        role,
        forms,
    )
    result.validate()
    return result


def build_semantic_catalog() -> tuple[FieldSemantic, ...]:
    entries: dict[tuple[str, str], FieldSemantic] = {}

    def put(item: FieldSemantic) -> None:
        key = (item.source, item.field)
        if key in entries:
            raise ValueError(f"duplicate field semantic: {key}")
        entries[key] = item

    price_units = {
        "amount": "CNY",
        "benchmark_close": "CNY_per_share",
        "close": "CNY_per_share",
        "high": "CNY_per_share",
        "low": "CNY_per_share",
        "turnover": "ratio",
        "volume": "shares",
    }
    for name, unit in price_units.items():
        put(
            _field(
                "qd_daily",
                name,
                unit=unit,
                availability="after_market_close",
                missing="source_absence",
                role="market_state" if name == "benchmark_close" else "price_liquidity",
                forms=(
                    "continuous_ranking",
                    "event_study",
                    "portfolio_filter",
                    "regime_switch",
                ),
            )
        )

    money_fields = {
        "net_inflow_amount",
        "large_buy_amount",
        "large_sell_amount",
        "extra_large_buy_amount",
        "extra_large_sell_amount",
    }
    for name in money_fields:
        put(
            _field(
                "qd_fund_flow",
                name,
                unit="CNY",
                availability="after_market_close",
                missing="unknown",
                role="investor_flow",
            )
        )

    auction_units = {
        "auction_return": "return",
        "auction_amount": "CNY",
        "auction_volume_ratio_1": "ratio",
    }
    for name, unit in auction_units.items():
        put(
            _field(
                "qd_auction",
                name,
                unit=unit,
                availability="after_opening_auction_before_continuous_session",
                sparsity="event_conditioned",
                missing="unknown",
                role="opening_auction_event",
                forms=("event_study", "portfolio_filter"),
            )
        )

    margin_units = {
        "margin_financing_balance": "CNY",
        "margin_financing_buy": "CNY",
        "margin_financing_repay": "CNY",
    }
    for name, unit in margin_units.items():
        put(
            _field(
                "qd_margin",
                name,
                unit=unit,
                availability="after_prior_session_publication",
                missing="unknown",
                role="leverage_demand_state",
                forms=("continuous_ranking", "portfolio_filter"),
            )
        )

    for name in ("industry_return", "industry_pe", "industry_pb"):
        put(
            _field(
                "qd_industry",
                name,
                unit="return" if name == "industry_return" else "multiple",
                availability="after_industry_snapshot_publication",
                missing="unknown",
                role="industry_context",
                forms=("continuous_ranking", "portfolio_filter", "regime_switch"),
            )
        )

    for name in (
        "chip_cost_5",
        "chip_cost_15",
        "chip_cost_50",
        "chip_cost_85",
        "chip_cost_95",
        "chip_weighted_cost",
    ):
        put(
            _field(
                "qd_chip",
                name,
                unit="CNY_per_share",
                availability="after_market_close_unproven_historical_vintage",
                missing="unknown",
                role="holder_cost_distribution",
            )
        )
    put(
        _field(
            "qd_chip",
            "chip_win_rate",
            unit="ratio",
            availability="after_market_close_unproven_historical_vintage",
            missing="unknown",
            role="holder_profit_state",
        )
    )

    limit_units = {
        "kpl_limit_up_flag": "binary",
        "kpl_main_net_amount": "CNY",
        "kpl_close_seal_amount": "CNY",
        "kpl_turnover_amount": "CNY",
        "kpl_float_market_cap": "CNY",
        "kpl_max_seal_amount": "CNY",
    }
    for name, unit in limit_units.items():
        put(
            _field(
                "qd_limit_event",
                name,
                value_type="binary" if name == "kpl_limit_up_flag" else "continuous",
                unit=unit,
                availability="after_limit_event_session_close",
                sparsity="sparse_event",
                missing=("structural_zero" if name == "kpl_limit_up_flag" else "not_applicable"),
                role="limit_event",
                forms=("event_study", "portfolio_filter"),
            )
        )

    expected = {(source, field) for source, fields in SOURCE_FIELDS.items() for field in fields}
    if set(entries) != expected:
        missing = sorted(expected - set(entries))
        extra = sorted(set(entries) - expected)
        raise AssertionError(f"semantic catalog coverage mismatch: missing={missing}, extra={extra}")
    return tuple(entries[key] for key in sorted(entries))


@dataclass(frozen=True)
class CandidateRoutingDecision:
    schema_id: str
    schema_fingerprint: str
    semantic_identity: str
    primary_form: ResearchForm
    allowed_forms: tuple[ResearchForm, ...]
    sources: tuple[str, ...]
    missing_policies: tuple[tuple[str, MissingMeaning], ...]
    reasons: tuple[str, ...]


def _semantic_identity(schema: FactorSchema, form: ResearchForm) -> str:
    payload = {
        "schema_fingerprint": schema.fingerprint,
        "research_form": form,
        "version": SEMANTIC_CATALOG_VERSION,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def route_factor_schema(
    schema: FactorSchema,
    *,
    requested_form: ResearchForm | None = None,
    catalog: tuple[FieldSemantic, ...] | None = None,
) -> CandidateRoutingDecision:
    schema.validate()
    catalog = catalog or build_semantic_catalog()
    semantics = {(item.source, item.field): item for item in catalog}
    used: list[FieldSemantic] = []
    for field in schema.required_fields:
        matches = [semantics[(source, field)] for source in schema.data_sources if (source, field) in semantics]
        if len(matches) != 1:
            raise ValueError(f"field must resolve to exactly one source semantic: {field}")
        used.append(matches[0])
    allowed = set(used[0].allowed_forms)
    for item in used[1:]:
        allowed &= set(item.allowed_forms)
    if not allowed:
        raise ValueError("candidate fields have no compatible research form")

    sources = set(schema.data_sources)
    reasons = []
    if "qd_limit_event" in sources:
        preferred: ResearchForm = "event_study"
        reasons.append("sparse limit-event inputs require event-conditioned evaluation")
    elif "qd_auction" in sources:
        preferred = "event_study"
        reasons.append("opening-auction inputs are routed to event-conditioned evaluation")
    elif "qd_margin" in sources:
        preferred = "continuous_ranking"
        reasons.append("published leverage state supports ranking and portfolio-filter roles")
    elif schema.event in {"market_regime", "risk_state", "liquidity_state"}:
        preferred = "regime_switch"
        reasons.append("market-state hypothesis controls portfolio regime")
    else:
        preferred = "continuous_ranking"
        reasons.append("dense point-in-time measures support cross-sectional ranking")
    if preferred not in allowed:
        preferred = min(allowed)  # deterministic fallback after semantic intersection
        reasons.append("preferred form narrowed by cross-source semantic compatibility")
    if requested_form is not None:
        if requested_form not in allowed:
            raise ValueError(
                f"requested research form {requested_form} is incompatible with fields"
            )
        preferred = requested_form
        reasons.append("caller-selected form accepted by semantic contract")

    missing = tuple(sorted((item.field, item.missing_meaning) for item in used))
    return CandidateRoutingDecision(
        schema.schema_id,
        schema.fingerprint,
        _semantic_identity(schema, preferred),
        preferred,
        tuple(sorted(allowed)),
        tuple(sorted(schema.data_sources)),
        missing,
        tuple(reasons),
    )


def failure_memory_identity(decision: CandidateRoutingDecision, failure_code: str) -> str:
    if not failure_code or any(char.isspace() for char in failure_code):
        raise ValueError("failure code must be a non-empty token")
    payload = {
        "semantic_identity": decision.semantic_identity,
        "research_form": decision.primary_form,
        "failure_code": failure_code,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def renamed_schema(schema: FactorSchema, schema_id: str, name: str) -> FactorSchema:
    """Test/support helper: names never change semantic or failure identity."""

    return replace(schema, schema_id=schema_id, name=name)


def catalog_to_json(catalog: tuple[FieldSemantic, ...] | None = None) -> str:
    return json.dumps(
        [asdict(item) for item in (catalog or build_semantic_catalog())],
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    )
