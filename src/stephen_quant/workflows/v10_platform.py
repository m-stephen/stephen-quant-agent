from __future__ import annotations

import hashlib
import json
from calendar import monthrange
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from stephen_quant.discovery.v10_generator import (
    V10CandidatePacket,
    generate_v10_candidates,
)
from stephen_quant.qmt.minute_features import build_minute_feature_mart
from stephen_quant.qmt.minute_warehouse import verify_minute_snapshot
from stephen_quant.qmt.models import QmtDataError

V10_VERSION = "v10.0-cross-source-alpha-platform-1.0.0"


@dataclass(frozen=True)
class V10PlatformReport:
    method_version: str
    minute_snapshot_id: str
    minute_feature_snapshot_id: str
    minute_feature_components: tuple[str, ...]
    feature_rows: int
    candidate_packet: V10CandidatePacket
    capital_cny: float
    sealed_from: str
    inferential_trial_delta: int
    decision: str
    next_action: str
    report_sha256: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True)

    def to_markdown(self, language: str) -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        return "\n".join(
            [
                "# V10.0 跨源自动 Alpha 平台" if zh else "# V10.0 Cross-source Automatic Alpha Platform",
                "",
                f"**{'结论' if zh else 'Decision'}: `{self.decision}`**",
                "",
                f"- {'分钟特征行' if zh else 'Minute feature rows'}: {self.feature_rows:,}",
                f"- {'候选策略快照' if zh else 'Candidate policy snapshot'}: `{self.candidate_packet.policy_sha256}`",
                f"- {'冻结候选' if zh else 'Frozen candidates'}: {len(self.candidate_packet.candidates)}",
                f"- {'读取标签' if zh else 'Labels read during generation'}: {self.candidate_packet.labels_read}",
                f"- {'本阶段推断 Trial 增量' if zh else 'Inferential trial delta in this stage'}: {self.inferential_trial_delta}",
                f"- {'资金' if zh else 'Capital'}: CNY {self.capital_cny:,.0f}",
                f"- {'封存起点' if zh else 'Sealed from'}: {self.sealed_from}",
                "",
                f"> {'下一步' if zh else 'Next'}: {self.next_action}",
                "",
            ]
        )


def run_v10_platform(
    warehouse_root: str | Path,
    *,
    minute_snapshot_id: str,
    feature_start: date,
    feature_end: date,
    candidate_budget: int,
    output_dir: str | Path,
    capital_cny: float = 3_000_000.0,
    reuse_verified_minute_snapshot: bool = False,
) -> V10PlatformReport:
    if feature_end >= date(2025, 1, 1):
        raise ValueError("V10 generation feature window must remain before sealed 2025-2026 data")
    if capital_cny != 3_000_000.0:
        raise ValueError("V10 acceptance run is frozen at CNY 3 million")
    if not reuse_verified_minute_snapshot:
        source_verification = verify_minute_snapshot(warehouse_root, minute_snapshot_id)
        if not source_verification["passed"]:
            raise QmtDataError("V10 source minute snapshot failed verification")
    feature_results: list[dict[str, object]] = []
    cursor = date(feature_start.year, feature_start.month, 1)
    while cursor <= feature_end:
        chunk_start = max(feature_start, cursor)
        chunk_end = min(
            feature_end,
            date(cursor.year, cursor.month, monthrange(cursor.year, cursor.month)[1]),
        )
        try:
            feature_results.append(
                build_minute_feature_mart(
                    warehouse_root,
                    minute_snapshot_id=minute_snapshot_id,
                    start_date=chunk_start,
                    end_date=chunk_end,
                    source_preverified=True,
                )
            )
        except QmtDataError as exc:
            if "no partitions" not in str(exc):
                raise
        cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
    if not feature_results:
        raise QmtDataError("V10 feature window contains no materialized minute data")
    feature_snapshot_ids = tuple(str(item["feature_snapshot_id"]) for item in feature_results)
    composite_feature_snapshot_id = hashlib.sha256(
        json.dumps(feature_snapshot_ids, separators=(",", ":")).encode()
    ).hexdigest()
    feature_rows = sum(int(item["row_count"]) for item in feature_results)
    packet = generate_v10_candidates(budget=candidate_budget)
    base = {
        "method_version": V10_VERSION,
        "minute_snapshot_id": minute_snapshot_id,
        "minute_feature_snapshot_id": composite_feature_snapshot_id,
        "minute_feature_components": feature_snapshot_ids,
        "feature_rows": feature_rows,
        "candidate_packet": asdict(packet),
        "capital_cny": capital_cny,
        "sealed_from": "2025-01-01",
        "inferential_trial_delta": 0,
        "decision": "READY_FOR_BOUNDED_EMPIRICAL_COURT",
        "next_action": "Evaluate every frozen candidate exactly once; retain PASS or NO_RELIABLE_ALPHA evidence.",
    }
    digest = hashlib.sha256(
        json.dumps(base, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    report = V10PlatformReport(
        V10_VERSION,
        minute_snapshot_id,
        composite_feature_snapshot_id,
        feature_snapshot_ids,
        feature_rows,
        packet,
        capital_cny,
        "2025-01-01",
        0,
        "READY_FOR_BOUNDED_EMPIRICAL_COURT",
        "Evaluate every frozen candidate exactly once; retain PASS or NO_RELIABLE_ALPHA evidence.",
        digest,
    )
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "v10-platform.json").write_text(report.to_json() + "\n", encoding="utf-8")
    (output / "v10-platform.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (output / "v10-platform.en.md").write_text(report.to_markdown("en"), encoding="utf-8")
    return report
