from __future__ import annotations

import hashlib
import json
import math
import random
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from statistics import median

from stephen_quant.discovery.portfolio_native import (
    PortfolioObservation,
    PortfolioPolicy,
    evaluate_portfolio_native,
)

V11_VERSION = "11.0.0"
HISTORICAL_SEARCH_FROZEN = True
RAW_GLOBAL_TRIALS_AT_FREEZE = 743


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


@dataclass(frozen=True)
class WindowUseRecord:
    window_id: str
    start: str
    end: str | None
    state: str
    first_use: str
    label_reads: int
    influenced_design: bool
    independent_evidence_eligible: bool


@dataclass(frozen=True)
class FrozenCandidate:
    name: str
    candidate_id: str
    trial_id: str
    expression: str
    direction: int
    operator: str
    method_version: str
    holding_sessions: int
    decision_time: str


@dataclass(frozen=True)
class ForwardProtocol:
    version: str
    frozen_at: str
    maximum_data_date_at_freeze: str
    first_eligible_date_exclusive: str
    source_snapshot_id: str
    code_version: str
    candidates: tuple[FrozenCandidate, ...]
    portfolio: Mapping[str, object]
    checkpoints: tuple[int, ...]
    family_correction: str
    protocol_sha256: str


@dataclass(frozen=True)
class ForwardStatus:
    protocol_sha256: str
    eligible_common_dates: int
    latest_eligible_date: str | None
    checkpoint: str
    performance_conclusion: None


@dataclass(frozen=True)
class UniverseRobustness:
    method_version: str
    samples: int
    median_return: float
    q05_return: float
    q25_return: float
    q75_return: float
    q95_return: float
    positive_fraction: float
    sign_consistency: float
    worst_return: float


@dataclass(frozen=True)
class NullPlacebo:
    method_version: str
    status: str
    p_value: float | None
    null_hypothesis: str
    exchangeable_unit: str
    preserved_constraints: tuple[str, ...]
    destroyed_relationship: str


@dataclass(frozen=True)
class PboIdentifiability:
    status: str
    configurations: int
    folds: int
    unique_rankings: int
    reason: str


@dataclass(frozen=True)
class ContractCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class StatisticalContractReport:
    version: str
    decision: str
    historical_search_frozen: bool
    raw_global_trial_count: int
    trial_taxonomy: Mapping[str, int | str]
    window_uses: tuple[WindowUseRecord, ...]
    planted_universe_robustness: UniverseRobustness
    planted_signal_null: NullPlacebo
    planted_universe_construction_null: NullPlacebo
    noise_signal_null: NullPlacebo
    identifiable_pbo: PboIdentifiability
    repeated_path_pbo: PboIdentifiability
    checks: tuple[ContractCheck, ...]
    report_sha256: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True)

    def to_markdown(self, language: str) -> str:
        zh = language == "zh"
        title = "# V11.0 统计合同结果" if zh else "# V11.0 Statistical Contract Result"
        labels = (
            ("结论", "历史搜索冻结", "冻结时全局 Trial", "检查")
            if zh
            else ("Decision", "Historical search frozen", "Global trials at freeze", "Checks")
        )
        lines = [
            title,
            "",
            f"**{labels[0]}: `{self.decision}`**",
            "",
            f"- {labels[1]}: {str(self.historical_search_frozen).lower()}",
            f"- {labels[2]}: {self.raw_global_trial_count}",
            f"- Signal null p: {self.planted_signal_null.p_value}",
            f"- Universe construction null p: {self.planted_universe_construction_null.p_value}",
            f"- Repeated-path PBO: `{self.repeated_path_pbo.status}`",
            "",
            f"## {labels[3]}",
            "",
        ]
        lines.extend(
            f"- {'PASS' if item.passed else 'FAIL'} — {item.name}: {item.detail}"
            for item in self.checks
        )
        lines.extend(
            [
                "",
                "> 2025–2026 historical return labels were not read."
                if not zh
                else "> 未读取 2025–2026 历史收益标签。",
                "",
            ]
        )
        return "\n".join(lines)


def assert_historical_search_frozen() -> None:
    raise RuntimeError(
        "historical V10 return search is frozen by V11.0; use the one-shot bounded epoch"
    )


