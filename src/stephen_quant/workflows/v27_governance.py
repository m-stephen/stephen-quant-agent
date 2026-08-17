from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from stephen_quant.v2.failures import (
    EpochBudget,
    EpochPolicy,
    FailureCode,
    FailureStore,
    FamilySignature,
    VariantSignature,
    WindowState,
)
from stephen_quant.v2.firewall import (
    FIREWALL_VERSION,
    BoundedResearchManifest,
    decision_hash_without_sealed_data,
)

V27_M0_CONFIG_VERSION = "2.7-m0.1"
V27_M0_METHOD_VERSION = "v2.7-governance-reset-1.0.0"
V27_M0_REPLAY_VERSION = "v2.7-governance-replay-1.0.0"


def _canonical(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha(value: object) -> str:
    return _sha_bytes(_canonical(value).encode())


@dataclass(frozen=True)
class V27M0Config:
    config_version: str
    issue_number: int
    v26_config: str
    authority: str
    recorded_at: str
    prior_evidence_sha256: str
    prior_inferential_trials: int
    family: FamilySignature
    rejected_expression_family: str
    rejected_primary_horizon: int

    def validate(self) -> None:
        if self.config_version != V27_M0_CONFIG_VERSION or self.issue_number != 67:
            raise ValueError("V2.7 M0 config version or authority issue differs from contract")
        if any(
            not value.strip()
            for value in (
                self.v26_config,
                self.authority,
                self.recorded_at,
                self.rejected_expression_family,
            )
        ):
            raise ValueError("V2.7 M0 config has empty required data")
        if len(self.prior_evidence_sha256) != 64 or self.prior_inferential_trials != 48:
            raise ValueError("V2.7 M0 must preserve the frozen V2.6 evidence and 48 trials")
        if self.rejected_primary_horizon < 1:
            raise ValueError("V2.7 M0 rejected horizon must be positive")
        self.family.validate()

    @property
    def sha256(self) -> str:
        self.validate()
        return _sha(asdict(self))


@dataclass(frozen=True)
class V27M0Report:
    method_version: str
    decision: str
    issue_number: int
    config_sha256: str
    prior_evidence_sha256: str
    family_sha256: str
    tombstone_id: str
    failure_node_ids: tuple[str, ...]
    rejected_variant_decision: str
    changed_variant_decision: str
    distinct_mechanism_decision: str
    window_states: tuple[tuple[str, str], ...]
    prior_inferential_trials: int
    new_inferential_trials: int
    cumulative_inferential_trials: int
    remote_model_requests: int
    consumed_window_accesses: int
    sealed_window_accesses: int
    directory_enumerations: int
    governance_decision_sha256: str
    live_trading_authorized: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class V27M0Artifacts:
    json_path: Path
    markdown_en_path: Path
    markdown_zh_path: Path
    replay_manifest_path: Path


@dataclass(frozen=True)
class V27M0ReplayVerification:
    passed: bool
    checked_artifacts: int
    mismatches: tuple[str, ...]


def load_v27_m0_config(path: str | Path) -> V27M0Config:
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    family = FamilySignature(
        mechanism_id=str(payload["family"]["mechanism_id"]),
        data_semantics=tuple(str(value) for value in payload["family"]["data_semantics"]),
        information_set=tuple(str(value) for value in payload["family"]["information_set"]),
        economic_claim=str(payload["family"]["economic_claim"]),
        signal_direction=str(payload["family"]["signal_direction"]),
    )
    config = V27M0Config(
        config_version=str(payload["config_version"]),
        issue_number=int(payload["issue_number"]),
        v26_config=str(payload["v26_config"]),
        authority=str(payload["authority"]),
        recorded_at=str(payload["recorded_at"]),
        prior_evidence_sha256=str(payload["prior_evidence_sha256"]),
        prior_inferential_trials=int(payload["prior_inferential_trials"]),
        family=family,
        rejected_expression_family=str(payload["rejected_expression_family"]),
        rejected_primary_horizon=int(payload["rejected_primary_horizon"]),
    )
    config.validate()
    v26_path = source.parent / config.v26_config
    v26 = json.loads(v26_path.read_text(encoding="utf-8"))
    if int(v26["prior_trial_count"]) + 1 != config.prior_inferential_trials:
        raise ValueError("V2.7 M0 trial baseline differs from V2.6")
    if str(v26["prior_evidence_sha256"]) != config.prior_evidence_sha256:
        raise ValueError("V2.7 M0 prior evidence hash differs from V2.6")
    return config


def _variant(config: V27M0Config, *, horizon: int, policy: str) -> VariantSignature:
    return VariantSignature(
        family=config.family,
        expression_family=config.rejected_expression_family,
        primary_horizon=horizon,
        secondary_horizon=None,
        transformation_lineage=("raw", "momentum_adv_residual", "top_k"),
        portfolio_wrapper="top_k_long_only",
        policy_wrapper=policy,
    )


def _distinct_variant(config: V27M0Config) -> VariantSignature:
    family = FamilySignature(
        mechanism_id="margin_demand_shock",
        data_semantics=("margin_balance_change", "price_confirmation"),
        information_set=("prior_close", "published_margin_balance"),
        economic_claim="unexpected financing demand predicts short-horizon continuation",
        signal_direction="positive",
    )
    return VariantSignature(
        family=family,
        expression_family="margin_demand_shock_preregistered",
        primary_horizon=5,
        secondary_horizon=None,
        transformation_lineage=("raw", "cross_sectional_rank"),
        portfolio_wrapper="research_only_unallocated",
        policy_wrapper="no_regime_wrapper",
    )


def run_v27_m0_governance(
    config_path: str | Path,
    *,
    failure_store_path: str | Path,
    output_dir: str | Path,
) -> tuple[V27M0Report, V27M0Artifacts]:
    config = load_v27_m0_config(config_path)
    store = FailureStore(Path(failure_store_path))
    policy = EpochPolicy("v2.7-m0-stop-policy-1.0.0", exhaustion_threshold=1)
    budget = EpochBudget(
        ((config.family.mechanism_id, 0),),
        candidate_budget=0,
        compute_budget=0,
        token_budget=0,
        statistical_trial_budget=0,
    )
    store.start_epoch("v2.7-m0", 27, policy, budget)
    codes = (
        FailureCode.TEMPORAL_NON_GENERALIZATION,
        FailureCode.PLACEBO_FAILURE_OOS,
        FailureCode.RETURN_CONCENTRATION,
        FailureCode.DSR_FAILURE,
        FailureCode.POLICY_OVERFIT_RISK,
    )
    failures = tuple(
        store.add_failure(
            epoch_id="v2.7-m0",
            family_id=config.family.mechanism_id,
            candidate_id="flow_confirmation_20_20d__risk_off_cash",
            stage="independent_validation",
            code=code,
            payload={
                "decision": "VALIDATION_FAIL_STOP",
                "source_evidence_sha256": config.prior_evidence_sha256,
                "granularity": "FROZEN_GATE_ONLY",
            },
        )
        for code in codes
    )
    tombstone = store.record_family_tombstone(
        config.family,
        reason_code="VALIDATION_FAIL_STOP",
        authority=config.authority,
        source_failure_node_ids=tuple(node.node_id for node in failures),
        recorded_at=config.recorded_at,
    )
    consumed = store.record_window_state(
        window_id="2025-validation",
        previous_state=WindowState.SEALED_VALIDATION,
        new_state=WindowState.CONSUMED_VALIDATION,
        authority=config.authority,
        source_artifact_sha256=config.prior_evidence_sha256,
        recorded_at=config.recorded_at,
    )
    sealed = store.record_window_state(
        window_id="2026-final-test",
        previous_state=WindowState.SEALED_FINAL_TEST,
        new_state=WindowState.SEALED_FINAL_TEST,
        authority=config.authority,
        source_artifact_sha256=config.prior_evidence_sha256,
        recorded_at=config.recorded_at,
    )
    rejected = store.tombstone_decision(
        _variant(config, horizon=config.rejected_primary_horizon, policy="risk_off_cash")
    )
    changed = store.tombstone_decision(
        _variant(config, horizon=10, policy="threshold_and_top_k_changed")
    )
    distinct = store.tombstone_decision(_distinct_variant(config))
    store.close_epoch(
        "v2.7-m0",
        {
            "status": "FORMAL_STOP_RECORDED",
            "new_inferential_trials": 0,
            "consumed_window_accesses": 0,
            "sealed_window_accesses": 0,
            "remote_model_requests": 0,
        },
    )
    empty_manifest = BoundedResearchManifest(FIREWALL_VERSION, "2024-12-31", ())
    governance_payload = {
        "family_sha256": config.family.sha256,
        "tombstone_id": tombstone.tombstone_id,
        "failure_node_ids": [node.node_id for node in failures],
        "window_events": [consumed.payload_sha256, sealed.payload_sha256],
        "prior_inferential_trials": config.prior_inferential_trials,
        "new_inferential_trials": 0,
    }
    decision_sha = decision_hash_without_sealed_data(empty_manifest, governance_payload)
    report = V27M0Report(
        method_version=V27_M0_METHOD_VERSION,
        decision="M0_GOVERNANCE_READY",
        issue_number=config.issue_number,
        config_sha256=config.sha256,
        prior_evidence_sha256=config.prior_evidence_sha256,
        family_sha256=config.family.sha256,
        tombstone_id=tombstone.tombstone_id,
        failure_node_ids=tuple(node.node_id for node in failures),
        rejected_variant_decision=rejected.action.value,
        changed_variant_decision=changed.action.value,
        distinct_mechanism_decision=distinct.action.value,
        window_states=(
            ("2025-validation", consumed.new_state.value),
            ("2026-final-test", sealed.new_state.value),
        ),
        prior_inferential_trials=config.prior_inferential_trials,
        new_inferential_trials=0,
        cumulative_inferential_trials=config.prior_inferential_trials,
        remote_model_requests=0,
        consumed_window_accesses=0,
        sealed_window_accesses=0,
        directory_enumerations=0,
        governance_decision_sha256=decision_sha,
        live_trading_authorized=False,
    )
    artifacts = write_v27_m0_artifacts(report, output_dir)
    return report, artifacts


def _markdown(report: V27M0Report, *, zh: bool) -> str:
    title = "# V2.7 M0 治理重置结果" if zh else "# V2.7 M0 Governance Reset Result"
    rows = [
        title,
        "",
        f"- {'结论' if zh else 'Decision'}: **{report.decision}**",
        f"- {'旧 family' if zh else 'Rejected family'}: `{report.rejected_variant_decision}`",
        f"- {'变体后代' if zh else 'Changed descendant'}: `{report.changed_variant_decision}`",
        f"- {'新机制 fixture' if zh else 'Distinct mechanism fixture'}: `{report.distinct_mechanism_decision}`",
        f"- {'累计 inferential trials' if zh else 'Cumulative inferential trials'}: {report.cumulative_inferential_trials}",
        f"- {'新增 inferential trials' if zh else 'New inferential trials'}: {report.new_inferential_trials}",
        f"- {'2025 状态' if zh else '2025 state'}: `CONSUMED_VALIDATION`",
        f"- {'2026 状态' if zh else '2026 state'}: `SEALED_FINAL_TEST`",
        f"- {'2025/2026 未授权访问' if zh else 'Unauthorized 2025/2026 accesses'}: 0 / 0",
        f"- {'远程模型请求' if zh else 'Remote model requests'}: 0",
        f"- {'实盘授权' if zh else 'Live trading authorized'}: false",
        "",
        (
            "> 本阶段只固化失败与治理边界，不读取行情、不产生收益反馈，也不授权新因子搜索。"
            if zh
            else "> This phase freezes failure and governance only; it reads no market data, creates no return feedback, and does not authorize factor search."
        ),
        "",
    ]
    return "\n".join(rows)


def write_v27_m0_artifacts(report: V27M0Report, output_dir: str | Path) -> V27M0Artifacts:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "v2.7-m0-governance.json"
    en_path = output / "v2.7-m0-governance.en.md"
    zh_path = output / "v2.7-m0-governance.zh.md"
    json_path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    en_path.write_text(_markdown(report, zh=False), encoding="utf-8")
    zh_path.write_text(_markdown(report, zh=True), encoding="utf-8")
    paths = (json_path, en_path, zh_path)
    replay_path = output / "v2.7-m0-replay-manifest.json"
    replay_path.write_text(
        json.dumps(
            {
                "replay_version": V27_M0_REPLAY_VERSION,
                "artifacts": {path.name: _sha_bytes(path.read_bytes()) for path in paths},
                "governance_decision_sha256": report.governance_decision_sha256,
                "remote_model_requests": 0,
                "consumed_window_accesses": 0,
                "sealed_window_accesses": 0,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return V27M0Artifacts(json_path, en_path, zh_path, replay_path)


def verify_v27_m0_replay(path: str | Path) -> V27M0ReplayVerification:
    manifest_path = Path(path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("replay_version") != V27_M0_REPLAY_VERSION:
        raise ValueError("unsupported V2.7 M0 replay manifest")
    if any(
        int(payload.get(key, -1)) != 0
        for key in (
            "remote_model_requests",
            "consumed_window_accesses",
            "sealed_window_accesses",
        )
    ):
        raise ValueError("V2.7 M0 replay reports forbidden access")
    mismatches = tuple(
        name
        for name, expected in payload["artifacts"].items()
        if not (manifest_path.parent / name).is_file()
        or _sha_bytes((manifest_path.parent / name).read_bytes()) != expected
    )
    return V27M0ReplayVerification(not mismatches, len(payload["artifacts"]), mismatches)
