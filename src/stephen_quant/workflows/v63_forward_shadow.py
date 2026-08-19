from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from stephen_quant.discovery.forward_shadow_v2 import (
    FORWARD_SHADOW_VERSION,
    ForwardShadowProtocol,
    ForwardShadowSummary,
    summarize_forward_shadow,
)

V63_VERSION = "v6.3-forward-shadow-1.0.0"


@dataclass(frozen=True)
class V63Report:
    method_version: str
    shadow_version: str
    minimum_new_common_sessions: int
    protocol_id: str | None
    summary: ForwardShadowSummary | None
    tuning_from_forward_window: bool
    inferential_trial_delta: int
    decision: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        lines = [
            "# V6.3 Append-only 前向影子验证" if zh else "# V6.3 Append-only Forward Shadow",
            "",
            f"**{'结论' if zh else 'Decision'}: `{self.decision}`**",
            "",
            f"- Protocol: `{self.protocol_id or 'not-frozen'}`",
            f"- Minimum new common sessions: {self.minimum_new_common_sessions}",
            f"- Tuning from forward window: {self.tuning_from_forward_window}",
            f"- Trial delta: {self.inferential_trial_delta}",
            "",
        ]
        if self.summary is not None:
            lines.extend(
                [
                    f"- Observed sessions: {self.summary.sessions}",
                    f"- First/last: {self.summary.first_session} / {self.summary.last_session}",
                    "",
                ]
            )
        return "\n".join(lines)


def _load_protocol(path: str | Path) -> ForwardShadowProtocol:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("forward protocol must be a JSON object")
    payload = dict(payload)
    payload["required_sources"] = tuple(payload["required_sources"])
    return ForwardShadowProtocol(**payload)


def run_v63_forward_shadow(
    output_dir: str | Path,
    *,
    protocol_path: str | Path | None = None,
    ledger_path: str | Path | None = None,
) -> V63Report:
    if protocol_path is None and ledger_path is not None:
        raise ValueError("forward ledger requires its frozen protocol")
    if protocol_path is None:
        protocol = None
        summary = None
        decision = "READY_FOR_FORWARD_PROTOCOL"
        minimum = 25
    else:
        protocol = _load_protocol(protocol_path)
        source = ledger_path or Path(output_dir) / "nonexistent-forward-ledger.jsonl"
        summary = summarize_forward_shadow(source, protocol)
        decision = summary.decision
        minimum = protocol.minimum_new_sessions
    report = V63Report(
        V63_VERSION,
        FORWARD_SHADOW_VERSION,
        minimum,
        None if protocol is None else protocol.protocol_id,
        summary,
        False,
        0,
        decision,
    )
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "v6.3-forward-shadow.json").write_text(report.to_json() + "\n", encoding="utf-8")
    (output / "v6.3-forward-shadow.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (output / "v6.3-forward-shadow.en.md").write_text(report.to_markdown("en"), encoding="utf-8")
    return report
