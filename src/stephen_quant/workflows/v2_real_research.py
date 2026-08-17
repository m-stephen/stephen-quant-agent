from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.path_config import LocalPathConfig
from stephen_quant.v2.real_qd import (
    V21ReadinessArtifacts,
    V21ReadinessReport,
    load_v21_real_research_config,
    readiness_semantic_hash,
    resolve_discovery_config,
    run_v21_readiness,
)
from stephen_quant.v2.reliability import ReliabilityCalibration, run_reliability_calibration

from .automated_discovery import AutomatedDiscoveryRun, run_automated_discovery

V21_RESEARCH_VERSION = "v2.1-real-qd-research-loop-1.0.0"


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class V21ResearchManifest:
    method_version: str
    readiness_semantic_sha256: str
    readiness_decision: str
    discovery_decision: str
    experiment_id: str
    campaign_id: str
    generated_candidates: int
    unique_candidates: int
    reliability: ReliabilityCalibration
    sealed_windows_opened: bool
    artifacts: tuple[tuple[str, str], ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)


@dataclass(frozen=True)
class V21ResearchRun:
    readiness: V21ReadinessReport
    readiness_artifacts: V21ReadinessArtifacts
    discovery: AutomatedDiscoveryRun
    reliability: ReliabilityCalibration
    manifest: V21ResearchManifest
    manifest_path: Path


@dataclass(frozen=True)
class V21ReplayVerification:
    passed: bool
    checked_artifacts: int
    mismatches: tuple[str, ...]


def run_v21_real_research(
    paths: LocalPathConfig,
    config_path: str | Path,
    *,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    ingested_at: str,
) -> V21ResearchRun:
    config = load_v21_real_research_config(config_path)
    discovery_config = resolve_discovery_config(config, config_path)
    directory = Path(output_dir).expanduser().resolve()
    readiness, readiness_artifacts = run_v21_readiness(
        paths, config, directory / "readiness", ingested_at=ingested_at
    )
    if readiness.decision != "READY":
        raise ValueError("V2.1 research is blocked by the real-data readiness gate")
    alternative_paths = {
        key: str(path)
        for key, path in paths.paths.items()
        if key in {"qd_fund_flow_dir", "qd_auction_dir", "qd_margin_dir", "qd_industry_dir"}
    }
    discovery = run_automated_discovery(
        paths.choose("qd_daily_dir", None, "qd_daily_dir"),
        (),
        registry=registry,
        output_dir=directory / "discovery",
        code_version=code_version,
        config=discovery_config,
        alternative_paths=alternative_paths,
        dynamic_membership_path=readiness_artifacts.membership_jsonl_path,
        ingested_at=ingested_at,
    )
    if discovery.report.validation_window_opened or discovery.report.test_window_opened:
        raise ValueError("V2.1 research attempted to open a sealed window")
    reliability = run_reliability_calibration()
    reliability_path = directory / "reliability.json"
    reliability_path.write_text(
        json.dumps(reliability.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    artifact_paths = {
        "readiness": readiness_artifacts.json_path,
        "discovery": discovery.json_path,
        "schemas": discovery.schemas_path,
        "reliability": reliability_path,
    }
    manifest = V21ResearchManifest(
        V21_RESEARCH_VERSION,
        readiness_semantic_hash(readiness),
        readiness.decision,
        discovery.report.decision,
        discovery.report.experiment_id,
        discovery.report.campaign_id,
        discovery.report.generated_candidates,
        discovery.report.unique_candidates,
        reliability,
        False,
        tuple(sorted((name, _sha(path)) for name, path in artifact_paths.items())),
    )
    manifest_path = directory / "v2.1-replay-manifest.json"
    manifest_path.write_text(manifest.to_json() + "\n", encoding="utf-8", newline="\n")
    return V21ResearchRun(
        readiness,
        readiness_artifacts,
        discovery,
        reliability,
        manifest,
        manifest_path,
    )


def verify_v21_replay(source: str | Path) -> V21ReplayVerification:
    path = Path(source).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("method_version") != V21_RESEARCH_VERSION:
        raise ValueError("unsupported V2.1 replay manifest")
    if payload.get("sealed_windows_opened") is not False:
        raise ValueError("V2.1 replay manifest reports sealed-window access")
    root = path.parent
    mapping = {
        "readiness": root / "readiness" / "readiness.json",
        "discovery": root / "discovery" / "automated-discovery.json",
        "schemas": root / "discovery" / "generated-schemas.json",
        "reliability": root / "reliability.json",
    }
    expected = dict(payload.get("artifacts", ()))
    mismatches = tuple(
        name
        for name, artifact in mapping.items()
        if name not in expected or not artifact.is_file() or _sha(artifact) != expected[name]
    )
    return V21ReplayVerification(not mismatches, len(mapping), mismatches)
