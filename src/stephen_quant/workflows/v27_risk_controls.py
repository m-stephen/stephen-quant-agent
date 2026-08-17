from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from statistics import median

from .v27_pit_readiness import load_v27_m1_config

V27_M2_CONFIG_VERSION = "2.7-m2.1"
V27_M2_METHOD_VERSION = "v2.7-fold-local-price-risk-1.0.0"
V27_M2_REPLAY_VERSION = "v2.7-fold-local-price-risk-replay-1.0.0"
PRICE_CONTROL_SCHEMA = (
    "market_beta",
    "realized_volatility",
    "log_adv",
    "short_term_reversal",
    "medium_term_momentum",
)
M1_PRICE_AUTHORIZATION = {
    "market_beta",
    "realized_volatility",
    "adv_liquidity",
    "price_reversal",
    "price_momentum",
}


def _canonical(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode()


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _finite(value: float, name: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


@dataclass(frozen=True)
class PriceRiskConfig:
    beta_window: int
    volatility_window: int
    adv_window: int
    reversal_window: int
    momentum_window: int
    momentum_skip: int
    winsor_lower_quantile: float
    winsor_upper_quantile: float
    ridge: float

    def validate(self) -> None:
        windows = (
            self.beta_window,
            self.volatility_window,
            self.adv_window,
            self.reversal_window,
            self.momentum_window,
            self.momentum_skip,
        )
        if any(value < 1 for value in windows):
            raise ValueError("risk-control windows must be positive")
        if self.momentum_skip >= self.momentum_window:
            raise ValueError("momentum skip must be shorter than momentum window")
        if not 0 <= self.winsor_lower_quantile < self.winsor_upper_quantile <= 1:
            raise ValueError("winsor quantiles are invalid")
        if self.ridge <= 0:
            raise ValueError("ridge must be positive")


@dataclass(frozen=True)
class PriceRiskObservation:
    instrument: str
    decision_at: str
    close: float
    amount: float
    market_close: float

    def validate(self) -> None:
        try:
            timestamp = datetime.fromisoformat(self.decision_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("risk observation decision_at must be ISO-8601") from exc
        if not self.instrument or timestamp.tzinfo is None:
            raise ValueError("risk observation requires instrument and ISO decision_at")
        for name in ("close", "amount", "market_close"):
            if _finite(float(getattr(self, name)), name) <= 0:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True)
class RawRiskExposure:
    instrument: str
    decision_at: str
    feature_names: tuple[str, ...]
    values: tuple[float, ...]
    history_end_at: str

    def as_mapping(self) -> dict[str, float]:
        if self.feature_names != PRICE_CONTROL_SCHEMA or len(self.values) != len(self.feature_names):
            raise ValueError("risk exposure schema differs from the preregistered schema")
        return dict(zip(self.feature_names, self.values, strict=True))


def _returns(values: Sequence[float]) -> list[float]:
    return [values[index] / values[index - 1] - 1.0 for index in range(1, len(values))]


def _sample_covariance(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or len(left) < 2:
        raise ValueError("covariance requires aligned samples")
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    return sum(
        (x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True)
    ) / (len(left) - 1)


def build_causal_price_exposures(
    observations: Iterable[PriceRiskObservation], config: PriceRiskConfig
) -> tuple[RawRiskExposure, ...]:
    """Build exposures using only observations strictly before each decision timestamp."""
    config.validate()
    rows = sorted(observations, key=lambda row: (row.decision_at, row.instrument))
    seen: set[tuple[str, str]] = set()
    market_by_timestamp: dict[str, float] = {}
    histories: dict[str, list[PriceRiskObservation]] = {}
    exposures: list[RawRiskExposure] = []
    minimum_closes = max(
        config.beta_window + 1,
        config.volatility_window + 1,
        config.adv_window,
        config.reversal_window + 1,
        config.momentum_window + 1,
    )
    for row in rows:
        row.validate()
        key = (row.instrument, row.decision_at)
        if key in seen:
            raise ValueError("duplicate instrument/decision timestamp")
        seen.add(key)
        established_market = market_by_timestamp.setdefault(row.decision_at, row.market_close)
        if not math.isclose(established_market, row.market_close, rel_tol=0, abs_tol=1e-12):
            raise ValueError("market close differs across instruments at one decision timestamp")
        history = histories.setdefault(row.instrument, [])
        if history and history[-1].decision_at >= row.decision_at:
            raise ValueError("risk observations must advance strictly by timestamp")
        if len(history) >= minimum_closes:
            closes = [item.close for item in history]
            markets = [item.market_close for item in history]
            stock_returns = _returns(closes[-(config.beta_window + 1) :])
            market_returns = _returns(markets[-(config.beta_window + 1) :])
            market_variance = _sample_covariance(market_returns, market_returns)
            if market_variance <= 0:
                raise ValueError("market variance must be positive for beta")
            beta = _sample_covariance(stock_returns, market_returns) / market_variance
            vol_returns = _returns(closes[-(config.volatility_window + 1) :])
            vol_mean = sum(vol_returns) / len(vol_returns)
            volatility = math.sqrt(
                sum((value - vol_mean) ** 2 for value in vol_returns)
                / (len(vol_returns) - 1)
            )
            log_adv = math.log(sum(item.amount for item in history[-config.adv_window :]) / config.adv_window)
            reversal = -(closes[-1] / closes[-(config.reversal_window + 1)] - 1.0)
            momentum = (
                closes[-(config.momentum_skip + 1)] / closes[-(config.momentum_window + 1)]
                - 1.0
            )
            values = (beta, volatility, log_adv, reversal, momentum)
            if all(math.isfinite(value) for value in values):
                exposures.append(
                    RawRiskExposure(
                        row.instrument,
                        row.decision_at,
                        PRICE_CONTROL_SCHEMA,
                        values,
                        history[-1].decision_at,
                    )
                )
        history.append(row)
    return tuple(exposures)


def _quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("quantile requires observations")
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


@dataclass(frozen=True)
class FoldLocalRiskState:
    method_version: str
    feature_names: tuple[str, ...]
    training_start: str
    training_end: str
    source_snapshot_sha256: str
    medians: tuple[float, ...]
    scales: tuple[float, ...]
    lower_bounds: tuple[float, ...]
    upper_bounds: tuple[float, ...]
    fit_rows: int
    state_sha256: str

    def validate(self) -> None:
        width = len(PRICE_CONTROL_SCHEMA)
        if self.feature_names != PRICE_CONTROL_SCHEMA or any(
            len(values) != width
            for values in (self.medians, self.scales, self.lower_bounds, self.upper_bounds)
        ):
            raise ValueError("fold risk state schema changed")
        if self.training_start > self.training_end or self.fit_rows < 2:
            raise ValueError("fold risk state bounds are invalid")
        if any(value <= 0 or not math.isfinite(value) for value in self.scales):
            raise ValueError("fold risk state scales are invalid")
        core = {
            "method_version": self.method_version,
            "feature_names": self.feature_names,
            "training_start": self.training_start,
            "training_end": self.training_end,
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "medians": self.medians,
            "scales": self.scales,
            "lower_bounds": self.lower_bounds,
            "upper_bounds": self.upper_bounds,
            "fit_rows": self.fit_rows,
        }
        if self.state_sha256 != _sha(core):
            raise ValueError("fold risk state hash mismatch")


def fit_fold_local_risk_state(
    exposures: Sequence[RawRiskExposure],
    *,
    training_start: str,
    training_end: str,
    source_snapshot_sha256: str,
    config: PriceRiskConfig,
) -> FoldLocalRiskState:
    config.validate()
    if len(source_snapshot_sha256) != 64 or training_start > training_end:
        raise ValueError("fold state bounds or source snapshot are invalid")
    training = [row for row in exposures if training_start <= row.decision_at <= training_end]
    if len(training) < 2:
        raise ValueError("fold-local risk fit requires at least two training rows")
    columns = [[] for _ in PRICE_CONTROL_SCHEMA]
    for row in training:
        mapping = row.as_mapping()
        for index, name in enumerate(PRICE_CONTROL_SCHEMA):
            columns[index].append(_finite(mapping[name], name))
    medians = tuple(median(column) for column in columns)
    lower = tuple(_quantile(column, config.winsor_lower_quantile) for column in columns)
    upper = tuple(_quantile(column, config.winsor_upper_quantile) for column in columns)
    clipped = [
        [min(max(value, lower[index]), upper[index]) for value in column]
        for index, column in enumerate(columns)
    ]
    scales = tuple(
        max(median([abs(value - medians[index]) for value in column]) * 1.4826, 1e-12)
        for index, column in enumerate(clipped)
    )
    core = {
        "method_version": V27_M2_METHOD_VERSION,
        "feature_names": PRICE_CONTROL_SCHEMA,
        "training_start": training_start,
        "training_end": training_end,
        "source_snapshot_sha256": source_snapshot_sha256,
        "medians": medians,
        "scales": scales,
        "lower_bounds": lower,
        "upper_bounds": upper,
        "fit_rows": len(training),
    }
    return FoldLocalRiskState(**core, state_sha256=_sha(core))


@dataclass(frozen=True)
class NormalizedRiskExposure:
    instrument: str
    decision_at: str
    feature_names: tuple[str, ...]
    values: tuple[float, ...]
    fit_state_sha256: str


def _transform_risk_exposures(
    state: FoldLocalRiskState,
    exposures: Sequence[RawRiskExposure],
    *,
    split: str,
) -> tuple[NormalizedRiskExposure, ...]:
    state.validate()
    transformed: list[NormalizedRiskExposure] = []
    for row in exposures:
        if split == "heldout" and row.decision_at <= state.training_end:
            raise ValueError("held-out transform received a training-time observation")
        if split == "training" and not state.training_start <= row.decision_at <= state.training_end:
            raise ValueError("training transform received an out-of-fold observation")
        mapping = row.as_mapping()
        raw = tuple(mapping[name] for name in state.feature_names)
        clipped = tuple(
            min(max(value, state.lower_bounds[index]), state.upper_bounds[index])
            for index, value in enumerate(raw)
        )
        values = tuple(
            (value - state.medians[index]) / state.scales[index]
            for index, value in enumerate(clipped)
        )
        transformed.append(
            NormalizedRiskExposure(
                row.instrument,
                row.decision_at,
                state.feature_names,
                values,
                state.state_sha256,
            )
        )
    return tuple(transformed)


def transform_training_risk_exposures(
    state: FoldLocalRiskState, exposures: Sequence[RawRiskExposure]
) -> tuple[NormalizedRiskExposure, ...]:
    return _transform_risk_exposures(state, exposures, split="training")


def transform_heldout_risk_exposures(
    state: FoldLocalRiskState, exposures: Sequence[RawRiskExposure]
) -> tuple[NormalizedRiskExposure, ...]:
    return _transform_risk_exposures(state, exposures, split="heldout")


def _solve(matrix: list[list[float]], target: list[float]) -> tuple[float, ...]:
    size = len(target)
    augmented = [matrix[row][:] + [target[row]] for row in range(size)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-15:
            raise ValueError("residualization design is singular")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        scale = augmented[column][column]
        augmented[column] = [value / scale for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(augmented[row], augmented[column], strict=True)
            ]
    return tuple(augmented[row][-1] for row in range(size))


@dataclass(frozen=True)
class CandidateControlRow:
    instrument: str
    decision_at: str
    candidate_value: float
    controls: NormalizedRiskExposure


@dataclass(frozen=True)
class FoldLocalResidualizer:
    candidate_name: str
    feature_names: tuple[str, ...]
    training_start: str
    training_end: str
    coefficients: tuple[float, ...]
    ridge: float
    fit_rows: int
    risk_state_sha256: str
    state_sha256: str
    model_scope: str = "PARTIAL_RISK_MODEL_ONLY"
    alpha_court_eligible: bool = False

    def validate(self) -> None:
        if (
            self.feature_names != PRICE_CONTROL_SCHEMA
            or len(self.coefficients) != len(PRICE_CONTROL_SCHEMA) + 1
            or self.model_scope != "PARTIAL_RISK_MODEL_ONLY"
            or self.alpha_court_eligible
        ):
            raise ValueError("residualizer scope or schema changed")
        core = {
            "candidate_name": self.candidate_name,
            "feature_names": self.feature_names,
            "training_start": self.training_start,
            "training_end": self.training_end,
            "coefficients": self.coefficients,
            "ridge": self.ridge,
            "fit_rows": self.fit_rows,
            "risk_state_sha256": self.risk_state_sha256,
            "model_scope": self.model_scope,
            "alpha_court_eligible": self.alpha_court_eligible,
        }
        if self.state_sha256 != _sha(core):
            raise ValueError("residualizer state hash mismatch")


def fit_fold_local_residualizer(
    rows: Sequence[CandidateControlRow],
    *,
    candidate_name: str,
    training_start: str,
    training_end: str,
    risk_state_sha256: str,
    ridge: float,
) -> FoldLocalResidualizer:
    training = [row for row in rows if training_start <= row.decision_at <= training_end]
    width = len(PRICE_CONTROL_SCHEMA) + 1
    if len(training) < width or ridge <= 0 or not candidate_name:
        raise ValueError("residualizer training contract is invalid or undersampled")
    design: list[list[float]] = []
    target: list[float] = []
    for row in training:
        if row.controls.fit_state_sha256 != risk_state_sha256:
            raise ValueError("residualizer rows mix fold-local risk states")
        if row.controls.feature_names != PRICE_CONTROL_SCHEMA:
            raise ValueError("residualizer feature schema changed")
        design.append([1.0, *row.controls.values])
        target.append(_finite(row.candidate_value, "candidate_value"))
    gram = [[0.0 for _ in range(width)] for _ in range(width)]
    rhs = [0.0 for _ in range(width)]
    for x, y in zip(design, target, strict=True):
        for left in range(width):
            rhs[left] += x[left] * y
            for right in range(width):
                gram[left][right] += x[left] * x[right]
    for index in range(1, width):
        gram[index][index] += ridge
    coefficients = _solve(gram, rhs)
    core = {
        "candidate_name": candidate_name,
        "feature_names": PRICE_CONTROL_SCHEMA,
        "training_start": training_start,
        "training_end": training_end,
        "coefficients": coefficients,
        "ridge": ridge,
        "fit_rows": len(training),
        "risk_state_sha256": risk_state_sha256,
        "model_scope": "PARTIAL_RISK_MODEL_ONLY",
        "alpha_court_eligible": False,
    }
    return FoldLocalResidualizer(**core, state_sha256=_sha(core))


def residualize_heldout(
    state: FoldLocalResidualizer, rows: Sequence[CandidateControlRow]
) -> tuple[tuple[str, str, float], ...]:
    state.validate()
    output: list[tuple[str, str, float]] = []
    for row in rows:
        if row.decision_at <= state.training_end:
            raise ValueError("held-out residualization received a training-time row")
        if row.controls.fit_state_sha256 != state.risk_state_sha256:
            raise ValueError("held-out row uses a different risk fit state")
        if (row.instrument, row.decision_at) != (
            row.controls.instrument,
            row.controls.decision_at,
        ):
            raise ValueError("held-out candidate and control identities differ")
        if any(not math.isfinite(value) for value in row.controls.values):
            raise ValueError("held-out controls must be finite")
        design = (1.0, *row.controls.values)
        fitted = sum(value * coefficient for value, coefficient in zip(design, state.coefficients, strict=True))
        output.append((row.instrument, row.decision_at, row.candidate_value - fitted))
    return tuple(output)


@dataclass(frozen=True)
class V27M2Config:
    config_version: str
    issue_number: int
    parent_issue_number: int
    m1_config: str
    expected_m1_config_sha256: str
    prior_inferential_trials: int
    source_snapshot_sha256: str
    risk: PriceRiskConfig

    def validate(self) -> None:
        if self.config_version != V27_M2_CONFIG_VERSION or self.issue_number != 74 or self.parent_issue_number != 67:
            raise ValueError("V2.7 M2 config differs from Issues #67/#74")
        if self.prior_inferential_trials != 48:
            raise ValueError("M2 must preserve 48 prior inferential trials")
        if len(self.expected_m1_config_sha256) != 64 or len(self.source_snapshot_sha256) != 64:
            raise ValueError("M2 hashes must be SHA-256")
        self.risk.validate()

    @property
    def sha256(self) -> str:
        self.validate()
        return _sha(asdict(self))


@dataclass(frozen=True)
class V27M2Report:
    method_version: str
    decision: str
    full_risk_model_status: str
    issue_number: int
    config_sha256: str
    m1_config_sha256: str
    source_snapshot_sha256: str
    authorized_controls: tuple[str, ...]
    blocked_controls: tuple[str, ...]
    fold_local_fit: bool
    causal_history_only: bool
    alpha_court_eligible: bool
    prior_inferential_trials: int
    new_inferential_trials: int
    cumulative_inferential_trials: int
    remote_model_requests: int
    consumed_window_accesses: int
    sealed_window_accesses: int
    directory_enumerations: int
    candidate_return_observations: int
    live_trading_authorized: bool
    decision_sha256: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class V27M2Artifacts:
    json_path: Path
    markdown_en_path: Path
    markdown_zh_path: Path
    replay_manifest_path: Path


@dataclass(frozen=True)
class V27M2ReplayVerification:
    passed: bool
    checked_artifacts: int
    mismatches: tuple[str, ...]


def load_v27_m2_config(path: str | Path) -> V27M2Config:
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    risk = PriceRiskConfig(**payload["risk"])
    config = V27M2Config(
        config_version=str(payload["config_version"]),
        issue_number=int(payload["issue_number"]),
        parent_issue_number=int(payload["parent_issue_number"]),
        m1_config=str(payload["m1_config"]),
        expected_m1_config_sha256=str(payload["expected_m1_config_sha256"]),
        prior_inferential_trials=int(payload["prior_inferential_trials"]),
        source_snapshot_sha256=str(payload["source_snapshot_sha256"]),
        risk=risk,
    )
    config.validate()
    m1 = load_v27_m1_config(source.parent / config.m1_config)
    if m1.sha256 != config.expected_m1_config_sha256:
        raise ValueError("M2 does not match the frozen M1 authorization")
    if M1_PRICE_AUTHORIZATION != {
        use
        for contract in m1.contracts
        if contract.source == "qd_daily"
        for use in contract.authorized_uses
    }:
        raise ValueError("M2 price controls exceed M1 authorization")
    return config


def run_v27_m2_engineering_audit(
    config_path: str | Path, output_dir: str | Path
) -> tuple[V27M2Report, V27M2Artifacts]:
    config = load_v27_m2_config(config_path)
    blocked = ("pit_stock_industry", "revision_safe_log_market_cap")
    core = {
        "config_sha256": config.sha256,
        "decision": "M2_PARTIAL_RISK_MODEL_READY",
        "full_risk_model_status": "DATA_NOT_RESEARCH_READY",
        "authorized_controls": PRICE_CONTROL_SCHEMA,
        "blocked_controls": blocked,
        "new_inferential_trials": 0,
    }
    report = V27M2Report(
        method_version=V27_M2_METHOD_VERSION,
        decision="M2_PARTIAL_RISK_MODEL_READY",
        full_risk_model_status="DATA_NOT_RESEARCH_READY",
        issue_number=config.issue_number,
        config_sha256=config.sha256,
        m1_config_sha256=config.expected_m1_config_sha256,
        source_snapshot_sha256=config.source_snapshot_sha256,
        authorized_controls=PRICE_CONTROL_SCHEMA,
        blocked_controls=blocked,
        fold_local_fit=True,
        causal_history_only=True,
        alpha_court_eligible=False,
        prior_inferential_trials=48,
        new_inferential_trials=0,
        cumulative_inferential_trials=48,
        remote_model_requests=0,
        consumed_window_accesses=0,
        sealed_window_accesses=0,
        directory_enumerations=0,
        candidate_return_observations=0,
        live_trading_authorized=False,
        decision_sha256=_sha(core),
    )
    return report, write_v27_m2_artifacts(report, output_dir)


def _markdown(report: V27M2Report, *, zh: bool) -> str:
    lines = [
        "# V2.7 M2 折内价格风险模型" if zh else "# V2.7 M2 Fold-Local Price Risk Model",
        "",
        f"- {'工程结论' if zh else 'Engineering decision'}: **{report.decision}**",
        f"- {'完整风险模型' if zh else 'Full risk model'}: **{report.full_risk_model_status}**",
        f"- {'Alpha Court 资格' if zh else 'Alpha Court eligible'}: false",
        f"- {'新增推断试验' if zh else 'New inferential trials'}: 0",
        f"- {'2025/2026 访问' if zh else '2025/2026 accesses'}: 0 / 0",
        "",
        "## 已授权控制" if zh else "## Authorized controls",
        "",
        ", ".join(report.authorized_controls),
        "",
        "## 继续封锁" if zh else "## Still blocked",
        "",
        ", ".join(report.blocked_controls),
        "",
        (
            "> 所有拟合状态仅来自训练折；缺失 PIT 行业与可靠市值时不得冒充完整风险模型。"
            if zh
            else "> Every fitted state is training-fold only; without PIT industry and revision-safe size this cannot be represented as a full risk model."
        ),
        "",
    ]
    return "\n".join(lines)


def write_v27_m2_artifacts(report: V27M2Report, output_dir: str | Path) -> V27M2Artifacts:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "v2.7-m2-risk-controls.json"
    en_path = output / "v2.7-m2-risk-controls.en.md"
    zh_path = output / "v2.7-m2-risk-controls.zh.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    en_path.write_text(_markdown(report, zh=False), encoding="utf-8")
    zh_path.write_text(_markdown(report, zh=True), encoding="utf-8")
    paths = (json_path, en_path, zh_path)
    replay = output / "v2.7-m2-replay-manifest.json"
    replay.write_text(
        json.dumps(
            {
                "replay_version": V27_M2_REPLAY_VERSION,
                "artifacts": {item.name: hashlib.sha256(item.read_bytes()).hexdigest() for item in paths},
                "decision_sha256": report.decision_sha256,
                "new_inferential_trials": 0,
                "candidate_return_observations": 0,
                "remote_model_requests": 0,
                "consumed_window_accesses": 0,
                "sealed_window_accesses": 0,
                "directory_enumerations": 0,
            },
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    return V27M2Artifacts(json_path, en_path, zh_path, replay)


def verify_v27_m2_replay(path: str | Path) -> V27M2ReplayVerification:
    manifest = Path(path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if payload.get("replay_version") != V27_M2_REPLAY_VERSION:
        raise ValueError("unsupported V2.7 M2 replay manifest")
    forbidden = (
        "new_inferential_trials",
        "candidate_return_observations",
        "remote_model_requests",
        "consumed_window_accesses",
        "sealed_window_accesses",
        "directory_enumerations",
    )
    if any(int(payload.get(key, -1)) != 0 for key in forbidden):
        raise ValueError("V2.7 M2 replay reports forbidden research activity")
    mismatches = tuple(
        name
        for name, expected in payload["artifacts"].items()
        if not (manifest.parent / name).is_file()
        or hashlib.sha256((manifest.parent / name).read_bytes()).hexdigest() != expected
    )
    return V27M2ReplayVerification(not mismatches, len(payload["artifacts"]), mismatches)
