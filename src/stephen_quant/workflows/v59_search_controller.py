from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from stephen_quant.discovery.search_controller import (
    DEFAULT_SEARCH_CONTROLLER_CONFIG,
    SEARCH_CONTROLLER_VERSION,
    SearchArmState,
    SearchControllerConfig,
    SearchDecision,
    choose_search_action,
)

V59_VERSION = "v5.9-search-controller-1.0.0"


@dataclass(frozen=True)
class V59Report:
    method_version: str
    controller_version: str
    config: SearchControllerConfig
    spent_trials: int
    arms: tuple[SearchArmState, ...]
    decision: SearchDecision
    validation_or_test_metrics_used: bool
    inferential_trial_delta: int
    status: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        return "\n".join(
            [
                "# V5.9 预算感知搜索控制器" if zh else "# V5.9 Budget-aware Search Controller",
                "",
                f"**{'状态' if zh else 'Status'}: `{self.status}`**",
                "",
                f"- Action: `{self.decision.action}`",
                f"- Family: `{self.decision.family}`",
                f"- Batch: {self.decision.batch_size}",
                f"- Maximum incremental Trials: {self.decision.maximum_incremental_trials}",
                f"- Validation/final-test metrics used: {self.validation_or_test_metrics_used}",
                f"- Controller Trial delta: {self.inferential_trial_delta}",
                "",
            ]
        )


def _default_arms() -> tuple[SearchArmState, ...]:
    return tuple(
        SearchArmState(family, 0, 0, 0, 0.0, cost, None, 0)
        for family, cost in (
            ("price", 1.2),
            ("fund_flow", 1.5),
            ("auction_event", 2.0),
            ("margin", 1.5),
            ("limit_event", 2.0),
            ("industry", 1.5),
            ("chip", 1.5),
        )
    )


def _load_state(path: str | Path) -> tuple[tuple[SearchArmState, ...], int]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != {"spent_trials", "arms"}:
        raise ValueError("controller state requires exactly spent_trials and arms")
    if not isinstance(payload["arms"], list):
        raise TypeError("controller arms must be a list")
    return tuple(SearchArmState(**row) for row in payload["arms"]), int(payload["spent_trials"])


def run_v59_search_controller(
    output_dir: str | Path,
    *,
    state_path: str | Path | None = None,
    config: SearchControllerConfig = DEFAULT_SEARCH_CONTROLLER_CONFIG,
) -> V59Report:
    arms, spent = _default_arms(), 0
    if state_path is not None:
        arms, spent = _load_state(state_path)
    decision = choose_search_action(arms, spent_trials=spent, config=config)
    report = V59Report(
        V59_VERSION,
        SEARCH_CONTROLLER_VERSION,
        config,
        spent,
        arms,
        decision,
        False,
        decision.controller_trial_delta,
        "READY_FOR_PORTFOLIO_AWARE_SEARCH" if decision.action != "STOP" else "SEARCH_STOPPED",
    )
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "v5.9-search-controller.json").write_text(report.to_json() + "\n", encoding="utf-8")
    (output / "v5.9-search-controller.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (output / "v5.9-search-controller.en.md").write_text(report.to_markdown("en"), encoding="utf-8")
    return report
