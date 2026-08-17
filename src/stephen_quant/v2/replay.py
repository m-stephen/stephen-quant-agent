from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from stephen_quant.integrity.registry import ExperimentRegistry

from .contracts import V2FactorContract

REPLAY_MANIFEST_VERSION = "v2-replay-manifest-1.0.0"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True)
class FrozenInteraction:
    provider: str
    model: str
    model_version: str
    prompt_version: str
    tool_versions: tuple[str, ...]
    raw_input: str
    raw_output: str
    tool_calls_json: str
    fetched_at: str

    def validate(self) -> None:
        if any(
            not item.strip()
            for item in (
                self.provider,
                self.model,
                self.model_version,
                self.prompt_version,
                self.raw_input,
                self.raw_output,
                self.tool_calls_json,
                self.fetched_at,
            )
        ):
            raise ValueError("frozen interaction contains empty required data")
        try:
            json.loads(self.tool_calls_json)
        except json.JSONDecodeError as exc:
            raise ValueError("frozen interaction tool calls must be JSON") from exc

    @property
    def input_sha256(self) -> str:
        return _sha256(self.raw_input)

    @property
    def output_sha256(self) -> str:
        return _sha256(self.raw_output)


@dataclass(frozen=True)
class ReferenceLibraryRecord:
    library_id: str
    version: str
    portfolio_mapping: str
    source_experiment_id: str
    source_snapshot_id: str
    config_sha256: str
    research_only: bool
    validated_alpha: bool

    def validate(self) -> None:
        if any(
            not item.strip()
            for item in (
                self.library_id,
                self.version,
                self.portfolio_mapping,
                self.source_experiment_id,
                self.source_snapshot_id,
            )
        ) or len(self.config_sha256) != 64:
            raise ValueError("reference library provenance is incomplete")
        if self.research_only and self.validated_alpha:
            raise ValueError("research-only reference cannot be labelled validated alpha")


@dataclass(frozen=True)
class ReplayManifest:
    manifest_version: str
    code_commit: str
    dataset_snapshot_id: str
    dataset_snapshot_sha256: str
    experiment_id: str
    factor_contract: V2FactorContract
    reference_library: ReferenceLibraryRecord
    config_json: str
    seed: int
    search_ledger_entry_ids: tuple[str, ...]
    inferential_trial_ids: tuple[str, ...]
    frozen_interactions: tuple[FrozenInteraction, ...]
    sealed_windows: tuple[str, ...]

    def validate(self) -> None:
        if self.manifest_version != REPLAY_MANIFEST_VERSION:
            raise ValueError("unsupported replay manifest version")
        if any(
            not item.strip()
            for item in (self.code_commit, self.dataset_snapshot_id, self.experiment_id)
        ) or len(self.dataset_snapshot_sha256) != 64:
            raise ValueError("replay manifest core provenance is incomplete")
        self.factor_contract.validate()
        self.reference_library.validate()
        if self.factor_contract.dataset_snapshot_id != self.dataset_snapshot_id:
            raise ValueError("factor contract and replay dataset snapshots differ")
        try:
            json.loads(self.config_json)
        except json.JSONDecodeError as exc:
            raise ValueError("replay manifest config must be JSON") from exc
        if len(self.search_ledger_entry_ids) != len(set(self.search_ledger_entry_ids)):
            raise ValueError("replay search ledger IDs must be unique")
        if len(self.inferential_trial_ids) != len(set(self.inferential_trial_ids)):
            raise ValueError("replay inferential Trial IDs must be unique")
        if not self.sealed_windows or any(not item.strip() for item in self.sealed_windows):
            raise ValueError("replay manifest must declare sealed windows")
        for interaction in self.frozen_interactions:
            interaction.validate()

    @property
    def manifest_sha256(self) -> str:
        self.validate()
        payload = json.dumps(asdict(self), separators=(",", ":"), sort_keys=True)
        return _sha256(payload)

    def to_json(self) -> str:
        self.validate()
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)


@dataclass(frozen=True)
class ReplayAudit:
    manifest_sha256: str
    dataset_linked: bool
    search_entries_linked: bool
    inferential_trials_linked: bool
    sealed_window_accesses: int
    passed: bool


def audit_replay_manifest(
    registry: ExperimentRegistry, manifest: ReplayManifest
) -> ReplayAudit:
    """Fail closed unless a replay manifest links to persisted provenance."""

    manifest.validate()
    snapshot_id = registry.experiment_snapshot_id(manifest.experiment_id)
    dataset_linked = (
        snapshot_id == manifest.dataset_snapshot_id
        and registry.snapshot_sha256(snapshot_id) == manifest.dataset_snapshot_sha256
    )
    entries = {
        str(item["entry_id"]): item
        for item in registry.search_ledger_entries(manifest.experiment_id)
    }
    search_entries_linked = set(manifest.search_ledger_entry_ids) <= set(entries)
    inferential_trials_linked = True
    for trial_id in manifest.inferential_trial_ids:
        try:
            registry.trial_result(trial_id)
        except ValueError:
            inferential_trials_linked = False
            break
    linked_empirical = {
        str(item["inferential_trial_id"])
        for item in entries.values()
        if item["empirical_exposure"]
    }
    inferential_trials_linked = inferential_trials_linked and set(
        manifest.inferential_trial_ids
    ) <= linked_empirical
    passed = dataset_linked and search_entries_linked and inferential_trials_linked
    return ReplayAudit(
        manifest.manifest_sha256,
        dataset_linked,
        search_entries_linked,
        inferential_trials_linked,
        0,
        passed,
    )
