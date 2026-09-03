from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from stephen_quant.discovery.mechanism_lineage import (
    FrozenProposalPacket,
    freeze_proposal_packet,
)
from stephen_quant.discovery.portfolio_native import PortfolioPolicy
from stephen_quant.discovery.proposal_generator import (
    GeneratedProposal,
    ProposalSpec,
    compile_proposal,
    generate_structural_proposals,
    merge_proposals,
)
from stephen_quant.discovery.search_calibration import (
    SearchCalibrationReport,
    run_search_calibration,
)

V90_VERSION = "v9.0-calibrated-portfolio-native-alpha-discovery-1.0.0"
V90_PRIOR_INFERENTIAL_TRIALS = 533
V90_DEFAULT_CONFIG = "configs/v9.0-alpha-discovery.json"


@dataclass(frozen=True)
class V90Config:
    discovery_start: str = "2015-01-01"
    discovery_end: str = "2017-12-31"
    validation_start: str = "2018-01-01"
    validation_end: str = "2018-12-31"
    frozen_test_start: str = "2019-01-01"
    frozen_test_end: str = "2019-12-31"
    confirmation_start: str = "2020-01-01"
    confirmation_end: str = "2021-12-31"
    stress_start: str = "2022-01-01"
    stress_end: str = "2024-12-31"
    sealed_start: str = "2025-01-01"
    empirical_budget: int = 50
    prior_inferential_trials: int = V90_PRIOR_INFERENTIAL_TRIALS
    min_dsr_probability: float = 0.95
    maximum_pbo: float = 0.05
    maximum_placebo_p_value: float = 0.05
    portfolio_policy: PortfolioPolicy = field(default_factory=PortfolioPolicy)

    def validate(self) -> None:
        boundaries = (
            self.discovery_start,
            self.discovery_end,
            self.validation_start,
            self.validation_end,
            self.frozen_test_start,
            self.frozen_test_end,
            self.confirmation_start,
            self.confirmation_end,
            self.stress_start,
            self.stress_end,
            self.sealed_start,
        )
        if tuple(sorted(boundaries)) != boundaries:
            raise ValueError("V9 temporal roles must be ordered and non-overlapping")
        if self.empirical_budget < 2 or self.prior_inferential_trials < 0:
            raise ValueError("invalid empirical or prior-trial budget")
        if not 0 < self.min_dsr_probability < 1:
            raise ValueError("invalid DSR gate")
        if not 0 <= self.maximum_pbo <= 1 or not 0 <= self.maximum_placebo_p_value <= 1:
            raise ValueError("invalid PBO/placebo gate")
        self.portfolio_policy.validate()


def load_v90_config(path: str | Path) -> tuple[V90Config, str, str]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("V9 config must be an object")
    roles = payload.get("time_roles")
    search = payload.get("search")
    court = payload.get("alpha_court")
    portfolio = payload.get("portfolio")
    snapshots = payload.get("warehouse_snapshots")
    if not all(isinstance(item, dict) for item in (roles, search, court, portfolio, snapshots)):
        raise TypeError("V9 config sections must be objects")

    def period(name: str) -> tuple[str, str]:
        value = roles.get(name)
        if not isinstance(value, list) or len(value) != 2:
            raise ValueError(f"V9 time role {name} must contain start and end")
        return str(value[0]), str(value[1])

    discovery = period("discovery")
    validation = period("validation")
    frozen_test = period("frozen_test")
    confirmation = period("confirmation")
    stress = period("stress")
    config = V90Config(
        discovery_start=discovery[0],
        discovery_end=discovery[1],
        validation_start=validation[0],
        validation_end=validation[1],
        frozen_test_start=frozen_test[0],
        frozen_test_end=frozen_test[1],
        confirmation_start=confirmation[0],
        confirmation_end=confirmation[1],
        stress_start=stress[0],
        stress_end=stress[1],
        sealed_start=str(roles.get("sealed_from")),
        empirical_budget=int(search.get("empirical_budget", 0)),
        prior_inferential_trials=int(search.get("prior_inferential_trials", -1)),
        min_dsr_probability=float(court.get("minimum_dsr_probability", 0.0)),
        maximum_pbo=float(court.get("maximum_pbo", -1.0)),
        maximum_placebo_p_value=float(court.get("maximum_placebo_p_value", -1.0)),
        portfolio_policy=PortfolioPolicy(
            initial_nav_cny=float(portfolio.get("initial_nav_cny", 0.0)),
            top_k=int(portfolio.get("top_k", 0)),
            rank_buffer=int(portfolio.get("rank_buffer", -1)),
            round_trip_cost_bps=float(portfolio.get("round_trip_cost_bps", -1.0)),
            participation_rate=float(portfolio.get("participation_rate", 0.0)),
            periods_per_year=int(portfolio.get("periods_per_year", 0)),
        ),
    )
    config.validate()
    daily = str(snapshots.get("qd_daily", ""))
    multi = str(snapshots.get("qd_multisource", ""))
    for value in (daily, multi):
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError("V9 snapshot identities must be lowercase SHA-256 values")
    return config, daily, multi