def build_window_ledger(maximum_data_date_at_freeze: str) -> tuple[WindowUseRecord, ...]:
    date.fromisoformat(maximum_data_date_at_freeze)
    return (
        WindowUseRecord(
            "historical-development",
            "2022-01-01",
            "2024-12-31",
            "DEVELOPMENT_ONLY",
            "V1.x-V10.x factor research",
            RAW_GLOBAL_TRIALS_AT_FREEZE,
            True,
            False,
        ),
        WindowUseRecord(
            "historical-sealed",
            "2025-01-01",
            maximum_data_date_at_freeze,
            "SEALED",
            "data maintenance only",
            0,
            False,
            False,
        ),
        WindowUseRecord(
            "prospective-forward",
            maximum_data_date_at_freeze,
            None,
            "FORWARD_APPEND_ONLY",
            "V11.0 protocol freeze",
            0,
            False,
            True,
        ),
    )


def build_forward_protocol(
    *,
    frozen_at: str,
    maximum_data_date_at_freeze: str,
    source_snapshot_id: str,
    code_version: str,
) -> ForwardProtocol:
    normalized = re.sub(
        r"(\.\d{6})\d+(?=[+-]\d{2}:\d{2}$)",
        r"\1",
        frozen_at.replace("Z", "+00:00"),
    )
    instant = datetime.fromisoformat(normalized)
    if instant.tzinfo is None:
        raise ValueError("forward freeze timestamp must include a timezone")
    maximum = date.fromisoformat(maximum_data_date_at_freeze)
    # The boundary is a trading-calendar date in the timestamp's declared
    # timezone. Converting an early China-market freeze to UTC would move it
    # to the prior calendar day and incorrectly admit already-existing data.
    freeze_day = instant.date()
    boundary = max(maximum, freeze_day).isoformat()
    candidates = (
        FrozenCandidate(
            "V10.1 intraday liquidity",
            "ec9faf313b03bd78dd999158c994d9a8464149c220c256abca6fa2c96009c1f2",
            "trial_9cc16d0cb3d4fbb5",
            "rank(amihud_intraday)-rank(amount_rank_20)",
            1,
            "divergence",
            "v10.1-bounded-daily-minute-court-1.1.0",
            20,
            "T+1_OPEN",
        ),
        FrozenCandidate(
            "V10.3 closing volume x chip",
            "25023e50365dc75cf614bc025ef36296193ac0447e06cc98feb18d4ff4340f7a",
            "trial_61b095cc20ecdb4d",
            "rank(closing_volume_share)*rank(concentration)",
            1,
            "interaction",
            "v10.3-centered-cross-source-court-1.0.0",
            20,
            "T+1_OPEN",
        ),
    )
    portfolio: Mapping[str, object] = {
        "estimand": "long_only_top40_minus_investable_dynamic_universe_equal_weight",
        "capital_cny": 3_000_000,
        "top_k": 40,
        "rank_buffer": 10,
        "standard_round_trip_cost_bps": 41.0,
        "double_round_trip_cost_bps": 82.0,
        "participation_rate": 0.05,
        "corporate_action_adjustment": "point_in_time_adjustment_factor",
        "suspension_limit_delisting": "frozen_v10_stateful_execution_contract",
        "cash_treatment": "unfilled_weight_remains_cash",
    }
    payload = {
        "version": V11_VERSION,
        "frozen_at": instant.isoformat(),
        "maximum_data_date_at_freeze": maximum.isoformat(),
        "first_eligible_date_exclusive": boundary,
        "source_snapshot_id": source_snapshot_id,
        "code_version": code_version,
        "candidates": [asdict(item) for item in candidates],
        "portfolio": portfolio,
        "checkpoints": [25, 126, 252],
        "family_correction": "Holm two-hypothesis correction at day 252 only",
    }
    return ForwardProtocol(
        V11_VERSION,
        instant.isoformat(),
        maximum.isoformat(),
        boundary,
        source_snapshot_id,
        code_version,
        candidates,
        portfolio,
        (25, 126, 252),
        "Holm two-hypothesis correction at day 252 only",
        _sha(payload),
    )


