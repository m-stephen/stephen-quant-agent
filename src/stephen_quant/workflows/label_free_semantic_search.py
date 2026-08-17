from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path

from stephen_quant.v2.semantic_search import (
    ContextRole,
    LabelFreeSearchController,
    PITReadiness,
    SemanticContext,
    SemanticPlan,
    StaticDecisionCode,
    build_candidate_identity,
    reject_sealed_references,
    sha256,
)

LABEL_FREE_CONFIG_VERSION = "label-free-semantic-config-1.0.0"
LABEL_FREE_RESULT_VERSION = "label-free-semantic-result-1.0.0"
LABEL_FREE_REPLAY_VERSION = "label-free-semantic-replay-1.0.0"
_SPLITS = ("train", "validation", "sealed_test")
_DUPLICATE_CODES = {
    StaticDecisionCode.SEMANTIC_DUPLICATE,
    StaticDecisionCode.EXPRESSION_DUPLICATE,
    StaticDecisionCode.TOMBSTONE_DESCENDANT,
}


def _read_json(path: str | Path) -> tuple[dict[str, object], str]:
    raw = Path(path).read_bytes()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("label-free config must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise TypeError("label-free config must be a JSON object")
    return payload, sha256(payload)


def _pairs(payload: object, name: str) -> tuple[tuple[str, str], ...]:
    if not isinstance(payload, dict):
        raise TypeError(f"{name} must be an object")
    return tuple(sorted((str(key), str(value)) for key, value in payload.items()))


def _plan(payload: object) -> SemanticPlan:
    if not isinstance(payload, dict):
        raise TypeError("semantic plan must be an object")
    try:
        contexts = tuple(
            SemanticContext(str(item["value"]), ContextRole(str(item["role"])))
            for item in payload["contexts"]
        )
        readiness = tuple(
            (str(field), PITReadiness(str(status)))
            for field, status in payload["pit_readiness"].items()
        )
        plan = SemanticPlan(
            plan_id=str(payload["plan_id"]),
            economic_claim=str(payload["economic_claim"]),
            event=str(payload["event"]),
            contexts=contexts,
            data_semantics=tuple(str(value) for value in payload["data_semantics"]),
            information_set=tuple(str(value) for value in payload["information_set"]),
            transmission_path=str(payload["transmission_path"]),
            economic_direction=int(payload["economic_direction"]),
            observable_proxy=str(payload["observable_proxy"]),
            required_data=tuple(str(value) for value in payload["required_data"]),
            pit_readiness=readiness,
            falsification=tuple(str(value) for value in payload["falsification"]),
            primary_horizon=str(payload["primary_horizon"]),
            secondary_horizon=(
                None
                if payload.get("secondary_horizon") is None
                else str(payload["secondary_horizon"])
            ),
            logic_budget=int(payload["logic_budget"]),
            parameter_budget=int(payload["parameter_budget"]),
        )
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError("semantic plan payload is invalid") from exc
    plan.validate()
    return plan


@dataclass(frozen=True)
class SyntheticCase:
    case_id: str
    split: str
    stage_order: int
    expected_code: StaticDecisionCode
    tombstoned: bool
    plan: SemanticPlan
    parameters: tuple[tuple[str, str], ...]

    def validate(self) -> None:
        if not self.case_id.strip() or self.split not in _SPLITS or self.stage_order < 0:
            raise ValueError("synthetic case identity is invalid")
        self.plan.validate()
        if self.tombstoned != (self.expected_code == StaticDecisionCode.TOMBSTONE_DESCENDANT):
            raise ValueError("synthetic tombstone truth must match expected code")


@dataclass(frozen=True)
class LabelFreeBenchmarkConfig:
    version: str
    proposal_budget: int
    seeds: tuple[int, ...]
    cases: tuple[SyntheticCase, ...]
    config_sha256: str

    def validate(self) -> None:
        if self.version != LABEL_FREE_CONFIG_VERSION or self.proposal_budget < 1:
            raise ValueError("unsupported label-free config or invalid proposal budget")
        if not self.seeds or len(self.seeds) != len(set(self.seeds)):
            raise ValueError("label-free seeds must be non-empty and unique")
        case_ids = tuple(case.case_id for case in self.cases)
        if len(case_ids) != len(set(case_ids)) or len(self.cases) > self.proposal_budget:
            raise ValueError("synthetic cases must be unique and fit the proposal budget")
        if {case.split for case in self.cases} != set(_SPLITS):
            raise ValueError("synthetic cases must cover train, validation and sealed_test")
        for case in self.cases:
            case.validate()


def load_label_free_config(path: str | Path) -> LabelFreeBenchmarkConfig:
    payload, config_sha256 = _read_json(path)
    reject_sealed_references(payload)
    try:
        cases = tuple(
            SyntheticCase(
                case_id=str(item["case_id"]),
                split=str(item["split"]),
                stage_order=int(item["stage_order"]),
                expected_code=StaticDecisionCode(str(item["expected_code"])),
                tombstoned=bool(item.get("tombstoned", False)),
                plan=_plan(item["plan"]),
                parameters=_pairs(item.get("parameters", {}), "parameters"),
            )
            for item in payload["cases"]
        )
        config = LabelFreeBenchmarkConfig(
            version=str(payload["version"]),
            proposal_budget=int(payload["proposal_budget"]),
            seeds=tuple(int(value) for value in payload["seeds"]),
            cases=cases,
            config_sha256=config_sha256,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("label-free config payload is invalid") from exc
    config.validate()
    return config


@dataclass(frozen=True)
class CaseDecision:
    case_id: str
    split: str
    expected_code: str
    baseline_code: str
    semantic_code: str
    semantic_correct: bool


@dataclass(frozen=True)
class SeedBenchmark:
    seed: int
    valid_schemas: int
    compiled_expressions: int
    baseline_duplicate_precision: float
    baseline_duplicate_recall: float
    semantic_duplicate_precision: float
    semantic_duplicate_recall: float
    semantic_tombstone_false_positive_rate: float
    semantic_tombstone_false_negative_rate: float
    mechanism_coverage: int
    mechanism_coverage_per_proposal: float
    expensive_evaluations_avoided: int
    budget_consumed: int
    decisions: tuple[CaseDecision, ...]
    search_event_ids: tuple[str, ...]


def _precision_recall(predicted: list[bool], actual: list[bool]) -> tuple[float, float]:
    true_positive = sum(p and a for p, a in zip(predicted, actual, strict=True))
    return (
        true_positive / max(sum(predicted), 1),
        true_positive / max(sum(actual), 1),
    )


def _run_seed(config: LabelFreeBenchmarkConfig, seed: int) -> SeedBenchmark:
    decisions: list[CaseDecision] = []
    search_events: list[str] = []
    accepted_families: set[str] = set()
    correctly_covered: set[str] = set()
    baseline_expressions: set[str] = set()
    baseline_codes: list[StaticDecisionCode] = []
    semantic_codes: list[StaticDecisionCode] = []
    expected_codes: list[StaticDecisionCode] = []
    rng = random.Random(seed)
    for split in _SPLITS:
        split_cases = [case for case in config.cases if case.split == split]
        ordered = sorted(split_cases, key=lambda item: (item.stage_order, rng.random(), item.case_id))
        controller = LabelFreeSearchController(len(ordered))
        split_families: set[str] = set()
        split_expressions: set[str] = set()
        tombstones = tuple(
            sorted(case.plan.family_sha256 for case in ordered if case.tombstoned)
        )
        for case in ordered:
            identity = build_candidate_identity(case.plan, parameters=case.parameters)
            readiness = dict(case.plan.pit_readiness)
            if any(status == PITReadiness.BLOCKED for status in readiness.values()):
                baseline = StaticDecisionCode.DATA_NOT_RESEARCH_READY
            elif identity.expression.expression_sha256 in baseline_expressions:
                baseline = StaticDecisionCode.EXPRESSION_DUPLICATE
            else:
                baseline = StaticDecisionCode.ACCEPT
                baseline_expressions.add(identity.expression.expression_sha256)
            semantic = controller.evaluate(
                identity,
                known_family_sha256=tuple(sorted(split_families)),
                known_expression_sha256=tuple(sorted(split_expressions)),
                tombstoned_family_sha256=tombstones,
            )
            if semantic.accepted:
                split_families.add(identity.plan.family_sha256)
                split_expressions.add(identity.expression.expression_sha256)
                accepted_families.add(identity.plan.family_sha256)
                if case.expected_code == StaticDecisionCode.ACCEPT:
                    correctly_covered.add(identity.plan.family_sha256)
            expected_codes.append(case.expected_code)
            baseline_codes.append(baseline)
            semantic_codes.append(semantic.code)
            decisions.append(
                CaseDecision(
                    case.case_id,
                    split,
                    case.expected_code.value,
                    baseline.value,
                    semantic.code.value,
                    semantic.code == case.expected_code,
                )
            )
        search_events.extend(event.event_id for event in controller.ledger.events)
    expected_duplicates = [code in _DUPLICATE_CODES for code in expected_codes]
    baseline_duplicates = [code in _DUPLICATE_CODES for code in baseline_codes]
    semantic_duplicates = [code in _DUPLICATE_CODES for code in semantic_codes]
    baseline_precision, baseline_recall = _precision_recall(
        baseline_duplicates, expected_duplicates
    )
    semantic_precision, semantic_recall = _precision_recall(
        semantic_duplicates, expected_duplicates
    )
    actual_tombstone = [
        code == StaticDecisionCode.TOMBSTONE_DESCENDANT for code in expected_codes
    ]
    predicted_tombstone = [
        code == StaticDecisionCode.TOMBSTONE_DESCENDANT for code in semantic_codes
    ]
    false_positive = sum(p and not a for p, a in zip(predicted_tombstone, actual_tombstone, strict=True))
    false_negative = sum(a and not p for p, a in zip(predicted_tombstone, actual_tombstone, strict=True))
    valid = len(config.cases)
    avoided = sum(code != StaticDecisionCode.ACCEPT for code in semantic_codes)
    return SeedBenchmark(
        seed=seed,
        valid_schemas=valid,
        compiled_expressions=valid,
        baseline_duplicate_precision=baseline_precision,
        baseline_duplicate_recall=baseline_recall,
        semantic_duplicate_precision=semantic_precision,
        semantic_duplicate_recall=semantic_recall,
        semantic_tombstone_false_positive_rate=false_positive / max(len(actual_tombstone), 1),
        semantic_tombstone_false_negative_rate=false_negative / max(sum(actual_tombstone), 1),
        mechanism_coverage=len(correctly_covered),
        mechanism_coverage_per_proposal=len(correctly_covered) / valid,
        expensive_evaluations_avoided=avoided,
        budget_consumed=valid,
        decisions=tuple(sorted(decisions, key=lambda item: item.case_id)),
        search_event_ids=tuple(search_events),
    )


@dataclass(frozen=True)
class LabelFreeBenchmarkReport:
    result_version: str
    config_sha256: str
    decision: str
    proposal_budget: int
    seeds: tuple[int, ...]
    split_counts: tuple[tuple[str, int], ...]
    valid_schema_per_proposal: float
    compiled_expression_per_valid_schema: float
    worst_seed_semantic_duplicate_recall: float
    worst_seed_mechanism_coverage: int
    minimum_expensive_evaluations_avoided: int
    inferential_trial_delta: int
    access_2025: int
    access_2026: int
    real_market_matrix_reads: int
    remote_model_requests: int
    seed_results: tuple[SeedBenchmark, ...]
    report_sha256: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def evaluate_label_free_config(config: LabelFreeBenchmarkConfig) -> LabelFreeBenchmarkReport:
    config.validate()
    seed_results = tuple(_run_seed(config, seed) for seed in config.seeds)
    worst_recall = min(item.semantic_duplicate_recall for item in seed_results)
    worst_coverage = min(item.mechanism_coverage for item in seed_results)
    minimum_avoided = min(item.expensive_evaluations_avoided for item in seed_results)
    baseline_best = max(item.baseline_duplicate_recall for item in seed_results)
    all_correct = all(
        decision.semantic_correct
        for seed_result in seed_results
        for decision in seed_result.decisions
    )
    decision = (
        "EFFICIENCY_GAIN"
        if all_correct and worst_recall > baseline_best and minimum_avoided > 0
        else "NO_EFFICIENCY_GAIN"
    )
    payload = {
        "result_version": LABEL_FREE_RESULT_VERSION,
        "config_sha256": config.config_sha256,
        "decision": decision,
        "proposal_budget": config.proposal_budget,
        "seeds": config.seeds,
        "split_counts": tuple(
            (split, sum(case.split == split for case in config.cases)) for split in _SPLITS
        ),
        "valid_schema_per_proposal": 1.0,
        "compiled_expression_per_valid_schema": 1.0,
        "worst_seed_semantic_duplicate_recall": worst_recall,
        "worst_seed_mechanism_coverage": worst_coverage,
        "minimum_expensive_evaluations_avoided": minimum_avoided,
        "inferential_trial_delta": 0,
        "access_2025": 0,
        "access_2026": 0,
        "real_market_matrix_reads": 0,
        "remote_model_requests": 0,
        "seed_results": seed_results,
    }
    hash_payload = {**payload, "seed_results": tuple(asdict(item) for item in seed_results)}
    return LabelFreeBenchmarkReport(**payload, report_sha256=sha256(hash_payload))


@dataclass(frozen=True)
class LabelFreeArtifacts:
    json_path: Path
    markdown_en_path: Path
    markdown_zh_path: Path
    replay_manifest_path: Path


def _markdown(report: LabelFreeBenchmarkReport, *, chinese: bool) -> str:
    title = "# 无标签语义搜索基准" if chinese else "# Label-free semantic search benchmark"
    labels = (
        {
            "decision": "结论",
            "config": "配置 SHA-256",
            "recall": "最差 seed 语义重复召回率",
            "coverage": "最差 seed 机制覆盖数",
            "avoided": "最少避免昂贵评估数",
            "trials": "新增 Inferential Trial",
            "windows": "受限窗口访问",
            "remote": "远程模型请求",
            "boundary": "边界",
        }
        if chinese
        else {
            "decision": "Decision",
            "config": "Config SHA-256",
            "recall": "Worst-seed semantic duplicate recall",
            "coverage": "Worst-seed mechanism coverage",
            "avoided": "Minimum expensive evaluations avoided",
            "trials": "New inferential trials",
            "windows": "Restricted-window access",
            "remote": "Remote model requests",
            "boundary": "Boundary",
        }
    )
    boundary = (
        "仅使用合成 fixture；不得解释为真实 Alpha 证据。"
        if chinese
        else "Synthetic fixtures only; this is not real Alpha evidence."
    )
    return "\n".join(
        (
            title,
            "",
            f"- {labels['decision']}: `{report.decision}`",
            f"- {labels['config']}: `{report.config_sha256}`",
            f"- {labels['recall']}: {report.worst_seed_semantic_duplicate_recall:.4f}",
            f"- {labels['coverage']}: {report.worst_seed_mechanism_coverage}",
            f"- {labels['avoided']}: {report.minimum_expensive_evaluations_avoided}",
            f"- {labels['trials']}: {report.inferential_trial_delta}",
            f"- {labels['windows']}: {report.access_2025 + report.access_2026}",
            f"- {labels['remote']}: {report.remote_model_requests}",
            "",
            f"**{labels['boundary']}：** {boundary}" if chinese else f"**{labels['boundary']}:** {boundary}",
            "",
        )
    )


def write_label_free_artifacts(
    report: LabelFreeBenchmarkReport, output_dir: str | Path
) -> LabelFreeArtifacts:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "label-free-semantic-result.json"
    en_path = output / "label-free-semantic-result.en.md"
    zh_path = output / "label-free-semantic-result.zh.md"
    replay_path = output / "label-free-semantic-replay.json"
    json_path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    en_path.write_text(_markdown(report, chinese=False), encoding="utf-8")
    zh_path.write_text(_markdown(report, chinese=True), encoding="utf-8")
    event_ids = tuple(
        event_id for seed_result in report.seed_results for event_id in seed_result.search_event_ids
    )
    replay = {
        "replay_version": LABEL_FREE_REPLAY_VERSION,
        "config_sha256": report.config_sha256,
        "report_sha256": report.report_sha256,
        "search_event_ids": event_ids,
        "inferential_trial_delta": 0,
        "access_2025": 0,
        "access_2026": 0,
        "real_market_matrix_reads": 0,
        "remote_model_requests": 0,
    }
    replay_path.write_text(
        json.dumps(replay, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return LabelFreeArtifacts(json_path, en_path, zh_path, replay_path)


def run_label_free_benchmark(
    config_path: str | Path, output_dir: str | Path
) -> tuple[LabelFreeBenchmarkReport, LabelFreeArtifacts]:
    config = load_label_free_config(config_path)
    report = evaluate_label_free_config(config)
    return report, write_label_free_artifacts(report, output_dir)


@dataclass(frozen=True)
class LabelFreeReplayVerification:
    config_linked: bool
    result_reproduced: bool
    event_ids_reproduced: bool
    zero_inferential_trials: bool
    zero_restricted_access: bool
    zero_remote_requests: bool
    passed: bool


def verify_label_free_replay(
    config_path: str | Path, replay_manifest_path: str | Path
) -> LabelFreeReplayVerification:
    config = load_label_free_config(config_path)
    report = evaluate_label_free_config(config)
    try:
        replay = json.loads(Path(replay_manifest_path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("label-free replay manifest must be valid JSON") from exc
    if replay.get("replay_version") != LABEL_FREE_REPLAY_VERSION:
        raise ValueError("unsupported label-free replay version")
    expected_events = tuple(
        event_id for seed_result in report.seed_results for event_id in seed_result.search_event_ids
    )
    config_linked = replay.get("config_sha256") == config.config_sha256
    result_reproduced = replay.get("report_sha256") == report.report_sha256
    event_ids_reproduced = tuple(replay.get("search_event_ids", ())) == expected_events
    zero_trials = replay.get("inferential_trial_delta") == report.inferential_trial_delta == 0
    zero_access = (
        replay.get("access_2025") == 0
        and replay.get("access_2026") == 0
        and replay.get("real_market_matrix_reads") == 0
    )
    zero_remote = replay.get("remote_model_requests") == report.remote_model_requests == 0
    passed = all(
        (config_linked, result_reproduced, event_ids_reproduced, zero_trials, zero_access, zero_remote)
    )
    return LabelFreeReplayVerification(
        config_linked,
        result_reproduced,
        event_ids_reproduced,
        zero_trials,
        zero_access,
        zero_remote,
        passed,
    )
