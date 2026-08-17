from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from enum import Enum

from stephen_quant.research_agent.dsl import analyze_formula

SEMANTIC_SEARCH_VERSION = "semantic-search-1.0.0"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_HORIZONS = {"next_open", "1d", "5d", "20d"}
_SEALED_MARKERS = ("2025", "2026")


def canonical_json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _require_text(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} cannot be empty")


def _unique_text(name: str, values: tuple[str, ...], *, allow_empty: bool = False) -> None:
    if not allow_empty and not values:
        raise ValueError(f"{name} cannot be empty")
    if any(not value.strip() for value in values) or len(values) != len(set(values)):
        raise ValueError(f"{name} must contain unique non-empty values")


def reject_sealed_references(value: object) -> None:
    """Reject any label-free artifact that mentions consumed/sealed calendar years."""

    if isinstance(value, Mapping):
        for key, item in value.items():
            reject_sealed_references(str(key))
            reject_sealed_references(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            reject_sealed_references(item)
    elif isinstance(value, str) and any(marker in value for marker in _SEALED_MARKERS):
        raise ValueError("label-free search cannot reference sealed or consumed windows")


class ContextRole(str, Enum):
    CONSTITUTIVE = "CONSTITUTIVE"
    ELIGIBILITY = "ELIGIBILITY"
    POLICY_CONDITION = "POLICY_CONDITION"


class PITReadiness(str, Enum):
    READY = "READY"
    CONDITIONAL = "CONDITIONAL"
    BLOCKED = "BLOCKED"


class ControlKind(str, Enum):
    PRIMARY = "PRIMARY"
    REVERSE_SIGN = "REVERSE_SIGN"
    REVERSE_RANK = "REVERSE_RANK"


class ChangeLayer(str, Enum):
    NONE = "NONE"
    FAMILY = "FAMILY"
    EXPRESSION = "EXPRESSION"
    PARAMETER = "PARAMETER"
    POLICY = "POLICY"
    CONTRACT = "CONTRACT"


class StaticDecisionCode(str, Enum):
    ACCEPT = "ACCEPT"
    DATA_NOT_RESEARCH_READY = "DATA_NOT_RESEARCH_READY"
    SEMANTIC_DUPLICATE = "SEMANTIC_DUPLICATE"
    EXPRESSION_DUPLICATE = "EXPRESSION_DUPLICATE"
    TOMBSTONE_DESCENDANT = "TOMBSTONE_DESCENDANT"


@dataclass(frozen=True)
class SemanticContext:
    value: str
    role: ContextRole

    def validate(self) -> None:
        _require_text("semantic context", self.value)


@dataclass(frozen=True)
class SemanticPlan:
    plan_id: str
    economic_claim: str
    event: str
    contexts: tuple[SemanticContext, ...]
    data_semantics: tuple[str, ...]
    information_set: tuple[str, ...]
    transmission_path: str
    economic_direction: int
    observable_proxy: str
    required_data: tuple[str, ...]
    pit_readiness: tuple[tuple[str, PITReadiness], ...]
    falsification: tuple[str, ...]
    primary_horizon: str
    secondary_horizon: str | None
    logic_budget: int
    parameter_budget: int

    def validate(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", self.plan_id):
            raise ValueError("plan_id must use lowercase snake_case")
        for name, value in (
            ("economic claim", self.economic_claim),
            ("event", self.event),
            ("transmission path", self.transmission_path),
        ):
            _require_text(name, value)
        if self.economic_direction not in {-1, 1}:
            raise ValueError("economic_direction must be -1 or 1")
        if self.primary_horizon not in _HORIZONS:
            raise ValueError("unsupported primary horizon")
        if self.secondary_horizon is not None and (
            self.secondary_horizon not in _HORIZONS
            or self.secondary_horizon == self.primary_horizon
        ):
            raise ValueError("secondary horizon must be supported and distinct")
        if self.logic_budget < 1 or self.parameter_budget < 0:
            raise ValueError("semantic budgets must be non-negative with positive logic budget")
        if not self.contexts or len(self.contexts) != len(
            {(item.value, item.role) for item in self.contexts}
        ):
            raise ValueError("contexts must be non-empty and unique")
        for context in self.contexts:
            context.validate()
        if not any(item.role == ContextRole.CONSTITUTIVE for item in self.contexts):
            raise ValueError("at least one CONSTITUTIVE context is required")
        _unique_text("data_semantics", self.data_semantics)
        _unique_text("information_set", self.information_set)
        _unique_text("required_data", self.required_data)
        _unique_text("falsification", self.falsification)
        readiness_fields = tuple(field for field, _ in self.pit_readiness)
        _unique_text("pit_readiness fields", readiness_fields)
        if set(readiness_fields) != set(self.required_data):
            raise ValueError("PIT readiness must cover required_data exactly")
        analysis = analyze_formula(self.observable_proxy)
        if not set(analysis.required_fields) <= set(self.required_data):
            raise ValueError("observable proxy fields must be declared in required_data")
        reject_sealed_references(asdict(self))

    @property
    def constitutive_contexts(self) -> tuple[str, ...]:
        return tuple(
            sorted(item.value for item in self.contexts if item.role == ContextRole.CONSTITUTIVE)
        )

    @property
    def family_payload(self) -> dict[str, object]:
        self.validate()
        return {
            "economic_claim": self.economic_claim,
            "event": self.event,
            "constitutive_contexts": self.constitutive_contexts,
            "data_semantics": sorted(self.data_semantics),
            "information_set": sorted(self.information_set),
            "transmission_path": self.transmission_path,
            "economic_direction": self.economic_direction,
        }

    @property
    def plan_sha256(self) -> str:
        self.validate()
        return sha256(asdict(self))

    @property
    def family_sha256(self) -> str:
        return sha256(self.family_payload)


@dataclass(frozen=True)
class ExpressionVariant:
    family_sha256: str
    formula: str
    control_kind: ControlKind = ControlKind.PRIMARY

    def validate(self) -> None:
        if _SHA256.fullmatch(self.family_sha256) is None:
            raise ValueError("expression requires a family SHA-256")
        analyze_formula(self.formula)

    @property
    def expression_sha256(self) -> str:
        self.validate()
        analysis = analyze_formula(self.formula)
        return sha256(
            {
                "family_sha256": self.family_sha256,
                "canonical_ast": analysis.canonical_ast,
                "required_fields": analysis.required_fields,
                "control_kind": self.control_kind.value,
            }
        )


@dataclass(frozen=True)
class ParameterVariant:
    expression_sha256: str
    parameters: tuple[tuple[str, str], ...]

    def validate(self) -> None:
        if _SHA256.fullmatch(self.expression_sha256) is None:
            raise ValueError("parameter variant requires an expression SHA-256")
        names = tuple(name for name, _ in self.parameters)
        _unique_text("parameter names", names, allow_empty=True)
        if tuple(sorted(self.parameters)) != self.parameters:
            raise ValueError("parameters must be sorted deterministically")

    @property
    def parameter_sha256(self) -> str:
        self.validate()
        return sha256(asdict(self))


@dataclass(frozen=True)
class PolicyVariant:
    parameter_sha256: str
    top_k: int
    threshold: str
    weighting: str
    regime: str
    execution: str

    def validate(self) -> None:
        if _SHA256.fullmatch(self.parameter_sha256) is None or self.top_k < 1:
            raise ValueError("policy requires parameter SHA-256 and positive top_k")
        for name, value in (
            ("threshold", self.threshold),
            ("weighting", self.weighting),
            ("regime", self.regime),
            ("execution", self.execution),
        ):
            _require_text(name, value)

    @property
    def policy_sha256(self) -> str:
        self.validate()
        return sha256(asdict(self))


@dataclass(frozen=True)
class ResearchContractVersion:
    contract_version: str
    primary_horizon: str
    secondary_horizon: str | None
    falsification: tuple[str, ...]
    pit_readiness: tuple[tuple[str, PITReadiness], ...]
    snapshot_authority: str
    window_authority: str
    logic_budget: int
    parameter_budget: int
    empirical_trial_budget: int = 0

    def validate(self) -> None:
        _require_text("contract_version", self.contract_version)
        if self.primary_horizon not in _HORIZONS:
            raise ValueError("contract primary horizon is unsupported")
        if self.secondary_horizon is not None and (
            self.secondary_horizon not in _HORIZONS
            or self.secondary_horizon == self.primary_horizon
        ):
            raise ValueError("contract secondary horizon is invalid")
        _unique_text("contract falsification", self.falsification)
        readiness_fields = tuple(field for field, _ in self.pit_readiness)
        _unique_text("contract readiness fields", readiness_fields)
        for name, value in (
            ("snapshot_authority", self.snapshot_authority),
            ("window_authority", self.window_authority),
        ):
            _require_text(name, value)
        if self.logic_budget < 1 or self.parameter_budget < 0:
            raise ValueError("contract budgets are invalid")
        if self.empirical_trial_budget != 0:
            raise ValueError("label-free contract requires zero empirical trial budget")
        reject_sealed_references(asdict(self))

    @property
    def contract_sha256(self) -> str:
        self.validate()
        return sha256(asdict(self))


@dataclass(frozen=True)
class CandidateIdentity:
    plan: SemanticPlan
    expression: ExpressionVariant
    parameter: ParameterVariant
    policy: PolicyVariant
    contract: ResearchContractVersion
    parent_policy_sha256: str | None = None

    def validate(self) -> None:
        self.plan.validate()
        self.expression.validate()
        self.parameter.validate()
        self.policy.validate()
        self.contract.validate()
        if self.expression.family_sha256 != self.plan.family_sha256:
            raise ValueError("expression is not linked to the plan family")
        if self.parameter.expression_sha256 != self.expression.expression_sha256:
            raise ValueError("parameter variant is not linked to the expression")
        if self.policy.parameter_sha256 != self.parameter.parameter_sha256:
            raise ValueError("policy variant is not linked to the parameter variant")
        if (
            self.contract.primary_horizon != self.plan.primary_horizon
            or self.contract.secondary_horizon != self.plan.secondary_horizon
            or self.contract.falsification != self.plan.falsification
            or self.contract.pit_readiness != self.plan.pit_readiness
        ):
            raise ValueError("research contract does not match the semantic plan")
        if self.parent_policy_sha256 is not None and _SHA256.fullmatch(
            self.parent_policy_sha256
        ) is None:
            raise ValueError("parent policy identity must be SHA-256")

    @property
    def identity_sha256(self) -> str:
        self.validate()
        return sha256(
            {
                "plan": self.plan.plan_sha256,
                "family": self.plan.family_sha256,
                "expression": self.expression.expression_sha256,
                "parameter": self.parameter.parameter_sha256,
                "policy": self.policy.policy_sha256,
                "contract": self.contract.contract_sha256,
                "parent": self.parent_policy_sha256,
            }
        )


def build_candidate_identity(
    plan: SemanticPlan,
    *,
    parameters: tuple[tuple[str, str], ...] = (),
    top_k: int = 10,
    threshold: str = "none",
    weighting: str = "equal",
    regime: str = "all",
    execution: str = "not_authorized",
    control_kind: ControlKind = ControlKind.PRIMARY,
    contract_version: str = "label-free-contract-1.0.0",
    snapshot_authority: str = "synthetic-fixture-only",
    window_authority: str = "no-real-window-access",
    parent_policy_sha256: str | None = None,
) -> CandidateIdentity:
    plan.validate()
    expression = ExpressionVariant(plan.family_sha256, plan.observable_proxy, control_kind)
    parameter = ParameterVariant(expression.expression_sha256, tuple(sorted(parameters)))
    policy = PolicyVariant(
        parameter.parameter_sha256, top_k, threshold, weighting, regime, execution
    )
    contract = ResearchContractVersion(
        contract_version,
        plan.primary_horizon,
        plan.secondary_horizon,
        plan.falsification,
        plan.pit_readiness,
        snapshot_authority,
        window_authority,
        plan.logic_budget,
        plan.parameter_budget,
        0,
    )
    identity = CandidateIdentity(
        plan, expression, parameter, policy, contract, parent_policy_sha256
    )
    identity.validate()
    return identity


def classify_change(before: CandidateIdentity, after: CandidateIdentity) -> ChangeLayer:
    before.validate()
    after.validate()
    changes: list[ChangeLayer] = []
    before_expression = (
        analyze_formula(before.expression.formula).canonical_ast,
        before.expression.control_kind,
    )
    after_expression = (
        analyze_formula(after.expression.formula).canonical_ast,
        after.expression.control_kind,
    )
    before_policy = (
        before.policy.top_k,
        before.policy.threshold,
        before.policy.weighting,
        before.policy.regime,
        before.policy.execution,
    )
    after_policy = (
        after.policy.top_k,
        after.policy.threshold,
        after.policy.weighting,
        after.policy.regime,
        after.policy.execution,
    )
    for layer, left, right in (
        (ChangeLayer.FAMILY, before.plan.family_payload, after.plan.family_payload),
        (
            ChangeLayer.EXPRESSION,
            before_expression,
            after_expression,
        ),
        (
            ChangeLayer.PARAMETER,
            before.parameter.parameters,
            after.parameter.parameters,
        ),
        (ChangeLayer.POLICY, before_policy, after_policy),
        (
            ChangeLayer.CONTRACT,
            asdict(before.contract),
            asdict(after.contract),
        ),
    ):
        if left != right:
            changes.append(layer)
    if len(changes) > 1:
        raise ValueError("one search transition may change exactly one identity layer")
    return changes[0] if changes else ChangeLayer.NONE


def validate_transition(before: CandidateIdentity, after: CandidateIdentity) -> ChangeLayer:
    layer = classify_change(before, after)
    if layer != ChangeLayer.NONE and after.parent_policy_sha256 != before.policy.policy_sha256:
        raise ValueError("derived candidate must bind its parent policy SHA-256")
    return layer


@dataclass(frozen=True)
class StaticDecision:
    candidate_sha256: str
    accepted: bool
    code: StaticDecisionCode
    matched_sha256: str | None


def static_gate(
    identity: CandidateIdentity,
    *,
    known_family_sha256: tuple[str, ...] = (),
    known_expression_sha256: tuple[str, ...] = (),
    tombstoned_family_sha256: tuple[str, ...] = (),
) -> StaticDecision:
    identity.validate()
    readiness = dict(identity.plan.pit_readiness)
    if any(status == PITReadiness.BLOCKED for status in readiness.values()):
        return StaticDecision(
            identity.identity_sha256,
            False,
            StaticDecisionCode.DATA_NOT_RESEARCH_READY,
            None,
        )
    family = identity.plan.family_sha256
    expression = identity.expression.expression_sha256
    if family in tombstoned_family_sha256:
        return StaticDecision(
            identity.identity_sha256,
            False,
            StaticDecisionCode.TOMBSTONE_DESCENDANT,
            family,
        )
    if family in known_family_sha256:
        return StaticDecision(
            identity.identity_sha256,
            False,
            StaticDecisionCode.SEMANTIC_DUPLICATE,
            family,
        )
    if expression in known_expression_sha256:
        return StaticDecision(
            identity.identity_sha256,
            False,
            StaticDecisionCode.EXPRESSION_DUPLICATE,
            expression,
        )
    return StaticDecision(identity.identity_sha256, True, StaticDecisionCode.ACCEPT, None)


@dataclass(frozen=True)
class RemoteLedgerRecord:
    request_id: str
    provider: str
    advertised_model: str
    provider_model_version: str
    prompt_template_version: str
    rendered_prompt: str
    sampling_config_json: str
    raw_response: str
    tool_calls_json: str
    parser_version: str
    retry_parent_id: str | None = None

    def validate(self) -> None:
        for name, value in (
            ("request_id", self.request_id),
            ("provider", self.provider),
            ("advertised_model", self.advertised_model),
            ("provider_model_version", self.provider_model_version),
            ("prompt_template_version", self.prompt_template_version),
            ("rendered_prompt", self.rendered_prompt),
            ("raw_response", self.raw_response),
            ("parser_version", self.parser_version),
        ):
            _require_text(name, value)
        for name, payload in (
            ("sampling config", self.sampling_config_json),
            ("tool calls", self.tool_calls_json),
        ):
            try:
                json.loads(payload)
            except json.JSONDecodeError as exc:
                raise ValueError(f"remote {name} must be valid JSON") from exc
        reject_sealed_references(asdict(self))

    @property
    def request_bytes_sha256(self) -> str:
        self.validate()
        return hashlib.sha256(self.rendered_prompt.encode()).hexdigest()

    @property
    def response_bytes_sha256(self) -> str:
        self.validate()
        return hashlib.sha256(self.raw_response.encode()).hexdigest()

    @property
    def ledger_sha256(self) -> str:
        self.validate()
        return sha256(
            {
                **asdict(self),
                "request_bytes_sha256": self.request_bytes_sha256,
                "response_bytes_sha256": self.response_bytes_sha256,
            }
        )


class ContentAddressedRemoteCache:
    """Offline-only cache. Cache misses fail; there is deliberately no network callback."""

    def __init__(self, records: tuple[RemoteLedgerRecord, ...]) -> None:
        self._records: dict[str, RemoteLedgerRecord] = {}
        for record in records:
            record.validate()
            if record.request_bytes_sha256 in self._records:
                raise ValueError("remote cache request hashes must be unique")
            self._records[record.request_bytes_sha256] = record

    def replay(self, request_bytes_sha256: str) -> RemoteLedgerRecord:
        if _SHA256.fullmatch(request_bytes_sha256) is None:
            raise ValueError("remote replay requires a SHA-256 request identity")
        try:
            return self._records[request_bytes_sha256]
        except KeyError as exc:
            raise ValueError("offline remote cache miss; network fallback is forbidden") from exc


@dataclass(frozen=True)
class SearchLedgerEvent:
    sequence: int
    event_type: str
    subject_sha256: str
    payload_json: str
    event_id: str


class SearchLedger:
    def __init__(self) -> None:
        self._events: list[SearchLedgerEvent] = []

    @property
    def events(self) -> tuple[SearchLedgerEvent, ...]:
        return tuple(self._events)

    def record(self, event_type: str, subject_sha256: str, payload: object) -> SearchLedgerEvent:
        _require_text("search event type", event_type)
        if _SHA256.fullmatch(subject_sha256) is None:
            raise ValueError("search event subject must be SHA-256")
        reject_sealed_references(payload)
        encoded = canonical_json(payload)
        sequence = len(self._events) + 1
        event_id = "search_" + sha256(
            {
                "sequence": sequence,
                "event_type": event_type,
                "subject_sha256": subject_sha256,
                "payload_sha256": hashlib.sha256(encoded.encode()).hexdigest(),
            }
        )[:24]
        event = SearchLedgerEvent(sequence, event_type, subject_sha256, encoded, event_id)
        self._events.append(event)
        return event


class LabelFreeSearchController:
    def __init__(self, proposal_budget: int) -> None:
        if proposal_budget < 1:
            raise ValueError("proposal budget must be positive")
        self.proposal_budget = proposal_budget
        self.ledger = SearchLedger()
        self._proposals = 0

    def evaluate(
        self,
        identity: CandidateIdentity,
        *,
        known_family_sha256: tuple[str, ...] = (),
        known_expression_sha256: tuple[str, ...] = (),
        tombstoned_family_sha256: tuple[str, ...] = (),
    ) -> StaticDecision:
        if self._proposals >= self.proposal_budget:
            raise ValueError("label-free proposal budget exhausted")
        identity.validate()
        self._proposals += 1
        self.ledger.record(
            "PROPOSAL",
            identity.identity_sha256,
            {
                "proposal_number": self._proposals,
                "family_sha256": identity.plan.family_sha256,
                "expression_sha256": identity.expression.expression_sha256,
            },
        )
        decision = static_gate(
            identity,
            known_family_sha256=known_family_sha256,
            known_expression_sha256=known_expression_sha256,
            tombstoned_family_sha256=tombstoned_family_sha256,
        )
        self.ledger.record("STATIC_DECISION", identity.identity_sha256, asdict(decision))
        return decision