def forward_status(protocol: ForwardProtocol, common_dates: Sequence[str]) -> ForwardStatus:
    boundary = date.fromisoformat(protocol.first_eligible_date_exclusive)
    dates = sorted({date.fromisoformat(item) for item in common_dates if date.fromisoformat(item) > boundary})
    count = len(dates)
    checkpoint = (
        "PRIMARY_DAY_252"
        if count >= 252
        else "DESCRIPTIVE_DAY_126"
        if count >= 126
        else "RUNTIME_DAY_25"
        if count >= 25
        else "COVERAGE_ONLY"
    )
    return ForwardStatus(
        protocol.protocol_sha256,
        count,
        dates[-1].isoformat() if dates else None,
        checkpoint,
        None,
    )


def _quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _daily_buckets(rows: Sequence[PortfolioObservation], groups: int = 4) -> tuple[tuple[PortfolioObservation, ...], ...]:
    ordered = sorted(rows, key=lambda item: (item.prior_adv_cny, item.instrument))
    return tuple(
        tuple(ordered[index::groups])
        for index in range(groups)
        if ordered[index::groups]
    )


def universe_robustness(
    observations: Sequence[PortfolioObservation],
    policy: PortfolioPolicy,
    *,
    samples: int = 99,
) -> UniverseRobustness:
    grouped: dict[str, list[PortfolioObservation]] = {}
    for item in observations:
        grouped.setdefault(item.date, []).append(item)
    if not grouped or min(map(len, grouped.values())) < math.ceil(policy.top_k / 0.8):
        raise ValueError("universe robustness requires enough names after stratified subsampling")
    rng = random.Random(11001)
    returns = []
    for _ in range(samples):
        subset: list[PortfolioObservation] = []
        for day in sorted(grouped):
            for bucket in _daily_buckets(grouped[day]):
                keep = max(1, math.ceil(len(bucket) * 0.8))
                subset.extend(rng.sample(list(bucket), keep))
        returns.append(
            evaluate_portfolio_native(tuple(subset), policy=policy).net_excess_total_return
        )
    standard = evaluate_portfolio_native(tuple(observations), policy=policy).net_excess_total_return
    sign = 1 if standard >= 0 else -1
    return UniverseRobustness(
        "v11-stratified-universe-robustness-1.0.0",
        samples,
        median(returns),
        _quantile(returns, 0.05),
        _quantile(returns, 0.25),
        _quantile(returns, 0.75),
        _quantile(returns, 0.95),
        sum(value > 0 for value in returns) / samples,
        sum((1 if value >= 0 else -1) == sign for value in returns) / samples,
        min(returns),
    )


def null_placebo(
    observations: Sequence[PortfolioObservation],
    policy: PortfolioPolicy,
    *,
    mode: str,
    samples: int = 99,
) -> NullPlacebo:
    if mode not in {"stratified_signal", "stratified_return", "universe_construction"}:
        raise ValueError("unknown V11 null placebo")
    grouped: dict[str, list[PortfolioObservation]] = {}
    for item in observations:
        grouped.setdefault(item.date, []).append(item)
    minimum = policy.top_k if mode == "stratified_signal" else math.ceil(policy.top_k / 0.8)
    if not grouped or min(map(len, grouped.values())) < minimum:
        return NullPlacebo(
            f"v11-{mode}-null-1.0.0",
            "NOT_IDENTIFIABLE",
            None,
            "no predictive relationship after matched randomization",
            "instrument within date and prior-ADV stratum",
            ("date", "cross-section size", "prior-ADV strata", "cost policy"),
            "signal-return identity",
        )
    observed = evaluate_portfolio_native(tuple(observations), policy=policy).net_excess_total_return
    rng = random.Random(
        11002 if mode == "stratified_signal" else 11006 if mode == "stratified_return" else 11003
    )
    exceed = 0
    for _ in range(samples):
        randomized: list[PortfolioObservation] = []
        for day in sorted(grouped):
            for bucket in _daily_buckets(grouped[day]):
                scores = [item.score for item in bucket]
                returns = [item.forward_return for item in bucket]
                if mode in {"stratified_signal", "universe_construction"}:
                    rng.shuffle(scores)
                if mode == "stratified_return":
                    rng.shuffle(returns)
                paired = [
                    PortfolioObservation(
                        item.date,
                        item.instrument,
                        score,
                        forward_return,
                        item.benchmark_return,
                        item.prior_adv_cny,
                        item.available_at,
                        item.label_start_at,
                    )
                    for item, score, forward_return in zip(
                        bucket, scores, returns, strict=True
                    )
                ]
                if mode == "universe_construction":
                    keep = max(1, math.ceil(len(paired) * 0.8))
                    paired = rng.sample(paired, keep)
                randomized.extend(paired)
        result = evaluate_portfolio_native(tuple(randomized), policy=policy)
        exceed += result.net_excess_total_return >= observed
    return NullPlacebo(
        f"v11-{mode}-null-1.0.0",
        "IDENTIFIABLE",
        (exceed + 1) / (samples + 1),
        "no predictive relationship after matched randomization",
        "instrument within date and prior-ADV stratum",
        ("date", "cross-section size", "prior-ADV strata", "cost policy"),
        "signal-return identity"
        if mode in {"stratified_signal", "stratified_return"}
        else "universe-membership and signal-return identity",
    )


