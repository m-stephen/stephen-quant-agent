from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Literal

from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_snapshot_manifest

from .compiler import CompilerPolicy, ExpressionBlueprint, compile_hypothesis, default_blueprints
from .contracts import V2Hypothesis
from .diagnostics import (
    DiagnosticCode,
    DiagnosticObservation,
    DiagnosticPolicy,
    run_cheap_diagnostics,
)
from .failures import (
    EpochBudget,
    EpochPolicy,
    FailureCode,
    FailureStore,
    SearchAction,
    plan_next_epoch,
)
from .marginal import MarginalObservation, MarginalPolicy, evaluate_marginal_candidate
from .novelty import CandidateSignature, NoveltyCode, novelty_gate
from .proposals import ConstrainedProposalQueue
from .replay import (
    REPLAY_MANIFEST_VERSION,
    FrozenInteraction,
    ReferenceLibraryRecord,
    ReplayManifest,
    audit_replay_manifest,
)

ShadowDecision = Literal["REJECT", "REVISE", "STOP_FAMILY", "PROMOTE_FOR_FUTURE_VALIDATION"]


class ShadowLoopStopped(RuntimeError):
    """Raised before mutation when the operator kill switch is active."""


class ShadowBudgetError(RuntimeError):
    """Raised when a frozen shadow-mode budget would be exceeded."""


@dataclass(frozen=True)
class ShadowLoopConfig:
    version: str = "v2.0-shadow-1.0.0"
    seed: int = 42
    candidate_budget: int = 6
    compute_budget: int = 4
    token_budget: int = 1000
    statistical_trial_budget: int = 4
    dry_run: bool = False
    kill_switch: bool = False
    shadow_mode: bool = True
    sealed_windows: tuple[str, ...] = ("2025-validation", "2026-final-test")

    def validate(self) -> None:
        if not self.version.strip() or not self.shadow_mode:
            raise ValueError("V2 validation must run in versioned shadow mode")
        if any(
            value < 1
            for value in (
                self.candidate_budget,
                self.compute_budget,
                self.token_budget,
                self.statistical_trial_budget,
            )
        ):
            raise ValueError("shadow budgets must be positive")
        if set(self.sealed_windows) != {"2025-validation", "2026-final-test"}:
            raise ValueError("shadow validation must keep both holdout windows sealed")


DEFAULT_SHADOW_LOOP_CONFIG = ShadowLoopConfig()


@dataclass(frozen=True)
class ShadowCandidateDecision:
    candidate_id: str
    family_id: str
    decision: ShadowDecision
    reason_code: str
    trial_id: str | None
    parent_candidate_id: str | None = None


