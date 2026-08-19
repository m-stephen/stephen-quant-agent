from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from stephen_quant.discovery.alpha_court_v2 import (
    AUTO_ALPHA_COURT_VERSION,
    DEFAULT_ALPHA_COURT_THRESHOLDS,
    AlphaCourtDecision,
    AlphaCourtEvidence,
    AlphaCourtThresholds,
    FrozenCourtProtocol,
    adjudicate_alpha_court,
)

V62_VERSION = "v6.2-auto-alpha-court-1.0.0"


@dataclass(frozen=True)
class V62Report:
    method_version: str
    court_version: str
    frozen_minimum_thresholds: AlphaCourtThresholds
    protocol_id: str | None
    adjudication: AlphaCourtDecision | None
    inferential_trial_delta: int
    decision: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        thresholds = self.frozen_minimum_thresholds
        lines = [
            "# V6.2 自动 Alpha Court" if zh else "# V6.2 Automatic Alpha Court",
            "",
            f"**{'结论' if zh else 'Decision'}: `{self.decision}`**",
            "",
            f"- Protocol: `{self.protocol_id or 'not-frozen'}`",
            f"- DSR minimum: {thresholds.minimum_dsr}",
            f"- PBO maximum: {thresholds.maximum_pbo}",
            f"- Signal placebo maximum: {thresholds.maximum_signal_placebo_p}",
            f"- Return placebo maximum: {thresholds.maximum_return_placebo_p}",
            f"- Minimum capacity: CNY {thresholds.minimum_capacity_cny:,.0f}",
            f"- Trial delta: {self.inferential_trial_delta}",
            "",
        ]
        if self.adjudication is not None:
            lines.append(f"- Failed gates: {', '.join(self.adjudication.failed_gates) or 'none'}")
            lines.append("")
        return "\n".join(lines)


def _load_protocol(path: str | Path) -> FrozenCourtProtocol:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("court protocol must be a JSON object")
    payload = dict(payload)
    if "thresholds" in payload:
        payload["thresholds"] = AlphaCourtThresholds(**payload["thresholds"])
    return FrozenCourtProtocol(**payload)


def _load_evidence(path: str | Path) -> AlphaCourtEvidence:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("court evidence must be a JSON object")
    return AlphaCourtEvidence(**payload)


def run_v62_auto_alpha_court(
    output_dir: str | Path,
    *,
    protocol_path: str | Path | None = None,
    evidence_path: str | Path | None = None,
) -> V62Report:
    if (protocol_path is None) != (evidence_path is None):
        raise ValueError("court protocol and evidence must be supplied together")
    if protocol_path is None:
        protocol = None
        decision = None
        status = "READY_FOR_FROZEN_PROTOCOL"
    else:
        protocol = _load_protocol(protocol_path)
        decision = adjudicate_alpha_court(protocol, _load_evidence(evidence_path))
        status = decision.decision
    report = V62Report(
        V62_VERSION,
        AUTO_ALPHA_COURT_VERSION,
        DEFAULT_ALPHA_COURT_THRESHOLDS,
        None if protocol is None else protocol.protocol_id,
        decision,
        0,
        status,
    )
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "v6.2-alpha-court.json").write_text(report.to_json() + "\n", encoding="utf-8")
    (output / "v6.2-alpha-court.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (output / "v6.2-alpha-court.en.md").write_text(report.to_markdown("en"), encoding="utf-8")
    return report