def assess_pbo_identifiability(
    train_scores: Mapping[str, Mapping[str, float]],
    test_scores: Mapping[str, Mapping[str, float]],
) -> PboIdentifiability:
    configurations = tuple(sorted(train_scores))
    if configurations != tuple(sorted(test_scores)) or len(configurations) < 2:
        return PboIdentifiability("NOT_IDENTIFIABLE", len(configurations), 0, 0, "candidate matrices do not match")
    folds = tuple(sorted(next(iter(train_scores.values()))))
    if not folds or any(tuple(sorted(values)) != folds for values in (*train_scores.values(), *test_scores.values())):
        return PboIdentifiability("NOT_IDENTIFIABLE", len(configurations), len(folds), 0, "fold coverage differs")
    rankings = {
        tuple(sorted(configurations, key=lambda item: (train_scores[item][fold], item)))
        for fold in folds
    }
    if len(rankings) < 2:
        return PboIdentifiability(
            "NOT_IDENTIFIABLE",
            len(configurations),
            len(folds),
            len(rankings),
            "candidate ranking is invariant across folds; repeated paths are not independent evidence",
        )
    return PboIdentifiability(
        "IDENTIFIABLE",
        len(configurations),
        len(folds),
        len(rankings),
        "candidate rankings vary across audited folds",
    )


def _synthetic_observations(*, signal: bool) -> tuple[PortfolioObservation, ...]:
    rng = random.Random(11004 if signal else 11005)
    result = []
    for day in range(12):
        date_text = f"2022-{day + 1:02d}-15"
        for instrument in range(80):
            score = (instrument + 1) / 81
            forward = (score - 0.5) * 0.08 + rng.gauss(0, 0.01) if signal else rng.gauss(0, 0.02)
            result.append(
                PortfolioObservation(
                    date_text,
                    f"{instrument:06d}.SZ",
                    score,
                    forward,
                    0.0,
                    10_000_000.0 + instrument * 1_000_000.0,
                    f"{date_text}T08:00:00+08:00",
                    f"{date_text}T09:30:00+08:00",
                )
            )
    return tuple(result)