@dataclass(frozen=True)
class ShadowRunReport:
    method_version: str
    status: Literal["COMPLETED", "DRY_RUN"]
    shadow_mode: bool
    experiment_id: str
    snapshot_id: str
    snapshot_sha256: str
    code_version: str
    candidate_budget: int
    compute_budget: int
    token_budget: int
    statistical_trial_budget: int
    candidates_proposed: int
    empirical_trials_used: int
    compute_units_used: int
    token_units_used: int
    search_ledger_entries: int
    sealed_window_accesses: int
    model_requests_during_replay: int
    decisions: tuple[ShadowCandidateDecision, ...]
    replay_manifest_sha256: str | None
    replay_audit_passed: bool
    semantic_decision_sha256: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: Literal["zh", "en"]) -> str:
        if language == "zh":
            lines = [
                "# V2.0 Shadow Mode 运行报告",
                "",
                f"- 状态：**{self.status}**",
                f"- Experiment：`{self.experiment_id}`",
                f"- Snapshot：`{self.snapshot_id}` / `{self.snapshot_sha256}`",
                f"- 候选：{self.candidates_proposed}/{self.candidate_budget}",
                f"- 实证 Trial：{self.empirical_trials_used}/{self.statistical_trial_budget}",
                f"- 封存窗口访问：{self.sealed_window_accesses}",
                f"- Replay audit：{'通过' if self.replay_audit_passed else '未执行'}",
                "",
                "## 决策",
                "",
            ]
            lines.extend(
                f"- `{item.family_id}` / `{item.candidate_id}`：**{item.decision}** — `{item.reason_code}`"
                for item in self.decisions
            )
            lines.extend(
                [
                    "",
                    "## 边界",
                    "",
                    "本报告来自冻结 synthetic engineering fixture，仅验证研究系统能力；不构成 Alpha、收益或实盘建议。",
                ]
            )
            return "\n".join(lines) + "\n"
        lines = [
            "# V2.0 Shadow-Mode Run Report",
            "",
            f"- Status: **{self.status}**",
            f"- Experiment: `{self.experiment_id}`",
            f"- Snapshot: `{self.snapshot_id}` / `{self.snapshot_sha256}`",
            f"- Candidates: {self.candidates_proposed}/{self.candidate_budget}",
            f"- Empirical trials: {self.empirical_trials_used}/{self.statistical_trial_budget}",
            f"- Sealed-window accesses: {self.sealed_window_accesses}",
            f"- Replay audit: {'passed' if self.replay_audit_passed else 'not run'}",
            "",
            "## Decisions",
            "",
        ]
        lines.extend(
            f"- `{item.family_id}` / `{item.candidate_id}`: **{item.decision}** — `{item.reason_code}`"
            for item in self.decisions
        )
        lines.extend(
            [
                "",
                "## Boundary",
                "",
                "This report uses a frozen synthetic engineering fixture and validates research-system behavior only. It is not alpha, return evidence or live-trading advice.",
            ]
        )
        return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class ShadowArtifacts:
    json_path: Path
    zh_markdown_path: Path
    en_markdown_path: Path
    replay_manifest_path: Path | None


@dataclass
class _BudgetState:
    candidates: int = 0
    compute: int = 0
    tokens: int = 0
    trials: int = 0

    def candidate(self, config: ShadowLoopConfig, amount: int = 1) -> None:
        if self.candidates + amount > config.candidate_budget:
            raise ShadowBudgetError("candidate budget exhausted")
        self.candidates += amount

    def empirical(self, config: ShadowLoopConfig, tokens: int = 0) -> None:
        if self.compute + 1 > config.compute_budget:
            raise ShadowBudgetError("compute budget exhausted")
        if self.trials + 1 > config.statistical_trial_budget:
            raise ShadowBudgetError("statistical trial budget exhausted")
        if self.tokens + tokens > config.token_budget:
            raise ShadowBudgetError("token budget exhausted")
        self.compute += 1
        self.trials += 1
        self.tokens += tokens


def load_shadow_loop_config(path: str | Path) -> ShadowLoopConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    config = ShadowLoopConfig(
        version=str(payload["version"]),
        seed=int(payload.get("seed", 42)),
        candidate_budget=int(payload["budgets"]["candidate"]),
        compute_budget=int(payload["budgets"]["compute"]),
        token_budget=int(payload["budgets"]["token"]),
        statistical_trial_budget=int(payload["budgets"]["statistical_trial"]),
        dry_run=bool(payload.get("dry_run", False)),
        kill_switch=bool(payload.get("kill_switch", False)),
        shadow_mode=bool(payload.get("shadow_mode", True)),
        sealed_windows=tuple(payload["sealed_windows"]),
    )
    config.validate()
    return config


