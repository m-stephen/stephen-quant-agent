from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path

V27_M1_CONFIG_VERSION = "2.7-m1.1"
V27_M1_METHOD_VERSION = "v2.7-pit-readiness-1.0.0"
V27_M1_REPLAY_VERSION = "v2.7-pit-readiness-replay-1.0.0"


def _canonical(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode()


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class PITReadinessStatus(str, Enum):
    READY_FOR_M2_CONTROLS = "READY_FOR_M2_CONTROLS"
    CONDITIONAL_READY = "CONDITIONAL_READY"
    DATA_NOT_RESEARCH_READY = "DATA_NOT_RESEARCH_READY"


@dataclass(frozen=True)
class PITSourceContract:
    source: str
    fields: tuple[str, ...]
    evidence_start: str | None
    evidence_end: str | None
    evidence_snapshot_sha256: str | None
    effective_time_policy: str
    availability_policy: str
    revision_policy: str
    survivorship_policy: str
    status: PITReadinessStatus
    authorized_uses: tuple[str, ...]
    blockers: tuple[str, ...]

    def validate(self) -> None:
        if not self.source or not self.fields or not self.effective_time_policy:
            raise ValueError("PIT source contract has empty required fields")
        if (self.evidence_start is None) != (self.evidence_end is None):
            raise ValueError("PIT evidence bounds must both be present or absent")
        if self.evidence_start and self.evidence_end and self.evidence_start > self.evidence_end:
            raise ValueError("PIT evidence bounds are reversed")
        if self.evidence_snapshot_sha256 is not None and len(self.evidence_snapshot_sha256) != 64:
            raise ValueError("PIT evidence snapshot must be SHA-256")
        if self.status is PITReadinessStatus.READY_FOR_M2_CONTROLS and (
            not self.authorized_uses or self.blockers
        ):
            raise ValueError("ready PIT source must have uses and no blockers")
        if self.status is PITReadinessStatus.DATA_NOT_RESEARCH_READY and self.authorized_uses:
            raise ValueError("blocked PIT source cannot authorize research use")
        if self.source == "qd_industry_index" and any(
            "membership" in value for value in self.authorized_uses
        ):
            raise ValueError("industry indices cannot authorize stock membership")


@dataclass(frozen=True)
class V27M1Config:
    config_version: str
    issue_number: int
    parent_issue_number: int
    authority: str
    research_window: tuple[str, str]
    consumed_validation_window: tuple[str, str]
    sealed_final_test_window: tuple[str, str]
    prior_readiness_artifact_sha256: str
    prior_source_snapshot_sha256: str
    prior_inferential_trials: int
    contracts: tuple[PITSourceContract, ...]

    def validate(self) -> None:
        if (
            self.config_version != V27_M1_CONFIG_VERSION
            or self.issue_number != 71
            or self.parent_issue_number != 67
        ):
            raise ValueError("V2.7 M1 config differs from Issues #67/#71")
        if len(self.prior_readiness_artifact_sha256) != 64:
            raise ValueError("prior readiness artifact hash must be SHA-256")
        if len(self.prior_source_snapshot_sha256) != 64:
            raise ValueError("prior source snapshot hash must be SHA-256")
        if self.prior_inferential_trials != 48:
            raise ValueError("M1 must preserve the frozen 48-trial baseline")
        if not self.authority or self.research_window[1] >= self.consumed_validation_window[0]:
            raise ValueError("M1 windows or authority are invalid")
        if self.consumed_validation_window[1] >= self.sealed_final_test_window[0]:
            raise ValueError("M1 validation and final-test windows overlap")
        names = [item.source for item in self.contracts]
        if len(names) != len(set(names)) or not names:
            raise ValueError("M1 source contracts must be non-empty and unique")
        for item in self.contracts:
            item.validate()
        required = {"qd_daily", "qd_industry_index", "stock_industry_membership", "corporate_actions", "expectation_revisions"}
        if not required <= set(names):
            raise ValueError("M1 omits a mandatory fail-closed source contract")

    @property
    def sha256(self) -> str:
        self.validate()
        return _sha_bytes(_canonical(asdict(self)))


@dataclass(frozen=True)
class V27M1Report:
    method_version: str
    decision: str
    issue_number: int
    config_sha256: str
    research_window: tuple[str, str]
    prior_source_snapshot_sha256: str
    contracts: tuple[PITSourceContract, ...]
    m2_authorized_controls: tuple[str, ...]
    blocked_capabilities: tuple[str, ...]
    prior_inferential_trials: int
    new_inferential_trials: int
    cumulative_inferential_trials: int
    remote_model_requests: int
    consumed_window_accesses: int
    sealed_window_accesses: int
    directory_enumerations: int
    return_observations: int
    live_trading_authorized: bool
    decision_sha256: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class V27M1Artifacts:
    json_path: Path
    markdown_en_path: Path
    markdown_zh_path: Path
    replay_manifest_path: Path


@dataclass(frozen=True)
class V27M1ReplayVerification:
    passed: bool
    checked_artifacts: int
    mismatches: tuple[str, ...]


def load_v27_m1_config(path: str | Path) -> V27M1Config:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    contracts = tuple(
        PITSourceContract(
            source=str(item["source"]),
            fields=tuple(str(value) for value in item["fields"]),
            evidence_start=item.get("evidence_start"),
            evidence_end=item.get("evidence_end"),
            evidence_snapshot_sha256=item.get("evidence_snapshot_sha256"),
            effective_time_policy=str(item["effective_time_policy"]),
            availability_policy=str(item["availability_policy"]),
            revision_policy=str(item["revision_policy"]),
            survivorship_policy=str(item["survivorship_policy"]),
            status=PITReadinessStatus(str(item["status"])),
            authorized_uses=tuple(str(value) for value in item["authorized_uses"]),
            blockers=tuple(str(value) for value in item["blockers"]),
        )
        for item in payload["contracts"]
    )
    config = V27M1Config(
        config_version=str(payload["config_version"]),
        issue_number=int(payload["issue_number"]),
        parent_issue_number=int(payload["parent_issue_number"]),
        authority=str(payload["authority"]),
        research_window=tuple(payload["research_window"]),  # type: ignore[arg-type]
        consumed_validation_window=tuple(payload["consumed_validation_window"]),  # type: ignore[arg-type]
        sealed_final_test_window=tuple(payload["sealed_final_test_window"]),  # type: ignore[arg-type]
        prior_readiness_artifact_sha256=str(payload["prior_readiness_artifact_sha256"]),
        prior_source_snapshot_sha256=str(payload["prior_source_snapshot_sha256"]),
        prior_inferential_trials=int(payload["prior_inferential_trials"]),
        contracts=contracts,
    )
    config.validate()
    return config


def run_v27_m1_pit_readiness(
    config_path: str | Path, output_dir: str | Path
) -> tuple[V27M1Report, V27M1Artifacts]:
    config = load_v27_m1_config(config_path)
    ready = tuple(
        use
        for contract in config.contracts
        if contract.status is PITReadinessStatus.READY_FOR_M2_CONTROLS
        for use in contract.authorized_uses
    )
    blocked = tuple(
        contract.source
        for contract in config.contracts
        if contract.status is PITReadinessStatus.DATA_NOT_RESEARCH_READY
    )
    decision = "PARTIAL_M2_AUTHORIZATION" if ready and blocked else "DATA_NOT_RESEARCH_READY"
    core = {
        "config_sha256": config.sha256,
        "decision": decision,
        "m2_authorized_controls": ready,
        "blocked_capabilities": blocked,
        "new_inferential_trials": 0,
        "consumed_window_accesses": 0,
        "sealed_window_accesses": 0,
    }
    report = V27M1Report(
        method_version=V27_M1_METHOD_VERSION,
        decision=decision,
        issue_number=config.issue_number,
        config_sha256=config.sha256,
        research_window=config.research_window,
        prior_source_snapshot_sha256=config.prior_source_snapshot_sha256,
        contracts=config.contracts,
        m2_authorized_controls=ready,
        blocked_capabilities=blocked,
        prior_inferential_trials=config.prior_inferential_trials,
        new_inferential_trials=0,
        cumulative_inferential_trials=config.prior_inferential_trials,
        remote_model_requests=0,
        consumed_window_accesses=0,
        sealed_window_accesses=0,
        directory_enumerations=0,
        return_observations=0,
        live_trading_authorized=False,
        decision_sha256=_sha_bytes(_canonical(core)),
    )
    return report, write_v27_m1_artifacts(report, output_dir)


def _markdown(report: V27M1Report, *, zh: bool) -> str:
    rows = [
        "# V2.7 M1 数据时点就绪审计" if zh else "# V2.7 M1 Point-in-Time Readiness Audit",
        "",
        f"- {'结论' if zh else 'Decision'}: **{report.decision}**",
        f"- {'研究窗口' if zh else 'Research window'}: {report.research_window[0]} — {report.research_window[1]}",
        f"- {'新增推断试验' if zh else 'New inferential trials'}: 0",
        f"- {'2025/2026 访问' if zh else '2025/2026 accesses'}: 0 / 0",
        f"- {'收益观测' if zh else 'Return observations'}: 0",
        "",
        "## 数据源矩阵" if zh else "## Source matrix",
        "",
        "| 数据源 | PIT 证据期 | 修订规则 | 幸存者偏差 | 状态 |" if zh else "| Source | PIT evidence | Revision policy | Survivorship | Status |",
        "|---|---|---|---|---|",
    ]
    for item in report.contracts:
        period = f"{item.evidence_start} — {item.evidence_end}" if item.evidence_start else "—"
        rows.append(
            f"| {item.source} | {period} | {item.revision_policy} | {item.survivorship_policy} | `{item.status.value}` |"
        )
    rows.extend(["", "## M2", ""])
    if zh:
        rows.append("仅授权价格型控制：" + "、".join(report.m2_authorized_controls) + "。")
        rows.append("以下能力继续封锁：" + "、".join(report.blocked_capabilities) + "。")
        rows.append("\n> 行业指数不等于股票历史行业归属；用户声明的可见时间不等于供应商级 PIT 证明。")
    else:
        rows.append("Authorized price-derived controls only: " + ", ".join(report.m2_authorized_controls) + ".")
        rows.append("Blocked capabilities: " + ", ".join(report.blocked_capabilities) + ".")
        rows.append("\n> Industry indices are not historical stock membership; user-declared clocks are not vendor-grade PIT evidence.")
    rows.append("")
    return "\n".join(rows)


def write_v27_m1_artifacts(report: V27M1Report, output_dir: str | Path) -> V27M1Artifacts:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "v2.7-m1-pit-readiness.json"
    en_path = output / "v2.7-m1-pit-readiness.en.md"
    zh_path = output / "v2.7-m1-pit-readiness.zh.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    en_path.write_text(_markdown(report, zh=False), encoding="utf-8")
    zh_path.write_text(_markdown(report, zh=True), encoding="utf-8")
    paths = (json_path, en_path, zh_path)
    replay = output / "v2.7-m1-replay-manifest.json"
    replay.write_text(
        json.dumps(
            {
                "replay_version": V27_M1_REPLAY_VERSION,
                "artifacts": {path.name: _sha_bytes(path.read_bytes()) for path in paths},
                "decision_sha256": report.decision_sha256,
                "new_inferential_trials": 0,
                "remote_model_requests": 0,
                "consumed_window_accesses": 0,
                "sealed_window_accesses": 0,
                "directory_enumerations": 0,
                "return_observations": 0,
            },
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    return V27M1Artifacts(json_path, en_path, zh_path, replay)


def verify_v27_m1_replay(path: str | Path) -> V27M1ReplayVerification:
    manifest = Path(path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if payload.get("replay_version") != V27_M1_REPLAY_VERSION:
        raise ValueError("unsupported V2.7 M1 replay manifest")
    forbidden = (
        "new_inferential_trials",
        "remote_model_requests",
        "consumed_window_accesses",
        "sealed_window_accesses",
        "directory_enumerations",
        "return_observations",
    )
    if any(int(payload.get(key, -1)) != 0 for key in forbidden):
        raise ValueError("V2.7 M1 replay reports forbidden research activity")
    mismatches = tuple(
        name
        for name, expected in payload["artifacts"].items()
        if not (manifest.parent / name).is_file()
        or _sha_bytes((manifest.parent / name).read_bytes()) != expected
    )
    return V27M1ReplayVerification(not mismatches, len(payload["artifacts"]), mismatches)