@dataclass(frozen=True)
class V90PlanningReport:
    method_version: str
    config: V90Config
    calibration: SearchCalibrationReport
    proposal_packet: FrozenProposalPacket
    recovered_v81_proposal_id: str
    mechanism_family_counts: tuple[tuple[str, int], ...]
    llm_mode: str
    labels_read: bool
    inferential_trial_delta: int
    readiness: str
    report_sha256: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        lines = [
            "# V9.0 自动 Alpha 发现准备报告"
            if zh
            else "# V9.0 Automatic Alpha Discovery Readiness Report",
            "",
            f"**{'结论' if zh else 'Decision'}: `{self.readiness}`**",
            "",
            f"- {'搜索标定' if zh else 'Search calibration'}: {self.calibration.passed}",
            f"- {'植入因子排名' if zh else 'Planted-alpha rank'}: {self.calibration.planted_rank}",
            (
                f"- {'冻结实证候选' if zh else 'Frozen empirical candidates'}: "
                f"{len(self.proposal_packet.proposal_ids)}"
            ),
            f"- {'机制族' if zh else 'Mechanism families'}: {len(self.mechanism_family_counts)}",
            f"- {'恢复 V8.1 候选' if zh else 'Recovered V8.1 candidate'}: `{self.recovered_v81_proposal_id}`",
            f"- {'读取真实标签' if zh else 'Real labels read'}: {self.labels_read}",
            f"- {'本阶段 Trial 增量' if zh else 'Trial delta in this stage'}: {self.inferential_trial_delta}",
            f"- LLM: `{self.llm_mode}`",
            "",
            "| Mechanism family | Candidates |",
            "|---|---:|",
        ]
        lines.extend(f"| {name} | {count} |" for name, count in self.mechanism_family_counts)
        lines.extend(
            [
                "",
                (
                    "> 该阶段只做无标签规划和合成搜索能力标定；真实数据运行必须使用冻结候选包，"
                    "并逐一记录 Trial。"
                    if zh
                    else "> This stage performs label-free planning and synthetic search-power calibration only. "
                    "The empirical run must consume this frozen packet and record every Trial."
                ),
                "",
            ]
        )
        return "\n".join(lines)


def frozen_v81_proposal() -> GeneratedProposal:
    return compile_proposal(
        ProposalSpec(
            formula=(
                "mean(net_inflow_amount, 5) / (mean(amount, 5) + 1) "
                "- period_return(close, 5)"
            ),
            hypothesis=(
                "Normalized net buying pressure may arrive before price fully incorporates demand."
            ),
            research_form="continuous_ranking",
            horizon="20d",
            direction=1,
            origin="symbolic",
            provider_id="symbolic:recovered-v8.1-flow-price-divergence",
        )
    )


def _hash(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def run_v90_planning(
    output_dir: str | Path,
    *,
    config: V90Config | None = None,
) -> V90PlanningReport:
    config = config or V90Config()
    config.validate()
    calibration = run_search_calibration()
    if not calibration.passed:
        raise ValueError("search calibration failed; empirical discovery is forbidden")
    recovered = frozen_v81_proposal()
    proposals = merge_proposals(
        (recovered,),
        generate_structural_proposals(budget=512),
        budget=513,
    )
    packet = freeze_proposal_packet(
        proposals,
        empirical_budget=config.empirical_budget,
        required_proposal_ids=frozenset({recovered.proposal_id}),
    )
    counts = tuple(sorted(Counter(item.mechanism_family for item in packet.lineages).items()))
    base: dict[str, object] = {
        "method_version": V90_VERSION,
        "config": asdict(config),
        "calibration_sha256": calibration.report_sha256,
        "proposal_packet_sha256": packet.packet_sha256,
        "recovered_v81_proposal_id": recovered.proposal_id,
        "mechanism_family_counts": counts,
        "llm_mode": "OPTIONAL_FROZEN_OFFLINE_CACHE_ONLY",
        "labels_read": False,
        "inferential_trial_delta": 0,
        "readiness": "READY_FOR_CONTROLLED_EMPIRICAL_EPOCH",
    }
    report = V90PlanningReport(
        V90_VERSION,
        config,
        calibration,
        packet,
        recovered.proposal_id,
        counts,
        "OPTIONAL_FROZEN_OFFLINE_CACHE_ONLY",
        False,
        0,
        "READY_FOR_CONTROLLED_EMPIRICAL_EPOCH",
        _hash(base),
    )
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "v9.0-readiness.json").write_text(report.to_json() + "\n", encoding="utf-8")
    (output / "v9.0-readiness.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (output / "v9.0-readiness.en.md").write_text(report.to_markdown("en"), encoding="utf-8")
    (output / "v9.0-frozen-proposals.json").write_text(packet.to_json() + "\n", encoding="utf-8")
    return report