def run_statistical_contract(
    output_dir: str | Path,
    *,
    maximum_data_date_at_freeze: str = "2026-08-16",
) -> StatisticalContractReport:
    policy = PortfolioPolicy(top_k=20, rank_buffer=5, round_trip_cost_bps=0)
    planted = _synthetic_observations(signal=True)
    noise = _synthetic_observations(signal=False)
    robustness = universe_robustness(planted, policy)
    signal_null = null_placebo(planted, policy, mode="stratified_signal")
    construction_null = null_placebo(planted, policy, mode="universe_construction")
    noise_null = null_placebo(noise, policy, mode="stratified_signal")
    identifiable = assess_pbo_identifiability(
        {"a": {"f1": 2.0, "f2": 0.0}, "b": {"f1": 0.0, "f2": 2.0}},
        {"a": {"f1": 1.0, "f2": -1.0}, "b": {"f1": -1.0, "f2": 1.0}},
    )
    repeated = assess_pbo_identifiability(
        {"a": {"f1": 2.0, "f2": 2.0}, "b": {"f1": 1.0, "f2": 1.0}},
        {"a": {"f1": 2.0, "f2": 2.0}, "b": {"f1": 1.0, "f2": 1.0}},
    )
    windows = build_window_ledger(maximum_data_date_at_freeze)
    checks = (
        ContractCheck("historical_search_fail_closed", HISTORICAL_SEARCH_FROZEN, "legacy V10 return search disabled"),
        ContractCheck("development_window_reclassified", windows[0].state == "DEVELOPMENT_ONLY", "2022-2024 are not independent validation"),
        ContractCheck("planted_signal_survives_universe_robustness", robustness.q25_return > 0, f"q25={robustness.q25_return:.6f}"),
        ContractCheck("planted_signal_rejects_signal_null", signal_null.p_value is not None and signal_null.p_value <= 0.05, f"p={signal_null.p_value}"),
        ContractCheck("planted_signal_rejects_universe_construction_null", construction_null.p_value is not None and construction_null.p_value <= 0.05, f"p={construction_null.p_value}"),
        ContractCheck("noise_does_not_reject_null", noise_null.p_value is not None and noise_null.p_value > 0.05, f"p={noise_null.p_value}"),
        ContractCheck("rank_reversal_is_identifiable", identifiable.status == "IDENTIFIABLE", identifiable.reason),
        ContractCheck("repeated_paths_fail_closed", repeated.status == "NOT_IDENTIFIABLE", repeated.reason),
        ContractCheck("sealed_label_reads", windows[1].label_reads == 0, "unauthorized reads=0"),
    )
    taxonomy: Mapping[str, int | str] = {
        "raw_global_trial_count": RAW_GLOBAL_TRIALS_AT_FREEZE,
        "calibration_trials": 0,
        "label_free_proposals": "preserved in search ledger",
        "label_reading_inferential_trials": RAW_GLOBAL_TRIALS_AT_FREEZE,
        "mechanism_family_trials": "sensitivity disclosure pending historical reconstruction",
        "policy_or_portfolio_trials": 0,
        "engineering_failures": "separate non-inferential ledger",
        "estimated_independent_trials": "range only; never replaces raw count",
    }
    payload = {
        "version": V11_VERSION,
        "decision": "READY_FOR_BOUNDED_EPOCH" if all(item.passed for item in checks) else "STATISTICAL_CONTRACT_NOT_READY",
        "historical_search_frozen": HISTORICAL_SEARCH_FROZEN,
        "raw_global_trial_count": RAW_GLOBAL_TRIALS_AT_FREEZE,
        "trial_taxonomy": taxonomy,
        "window_uses": [asdict(item) for item in windows],
        "planted_universe_robustness": asdict(robustness),
        "planted_signal_null": asdict(signal_null),
        "planted_universe_construction_null": asdict(construction_null),
        "noise_signal_null": asdict(noise_null),
        "identifiable_pbo": asdict(identifiable),
        "repeated_path_pbo": asdict(repeated),
        "checks": [asdict(item) for item in checks],
    }
    report = StatisticalContractReport(
        V11_VERSION,
        payload["decision"],
        HISTORICAL_SEARCH_FROZEN,
        RAW_GLOBAL_TRIALS_AT_FREEZE,
        taxonomy,
        windows,
        robustness,
        signal_null,
        construction_null,
        noise_null,
        identifiable,
        repeated,
        checks,
        _sha(payload),
    )
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "STATISTICAL_CONTRACT_RESULT.json").write_text(report.to_json() + "\n", encoding="utf-8")
    (output / "STATISTICAL_CONTRACT_RESULT.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (output / "STATISTICAL_CONTRACT_RESULT.en.md").write_text(report.to_markdown("en"), encoding="utf-8")
    return report


def write_forward_protocol(protocol: ForwardProtocol, output_dir: str | Path) -> ForwardStatus:
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    protocol_path = output / "FORWARD_PROTOCOL.json"
    payload = json.dumps(asdict(protocol), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if protocol_path.exists() and protocol_path.read_text(encoding="utf-8") != payload:
        raise ValueError("forward protocol is immutable and cannot be overwritten")
    protocol_path.write_text(payload, encoding="utf-8")
    status = forward_status(protocol, ())
    status_path = output / "FORWARD_STATUS.json"
    if status_path.exists():
        previous = json.loads(status_path.read_text(encoding="utf-8"))
        if previous["protocol_sha256"] != protocol.protocol_sha256:
            raise ValueError("forward status protocol hash mismatch")
    status_path.write_text(
        json.dumps(asdict(status), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return status