def _canonical(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def _record_search(
    registry: ExperimentRegistry,
    *,
    experiment_id: str,
    entry_type: str,
    subject_id: str,
    payload: dict[str, object],
    trial_id: str | None = None,
    parent_entry_id: str | None = None,
) -> str:
    encoded = _canonical(payload)
    entry_id, _ = registry.record_search_ledger_entry(
        experiment_id=experiment_id,
        entry_type=entry_type,
        subject_id=subject_id,
        payload_json=encoded,
        payload_sha256=hashlib.sha256(encoded.encode()).hexdigest(),
        empirical_exposure=trial_id is not None,
        inferential_trial_id=trial_id,
        parent_entry_id=parent_entry_id,
    )
    return entry_id


def _trial(
    registry: ExperimentRegistry,
    experiment_id: str,
    candidate_id: str,
    stage: str,
    config: ShadowLoopConfig,
    budget: _BudgetState,
) -> str:
    budget.empirical(config)
    trial_id, _ = registry.create_trial(
        TrialSpec(
            experiment_id=experiment_id,
            model_name=f"v2_shadow_{stage}",
            factor_set=candidate_id,
            hyperparams=_canonical({"stage": stage, "fixture": "synthetic_research_only"}),
            seed=config.seed,
            train_start="2022-01-04",
            train_end="2024-12-31",
            validation_start="2025-01-03",
            validation_end="2025-12-31",
            test_start="2026-01-05",
            test_end="2026-12-31",
        )
    )
    return trial_id


def _hypothesis(blueprint: ExpressionBlueprint) -> V2Hypothesis:
    inputs = {
        "flow_price_divergence": ("amount", "close", "net_inflow_amount"),
        "large_flow_surprise": ("amount", "large_buy_amount", "large_sell_amount"),
        "margin_financing": ("amount", "margin_financing_buy"),
    }[blueprint.event]
    return V2Hypothesis(
        statement=f"Frozen falsifiable hypothesis for {blueprint.event}",
        event=blueprint.event,
        contexts=("after_close",),
        mechanism="Point-in-time demand imbalance may precede price adjustment.",
        direction=1,
        expected_horizon="20d",
        universe="synthetic_dynamic_research_universe",
        regime="frozen_engineering_regimes",
        inputs=inputs,
        controls=("reference_portfolio",),
        falsification_criteria=("no_residual_value", "cost_erases_spread"),
        evidence_refs=("issue_36", "issue_49"),
        economic_complexity_budget=4,
        search_budget=2,
    )


def _diagnostic_rows(good: bool) -> tuple[DiagnosticObservation, ...]:
    rows: list[DiagnosticObservation] = []
    for date_index in range(3):
        for instrument_index in range(10):
            value = float(instrument_index - 4.5) + date_index * 0.05
            missing = not good and instrument_index < 4
            rows.append(
                DiagnosticObservation(
                    date=f"2024-02-{date_index + 2:02d}",
                    instrument=f"stock_{instrument_index:02d}",
                    value=None if missing else value,
                    forward_return=value * (0.001 if good else -0.001),
                    residual_return=value * (0.0008 if good else -0.0008),
                    stale_days=0 if good else 2,
                    regime="up" if date_index < 2 else "down",
                    industry="A" if instrument_index < 5 else "B",
                    style_exposures=(("size", float(instrument_index)),),
                    holding_returns=(value * 0.001, value * 0.0005),
                )
            )
    return tuple(rows)


def _marginal_rows() -> tuple[MarginalObservation, ...]:
    rows: list[MarginalObservation] = []
    for fold_index in range(2):
        for date_index in range(7):
            for instrument_index in range(10):
                reference = float(instrument_index) - 4.5
                orthogonal = (reference * reference - 8.25) / 8
                scale = 1 + 0.1 * ((date_index % 3) - 1)
                rows.append(
                    MarginalObservation(
                        fold_id=f"fold_{fold_index}",
                        phase="train" if date_index < 3 else "test",
                        date=f"202{3 + fold_index}-03-{date_index + 2:02d}",
                        instrument=f"f{fold_index}_stock_{instrument_index:02d}",
                        candidate_value=orthogonal,
                        reference_value=reference,
                        forward_return=scale * (0.003 * reference + 0.001 * orthogonal),
                        adv=50_000_000 + instrument_index * 1_000_000,
                    )
                )
    return tuple(rows)


def _semantic_digest(decisions: tuple[ShadowCandidateDecision, ...]) -> str:
    payload = [
        {
            "family": item.family_id,
            "decision": item.decision,
            "reason": item.reason_code,
            "parent": item.parent_candidate_id is not None,
        }
        for item in decisions
    ]
    return hashlib.sha256(_canonical(payload).encode()).hexdigest()


def _write_artifacts(
    output_dir: Path, report: ShadowRunReport, manifest: ReplayManifest | None
) -> ShadowArtifacts:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "v2-shadow-report.json"
    zh_path = output_dir / "v2-shadow-report.zh.md"
    en_path = output_dir / "v2-shadow-report.en.md"
    json_path.write_text(report.to_json() + "\n", encoding="utf-8")
    zh_path.write_text(report.to_markdown("zh"), encoding="utf-8")
    en_path.write_text(report.to_markdown("en"), encoding="utf-8")
    manifest_path = None
    if manifest is not None:
        manifest_path = output_dir / "v2-shadow-replay-manifest.json"
        envelope = {
            "manifest": json.loads(manifest.to_json()),
            "report": report.to_dict(),
            "report_sha256": hashlib.sha256(report.to_json().encode()).hexdigest(),
        }
        manifest_path.write_text(
            json.dumps(envelope, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return ShadowArtifacts(json_path, zh_path, en_path, manifest_path)


def run_shadow_validation(
    registry: ExperimentRegistry,
    output_dir: str | Path,
    *,
    code_version: str,
    config: ShadowLoopConfig = DEFAULT_SHADOW_LOOP_CONFIG,
) -> tuple[ShadowRunReport, ShadowArtifacts]:
    config.validate()
    if config.kill_switch:
        raise ShadowLoopStopped("V2 shadow loop stopped by operator kill switch")
    output = Path(output_dir)
    fixture_dir = output / "frozen-fixture"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    fixture_payload = {
        "fixture": "v2-shadow-engineering",
        "version": config.version,
        "research_window": ["2022-01-04", "2024-12-31"],
        "sealed_windows": config.sealed_windows,
    }
    (fixture_dir / "fixture.json").write_text(
        json.dumps(fixture_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    snapshot = build_snapshot_manifest(fixture_dir)
    snapshot_id = registry.register_snapshot(snapshot, "synthetic-v2", "M5 engineering fixture")
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            name="V2.0 shadow-mode engineering validation",
            hypothesis="The controlled research loop is auditable, replayable and stoppable.",
            dataset_snapshot_id=snapshot_id,
            code_version=code_version,
            search_space=_canonical(asdict(config)),
        )
    )
    budget = _BudgetState()
    queue = ConstrainedProposalQueue(default_blueprints(), config.candidate_budget)
    compiler_policy = CompilerPolicy(
        dataset_snapshot_id=snapshot_id,
        decision_context="after_close",
        field_coverage=(
            ("amount", 0.99),
            ("close", 0.99),
            ("net_inflow_amount", 0.95),
            ("large_buy_amount", 0.94),
            ("large_sell_amount", 0.94),
            ("margin_financing_buy", 0.90),
        ),
        maximum_complexity_nodes=64,
    )
    proposals = []
    proposal_entries: dict[str, str] = {}
    compiled = []
    for blueprint in default_blueprints():
        budget.candidate(config)
        proposal = queue.explore(_hypothesis(blueprint))
        family = compile_hypothesis(proposal.hypothesis, proposal.blueprint, compiler_policy)
        proposals.append(proposal)
        compiled.append(family)
        proposal_entries[proposal.proposal_id] = _record_search(
            registry,
            experiment_id=experiment_id,
            entry_type="PROPOSAL",
            subject_id=proposal.proposal_id,
            payload={
                "mode": proposal.mode,
                "hypothesis_id": proposal.hypothesis.hypothesis_id,
                "blueprint_id": proposal.blueprint.blueprint_id,
                "contract_ids": asdict(family.contract.ids),
            },
        )
    if config.dry_run:
        decisions = tuple(
            ShadowCandidateDecision(
                item.contract.ids.parameter_variant_id,
                item.contract.hypothesis.event,
                "REJECT",
                "DRY_RUN_NO_EMPIRICAL_ACCESS",
                None,
            )
            for item in compiled
        )
        report = ShadowRunReport(
            config.version,
            "DRY_RUN",
            True,
            experiment_id,
            snapshot_id,
            snapshot.snapshot_sha256,
            code_version,
            config.candidate_budget,
            config.compute_budget,
            config.token_budget,
            config.statistical_trial_budget,
            budget.candidates,
            0,
            0,
            0,
            registry.search_ledger_count(experiment_id),
            0,
            0,
            decisions,
            None,
            False,
            _semantic_digest(decisions),
        )
        return report, _write_artifacts(output, report, None)

    decisions_list: list[ShadowCandidateDecision] = []
    search_ids = list(proposal_entries.values())
    trial_ids: list[str] = []

    # Candidate 1: exact duplicate is rejected before expensive validation.
    duplicate_family = compiled[0]
    duplicate_id = duplicate_family.contract.ids.parameter_variant_id
    duplicate_trial = _trial(registry, experiment_id, duplicate_id, "novelty", config, budget)
    trial_ids.append(duplicate_trial)
    base_values = (-1.8, -1.1, -0.2, 0.1, 0.8, 0.7, 1.8, 1.7)
    control = (-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0)
    signature = CandidateSignature(
        duplicate_id,
        duplicate_family.contract.formula,
        base_values,
        control,
        (0.8, 0.2),
        ("flow", "price"),
    )
    peer = replace(signature, candidate_id="reference_duplicate")
    novelty = novelty_gate(signature, (peer,))
    if novelty.code != NoveltyCode.EXACT_AST_DUPLICATE:
        raise RuntimeError("frozen duplicate fixture did not trigger exact gate")
    registry.record_trial_result(
        duplicate_trial, _canonical({"decision": "REJECT", "reason": novelty.code.value})
    )
    decision = ShadowCandidateDecision(
        duplicate_id,
        duplicate_family.contract.hypothesis.event,
        "REJECT",
        novelty.code.value,
        duplicate_trial,
    )
    decisions_list.append(decision)
    search_ids.append(
        _record_search(
            registry,
            experiment_id=experiment_id,
            entry_type="DECISION",
            subject_id=duplicate_id,
            payload=asdict(decision),
            trial_id=duplicate_trial,
            parent_entry_id=proposal_entries[proposals[0].proposal_id],
        )
    )

    # Candidate 2: cheap diagnostics fail, producing a single-dimension revision.
    margin_family = compiled[2]
    margin_id = margin_family.contract.ids.parameter_variant_id
    margin_trial = _trial(registry, experiment_id, margin_id, "cheap_diagnostics", config, budget)
    trial_ids.append(margin_trial)
    failed_diagnostics = run_cheap_diagnostics(
        _diagnostic_rows(False),
        DiagnosticPolicy(expected_observations=30, minimum_coverage=0.80),
    )
    reason = next(code.value for code in failed_diagnostics.codes if code != DiagnosticCode.PASS)
    registry.record_trial_result(margin_trial, _canonical({"decision": "REVISE", "reason": reason}))
    revise = ShadowCandidateDecision(
        margin_id, margin_family.contract.hypothesis.event, "REVISE", reason, margin_trial
    )
    decisions_list.append(revise)
    revise_entry = _record_search(
        registry,
        experiment_id=experiment_id,
        entry_type="DECISION",
        subject_id=margin_id,
        payload=asdict(revise),
        trial_id=margin_trial,
        parent_entry_id=proposal_entries[proposals[2].proposal_id],
    )
    search_ids.append(revise_entry)
    budget.candidate(config)
    mutation = queue.mutate_lookback(proposals[2], parameter="lookback", value=60)
    revised_family = compile_hypothesis(mutation.hypothesis, mutation.blueprint, compiler_policy)
    revised_id = revised_family.contract.ids.parameter_variant_id
    search_ids.append(
        _record_search(
            registry,
            experiment_id=experiment_id,
            entry_type="MUTATION",
            subject_id=revised_id,
            payload={"parent": margin_id, "dimension": mutation.mutated_dimension},
            trial_id=margin_trial,
            parent_entry_id=revise_entry,
        )
    )
    revised_trial = _trial(registry, experiment_id, revised_id, "marginal_value", config, budget)
    trial_ids.append(revised_trial)
    good_diagnostics = run_cheap_diagnostics(
        _diagnostic_rows(True), DiagnosticPolicy(expected_observations=30)
    )
    if good_diagnostics.codes != (DiagnosticCode.PASS,):
        raise RuntimeError("frozen revised fixture did not pass cheap diagnostics")
    reference = ReferenceLibraryRecord(
        "reference_v1_8_21",
        "1.0.0",
        "exclude_bottom_decile_3m",
        "exp_v1_8_21_reference",
        snapshot_id,
        hashlib.sha256(b"v1.8.21-reference").hexdigest(),
        True,
        False,
    )
    marginal = evaluate_marginal_candidate(
        revised_id,
        _marginal_rows(),
        reference,
        complexity_cost=1,
        data_cost=1,
        policy=MarginalPolicy(residual_blend=0.75),
    )
    registry.record_trial_result(
        revised_trial,
        _canonical(
            {
                "decision": "PROMOTE_FOR_FUTURE_VALIDATION",
                "marginal_utility": marginal.marginal_utility,
                "alpha_court": "NOT_RUN_SHADOW_FIXTURE",
            }
        ),
    )
    promote = ShadowCandidateDecision(
        revised_id,
        revised_family.contract.hypothesis.event,
        "PROMOTE_FOR_FUTURE_VALIDATION",
        "POSITIVE_ORTHOGONAL_ENGINEERING_FIXTURE",
        revised_trial,
        margin_id,
    )
    decisions_list.append(promote)
    search_ids.append(
        _record_search(
            registry,
            experiment_id=experiment_id,
            entry_type="DECISION",
            subject_id=revised_id,
            payload=asdict(promote),
            trial_id=revised_trial,
        )
    )

    # Candidate 3: data failure exhausts its family and forces STOP_FAMILY next epoch.
    large_family = compiled[1]
    large_id = large_family.contract.ids.parameter_variant_id
    large_trial = _trial(registry, experiment_id, large_id, "family_exhaustion", config, budget)
    trial_ids.append(large_trial)
    failure_db = output / f"failure-{experiment_id}.sqlite3"
    failure_store = FailureStore(failure_db)
    epoch_policy = EpochPolicy("shadow-epoch-policy-1.0.0", exhaustion_threshold=1)
    epoch_budget = EpochBudget(((large_family.contract.hypothesis.event, 1),), 1, 1, 100, 1)
    failure_store.start_epoch("epoch_1", 1, epoch_policy, epoch_budget)
    failure_store.add_failure(
        epoch_id="epoch_1",
        family_id=large_family.contract.hypothesis.event,
        candidate_id=large_id,
        stage="cheap_diagnostics",
        code=FailureCode.LOW_COVERAGE,
        payload={"coverage": 0.60},
    )
    failure_store.close_epoch("epoch_1", {"sealed_window_accesses": 0})
    _, epoch_decisions = plan_next_epoch(
        failure_store,
        previous_epoch_id="epoch_1",
        next_epoch_id="epoch_2",
        next_epoch_index=2,
        families=(large_family.contract.hypothesis.event,),
        base_family_budget=1,
    )
    if epoch_decisions[0].action != SearchAction.STOP_FAMILY:
        raise RuntimeError("frozen exhausted family did not stop")
    registry.record_trial_result(
        large_trial,
        _canonical({"decision": "STOP_FAMILY", "reason": epoch_decisions[0].reason_code}),
    )
    stop = ShadowCandidateDecision(
        large_id,
        large_family.contract.hypothesis.event,
        "STOP_FAMILY",
        epoch_decisions[0].reason_code,
        large_trial,
    )
    decisions_list.append(stop)
    search_ids.append(
        _record_search(
            registry,
            experiment_id=experiment_id,
            entry_type="DECISION",
            subject_id=large_id,
            payload=asdict(stop),
            trial_id=large_trial,
            parent_entry_id=proposal_entries[proposals[1].proposal_id],
        )
    )

    decisions = tuple(decisions_list)
    allowed = {"REJECT", "REVISE", "STOP_FAMILY", "PROMOTE_FOR_FUTURE_VALIDATION"}
    if {item.decision for item in decisions} - allowed:
        raise RuntimeError("shadow loop emitted an unsupported decision")
    interaction = FrozenInteraction(
        "frozen-fixture",
        "no-live-model",
        "1",
        "v2-m5",
        ("typed-dsl-2",),
        _canonical({"hypotheses": [item.hypothesis.hypothesis_id for item in proposals]}),
        _canonical({"blueprints": [item.blueprint.blueprint_id for item in proposals]}),
        "[]",
        "2026-08-17T00:00:00+00:00",
    )
    config_json = _canonical(asdict(config))
    replay = ReplayManifest(
        REPLAY_MANIFEST_VERSION,
        code_version,
        snapshot_id,
        snapshot.snapshot_sha256,
        experiment_id,
        revised_family.contract,
        reference,
        config_json,
        config.seed,
        tuple(search_ids),
        tuple(trial_ids),
        (interaction,),
        config.sealed_windows,
    )
    replay_audit = audit_replay_manifest(registry, replay)
    if not replay_audit.passed or replay_audit.sealed_window_accesses != 0:
        raise RuntimeError("shadow replay provenance audit failed")
    report = ShadowRunReport(
        config.version,
        "COMPLETED",
        True,
        experiment_id,
        snapshot_id,
        snapshot.snapshot_sha256,
        code_version,
        config.candidate_budget,
        config.compute_budget,
        config.token_budget,
        config.statistical_trial_budget,
        budget.candidates,
        budget.trials,
        budget.compute,
        budget.tokens,
        registry.search_ledger_count(experiment_id),
        replay_audit.sealed_window_accesses,
        0,
        decisions,
        replay.manifest_sha256,
        replay_audit.passed,
        _semantic_digest(decisions),
    )
    artifacts = _write_artifacts(output, report, replay)
    for kind, path in (
        ("v2_shadow_report_json", artifacts.json_path),
        ("v2_shadow_report_zh", artifacts.zh_markdown_path),
        ("v2_shadow_report_en", artifacts.en_markdown_path),
        ("v2_shadow_replay_manifest", artifacts.replay_manifest_path),
    ):
        if path is not None:
            registry.register_artifact(
                trial_id=trial_ids[-1],
                kind=kind,
                path=str(path),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
    return report, artifacts


@dataclass(frozen=True)
class ShadowReplayVerification:
    verified: bool
    report_sha256: str
    semantic_decision_sha256: str
    model_requests: int
    sealed_window_accesses: int


def verify_shadow_replay(path: str | Path) -> ShadowReplayVerification:
    """Verify a frozen M5 envelope without model, network or data access."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    report = payload["report"]
    encoded_report = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False)
    report_sha = hashlib.sha256(encoded_report.encode()).hexdigest()
    if report_sha != payload["report_sha256"]:
        raise ValueError("shadow replay report hash mismatch")
    decisions = tuple(ShadowCandidateDecision(**item) for item in report["decisions"])
    semantic = _semantic_digest(decisions)
    if semantic != report["semantic_decision_sha256"]:
        raise ValueError("shadow replay semantic decision hash mismatch")
    return ShadowReplayVerification(
        True,
        report_sha,
        semantic,
        0,
        int(report["sealed_window_accesses"]),
    )
