from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from itertools import combinations, pairwise
from pathlib import Path
from statistics import mean, stdev

from stephen_quant.cross_validation import (
    SampleInterval,
    SplitLineage,
    audit_manifest,
    generate_cpcv_manifest,
)
from stephen_quant.evaluation import EvaluationObservation, average_ranks, spearman_correlation
from stephen_quant.falsification import deflated_sharpe_ratio, run_placebo
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import (
    build_composite_snapshot_manifest,
    build_selected_files_snapshot_manifest,
)
from stephen_quant.qmt import (
    PriceLimitContext,
    QmtDailyBar,
    load_qd_daily_directory,
    resolve_price_limit_rule,
    select_qd_daily_files,
)

PRICE_DISCOVERY_VERSION = "v3.1-price-discovery-lab-1.0.0"
LOOKBACKS = (2, 3, 5, 10, 20, 40, 60, 120, 240)
SECONDARY_LOOKBACKS = (5, 20, 60)
HORIZONS = (1, 3, 5, 10, 20)


@dataclass(frozen=True)
class PriceDiscoveryConfig:
    data_start: str = "2021-01-01"
    discovery_year: int = 2022
    confirmation_year: int = 2023
    shadow_year: int = 2024
    dynamic_universe_top_n: int = 50
    freeze_top_n: int = 60
    court_top_n: int = 10
    minimum_cross_section: int = 10
    cpcv_groups: int = 6
    cpcv_test_groups: int = 3
    placebo_repetitions: int = 199
    seed: int = 42
    top_k: int = 5
    commission_bps: float = 3.0
    sell_tax_bps: float = 5.0
    slippage_bps: float = 5.0
    impact_bps: float = 10.0
    court_minimum_excess_sharpe: float = 0.50
    court_maximum_drawdown: float = 0.25
    minimum_dsr_probability: float = 0.95
    maximum_placebo_p_value: float = 0.05
    maximum_pbo: float = 0.20

    def validate(self) -> None:
        if (self.discovery_year, self.confirmation_year, self.shadow_year) != (2022, 2023, 2024):
            raise ValueError("V3.1 windows are frozen to 2022/2023/2024")
        if self.dynamic_universe_top_n < self.minimum_cross_section:
            raise ValueError("dynamic universe must cover the minimum cross-section")
        if not 1 <= self.court_top_n <= self.freeze_top_n:
            raise ValueError("court_top_n must be within the frozen shortlist")
        if self.placebo_repetitions < 1:
            raise ValueError("placebo repetitions must be positive")


@dataclass(frozen=True)
class PriceCandidate:
    candidate_id: str
    family: str
    field: str
    lookback: int
    horizon: int
    direction: int
    formula: str
    fingerprint: str


@dataclass(frozen=True)
class YearScore:
    year: int
    dates: int
    observations: int
    mean_rank_ic: float | None
    mean_top_bottom_return: float | None
    mean_top_excess_return: float | None
    spread_sharpe: float | None


@dataclass(frozen=True)
class CandidateResult:
    candidate: PriceCandidate
    discovery: YearScore
    confirmation: YearScore | None
    shadow: YearScore | None
    discovery_rank: int | None
    status: str


@dataclass(frozen=True)
class CpcvResult:
    configurations: int
    paths: int
    selected_fingerprint: str
    selected_mean_oos_rank_ic: float
    selected_positive_paths: int
    pbo: float | None
    hygiene_passed: bool
    manifest_sha256: str


@dataclass(frozen=True)
class SleeveResult:
    horizon: int
    offsets: int
    mean_excess_sharpe: float
    worst_excess_sharpe: float
    worst_drawdown: float
    observations: int


@dataclass(frozen=True)
class CourtResult:
    selected_candidate_id: str | None
    selected_fingerprint: str | None
    cpcv: CpcvResult | None
    signal_placebo_p_value: float | None
    return_placebo_p_value: float | None
    dsr_probability: float | None
    sleeve: SleeveResult | None
    candidate_level_multiplicity: int
    audit_trial_count: int
    decision: str
    failed_gates: tuple[str, ...]


@dataclass(frozen=True)
class PriceDiscoveryReport:
    method_version: str
    experiment_id: str
    snapshot_id: str
    snapshot_sha256: str
    search_space_sha256: str
    generated_candidates: int
    frozen_shortlist_sha256: str
    results: tuple[CandidateResult, ...]
    court: CourtResult
    conclusion: str
    caveats: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        title = "# V3.1 价格因子发现实验" if zh else "# V3.1 Price-Factor Discovery Lab"
        conclusion = "结论" if zh else "Conclusion"
        labels = (
            ("候选总数", "Candidates"),
            ("候选级多重检验数", "Candidate-level multiplicity"),
            ("审计 Trial 总数", "Audit trial count"),
            ("最终判定", "Final decision"),
        )
        lines = [
            title,
            "",
            f"**{conclusion}: {self.conclusion}**",
            "",
            f"- {labels[0][0 if zh else 1]}: {self.generated_candidates}",
            f"- {labels[1][0 if zh else 1]}: {self.court.candidate_level_multiplicity}",
            f"- {labels[2][0 if zh else 1]}: {self.court.audit_trial_count}",
            f"- {labels[3][0 if zh else 1]}: `{self.court.decision}`",
            f"- Snapshot: `{self.snapshot_sha256}`",
            f"- Search space: `{self.search_space_sha256}`",
            f"- Frozen Top 60: `{self.frozen_shortlist_sha256}`",
            "",
            "## Top candidates" if not zh else "## 领先候选",
            "",
            "| Rank | Candidate | 2022 RankIC | 2023 RankIC | 2024 RankIC | Status |",
            "|---:|---|---:|---:|---:|---|",
        ]
        ranked = sorted(
            (item for item in self.results if item.discovery_rank is not None),
            key=lambda item: item.discovery_rank or 10**9,
        )[:15]
        for item in ranked:
            value = lambda score: "N/A" if score is None or score.mean_rank_ic is None else f"{score.mean_rank_ic:.6f}"
            lines.append(
                f"| {item.discovery_rank} | `{item.candidate.candidate_id}` | "
                f"{value(item.discovery)} | {value(item.confirmation)} | "
                f"{value(item.shadow)} | {item.status} |"
            )
        lines.extend(["", "## Alpha Court", ""])
        if self.court.selected_candidate_id is None:
            lines.append("- No candidate reached the court." if not zh else "- 没有候选进入 Alpha Court。")
        else:
            lines.append(
                f"- {'入选候选' if zh else 'Selected'}: `{self.court.selected_candidate_id}`"
            )
            if self.court.cpcv is not None:
                lines.append(
                    f"- {'CPCV 样本外平均 RankIC' if zh else 'CPCV mean OOS RankIC'}: "
                    f"{self.court.cpcv.selected_mean_oos_rank_ic:.6f}"
                )
                lines.append(
                    f"- {'CPCV 正向路径' if zh else 'CPCV positive paths'}: "
                    f"{self.court.cpcv.selected_positive_paths}/{self.court.cpcv.paths}"
                )
                lines.append(f"- PBO: {self.court.cpcv.pbo if self.court.cpcv.pbo is not None else 'N/A'}")
            lines.append(f"- {'信号安慰剂 p 值' if zh else 'Signal placebo p'}: {self.court.signal_placebo_p_value}")
            lines.append(f"- {'收益安慰剂 p 值' if zh else 'Return placebo p'}: {self.court.return_placebo_p_value}")
            lines.append(f"- {'DSR 概率' if zh else 'DSR probability'}: {self.court.dsr_probability}")
            if self.court.sleeve is not None:
                lines.append(f"- {'平均分袖超额 Sharpe' if zh else 'Mean sleeve excess Sharpe'}: {self.court.sleeve.mean_excess_sharpe:.6f}")
                lines.append(f"- {'最差分袖回撤' if zh else 'Worst sleeve drawdown'}: {self.court.sleeve.worst_drawdown:.6f}")
            lines.append(f"- {'未通过门禁' if zh else 'Failed gates'}: {', '.join(self.court.failed_gates) or ('无' if zh else 'none')}")
        lines.extend(["", "## Caveats" if not zh else "## 限制", ""])
        caveats = self.caveats
        if zh:
            caveats = (
                "项目过去已检查过 2022–2024；本次属于校准与回顾性影子证据，不是未经触碰的实时样本外证据。",
                "动态股票池来自已有 PIT 成分工件；不对缺失的历史行业成分进行猜测或填补。",
                "2025 和 2026 未被读取、列举、排序或用于推断。",
                "多头 Top 5 可交易性测试与横截面因子有效性分开报告。",
            )
        lines.extend(f"- {item}" for item in caveats)
        lines.append("")
        return "\n".join(lines)


@dataclass(frozen=True)
class _DailyMetric:
    day: str
    rank_ic: float
    top_bottom: float
    top_excess: float
    observations: int


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def generate_price_candidates() -> tuple[PriceCandidate, ...]:
    raw: list[tuple[str, str, int, int, int, str]] = []
    for field in ("open", "high", "low", "close"):
        for lookback in LOOKBACKS:
            for horizon in HORIZONS:
                for direction in (-1, 1):
                    raw.append(("ohlc_return", field, lookback, horizon, direction, f"return({field},{lookback})"))
    for family in (
        "risk_adjusted_return",
        "volatility",
        "max_drawdown",
        "amihud",
        "volume_return",
        "amount_return",
    ):
        for lookback in SECONDARY_LOOKBACKS:
            for horizon in HORIZONS:
                for direction in (-1, 1):
                    raw.append((family, family, lookback, horizon, direction, f"{family}({lookback})"))
    for lookback in SECONDARY_LOOKBACKS:
        for horizon in HORIZONS:
            for direction in (-1, 1):
                short = max(2, lookback // 4)
                raw.append(("sma_ratio", "close", lookback, horizon, direction, f"sma(close,{short})/sma(close,{lookback})-1"))
    for family in ("price_volume_interaction", "price_amihud_interaction"):
        for lookback in SECONDARY_LOOKBACKS:
            for horizon in HORIZONS:
                for direction in (-1, 1):
                    raw.append((family, family, lookback, horizon, direction, f"{family}({lookback})"))
    result: list[PriceCandidate] = []
    for family, field, lookback, horizon, direction, formula in raw:
        identity = {
            "family": family,
            "field": field,
            "lookback": lookback,
            "horizon": horizon,
            "direction": direction,
            "formula": formula,
            "version": PRICE_DISCOVERY_VERSION,
        }
        sign = "pos" if direction == 1 else "neg"
        result.append(
            PriceCandidate(
                candidate_id=f"{family}_{field}_{lookback}_{horizon}d_{sign}",
                family=family,
                field=field,
                lookback=lookback,
                horizon=horizon,
                direction=direction,
                formula=formula,
                fingerprint=_fingerprint(identity),
            )
        )
    ordered = tuple(sorted(result, key=lambda item: item.candidate_id))
    if len(ordered) != 630 or len({item.fingerprint for item in ordered}) != 630:
        raise AssertionError("price candidate grammar must contain exactly 630 unique specs")
    return ordered


def _load_memberships(path: str | Path, top_n: int) -> tuple[dict[str, tuple[str, ...]], str]:
    source = Path(path).expanduser().resolve()
    content = source.read_bytes()
    rows: dict[str, tuple[str, ...]] = {}
    for number, line in enumerate(content.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        day = str(payload["decision_date"])
        members = tuple(dict.fromkeys(str(item).strip().upper() for item in payload["members"]))
        if day in rows or not members:
            raise ValueError(f"invalid dynamic membership line {number}")
        rows[day] = members[:top_n]
    if not rows:
        raise ValueError("dynamic membership file is empty")
    return rows, hashlib.sha256(content).hexdigest()


def _execution_memberships(
    memberships: dict[str, tuple[str, ...]], dates: tuple[str, ...]
) -> dict[str, tuple[str, ...]]:
    decisions = sorted(memberships)
    output: dict[str, tuple[str, ...]] = {}
    cursor = 0
    latest: tuple[str, ...] = ()
    for day in dates:
        while cursor < len(decisions) and decisions[cursor] < day:
            latest = memberships[decisions[cursor]]
            cursor += 1
        output[day] = latest
    return output


def _safe_return(start: float, end: float) -> float | None:
    if start <= 0 or not math.isfinite(start) or not math.isfinite(end):
        return None
    value = end / start - 1
    return value if math.isfinite(value) else None


def _signal(candidate: PriceCandidate, history: list[QmtDailyBar]) -> float | None:
    window = history[-(candidate.lookback + 1) :]
    if len(window) != candidate.lookback + 1:
        return None
    family = candidate.family
    if family == "ohlc_return":
        start = getattr(window[0], candidate.field)
        end = getattr(window[-1], candidate.field)
        value = _safe_return(start, end)
    elif family in {"volume_return", "amount_return"}:
        field = "volume" if family == "volume_return" else "amount"
        value = _safe_return(getattr(window[0], field), getattr(window[-1], field))
    else:
        daily_returns = [
            item
            for item in (
                _safe_return(window[offset - 1].close, window[offset].close)
                for offset in range(1, len(window))
            )
            if item is not None
        ]
        close_return = _safe_return(window[0].close, window[-1].close)
        if close_return is None or len(daily_returns) != len(window) - 1:
            return None
        volatility = stdev(daily_returns) if len(daily_returns) >= 2 else 0.0
        if family == "volatility":
            value = volatility
        elif family == "risk_adjusted_return":
            value = close_return / volatility if volatility > 0 else None
        elif family == "max_drawdown":
            peak = window[0].close
            drawdown = 0.0
            for bar in window:
                peak = max(peak, bar.close)
                drawdown = min(drawdown, bar.close / peak - 1)
            value = drawdown
        elif family == "amihud":
            amounts = [bar.amount for bar in window[1:]]
            value = mean(abs(ret) / amount for ret, amount in zip(daily_returns, amounts, strict=True)) if all(amount > 0 for amount in amounts) else None
        elif family == "sma_ratio":
            short = max(2, candidate.lookback // 4)
            long_mean = mean(bar.close for bar in window)
            value = mean(bar.close for bar in window[-short:]) / long_mean - 1 if long_mean > 0 else None
        elif family == "price_volume_interaction":
            volume_return = _safe_return(window[0].volume, window[-1].volume)
            value = close_return * volume_return if volume_return is not None else None
        elif family == "price_amihud_interaction":
            amounts = [bar.amount for bar in window[1:]]
            amihud = mean(abs(ret) / amount for ret, amount in zip(daily_returns, amounts, strict=True)) if all(amount > 0 for amount in amounts) else None
            value = close_return * amihud if amihud is not None else None
        elif family == "trend_curvature":
            middle = len(window) // 2
            early = _safe_return(window[0].close, window[middle].close)
            recent = _safe_return(window[middle].close, window[-1].close)
            value = recent - early if early is not None and recent is not None else None
        elif family == "breakout_position":
            lowest = min(bar.low for bar in window)
            highest = max(bar.high for bar in window)
            value = (window[-1].close - lowest) / (highest - lowest) if highest > lowest else None
        elif family == "drawdown_recovery":
            trough = min(bar.close for bar in window)
            value = window[-1].close / trough - 1 if trough > 0 else None
        elif family in {"downside_volatility", "upside_volatility"}:
            selected = [
                item
                for item in daily_returns
                if (item < 0 if family == "downside_volatility" else item > 0)
            ]
            value = math.sqrt(mean(item * item for item in selected)) if selected else 0.0
        elif family == "range_volatility":
            value = mean(
                (bar.high - bar.low) / bar.close for bar in window[1:] if bar.close > 0
            )
        elif family == "gap_mean":
            gaps = [
                bar.open / previous.close - 1
                for previous, bar in pairwise(window)
                if previous.close > 0
            ]
            value = mean(gaps) if gaps else None
        elif family == "intraday_mean":
            values = [bar.close / bar.open - 1 for bar in window[1:] if bar.open > 0]
            value = mean(values) if values else None
        elif family == "overnight_momentum":
            value = math.prod(
                bar.open / previous.close
                for previous, bar in pairwise(window)
                if previous.close > 0
            ) - 1
        elif family == "volume_price_divergence":
            volume_return = _safe_return(window[0].volume, window[-1].volume)
            value = close_return - volume_return if volume_return is not None else None
        elif family == "liquidity_change":
            middle = max(2, len(daily_returns) // 2)
            ratios = [
                abs(ret) / bar.amount
                for ret, bar in zip(daily_returns, window[1:], strict=True)
                if bar.amount > 0
            ]
            early = mean(ratios[:middle]) if ratios[:middle] else None
            recent = mean(ratios[middle:]) if ratios[middle:] else None
            value = recent / early - 1 if early and recent is not None else None
        elif family == "return_skewness":
            center = mean(daily_returns)
            variance = mean((item - center) ** 2 for item in daily_returns)
            value = (
                mean((item - center) ** 3 for item in daily_returns) / variance**1.5
                if variance > 0
                else 0.0
            )
        elif family == "price_level":
            value = math.log(window[-1].close) if window[-1].close > 0 else None
        elif family == "t1_delayed_feedback":
            last_return = daily_returns[-1]
            prior_amounts = [bar.amount for bar in window[1:-1] if bar.amount > 0]
            amount_base = mean(prior_amounts) if prior_amounts else None
            abnormal_amount = (
                window[-1].amount / amount_base if amount_base and window[-1].amount > 0 else None
            )
            value = (
                min(last_return, 0.0) * abnormal_amount
                if abnormal_amount is not None
                else None
            )
        elif family == "negative_return_asymmetry":
            negative = [min(item, 0.0) for item in daily_returns]
            positive = [max(item, 0.0) for item in daily_returns]
            value = mean(negative) - mean(positive)
        elif family == "overnight_intraday_divergence":
            overnight = [
                bar.open / previous.close - 1
                for previous, bar in pairwise(window)
                if previous.close > 0
            ]
            intraday = [bar.close / bar.open - 1 for bar in window[1:] if bar.open > 0]
            value = (
                mean(overnight) - mean(intraday)
                if len(overnight) == len(intraday) == candidate.lookback
                else None
            )
        elif family == "gap_fill_pressure":
            interactions = [
                -(bar.open / previous.close - 1) * (bar.close / bar.open - 1)
                for previous, bar in pairwise(window)
                if previous.close > 0 and bar.open > 0
            ]
            value = mean(interactions) if interactions else None
        elif family in {"limit_proximity", "limit_exhaustion"}:
            ratios: list[float] = []
            for previous, bar in pairwise(window):
                if previous.close <= 0 or bar.open <= 0:
                    continue
                rule = resolve_price_limit_rule(
                    PriceLimitContext(bar.instrument, bar.trade_date)
                )
                if not rule.has_limit or rule.ratio is None:
                    continue
                limit = rule.ratio
                close_move = bar.close / previous.close - 1
                proximity = close_move / limit
                if family == "limit_proximity":
                    ratios.append(proximity)
                else:
                    intraday = bar.close / bar.open - 1
                    ratios.append(max(proximity, 0.0) * -intraday)
            value = mean(ratios) if ratios else None
        else:
            raise ValueError(f"unknown price candidate family: {family}")
    return value if value is not None and math.isfinite(value) else None


def _panel(
    candidate: PriceCandidate,
    *,
    year: int,
    calendar: tuple[str, ...],
    bars: dict[str, dict[str, QmtDailyBar]],
    execution_members: dict[str, tuple[str, ...]],
    minimum_cross_section: int,
    signal_cache: dict[tuple[str, str, int, str, str], float | None] | None = None,
) -> tuple[tuple[EvaluationObservation, ...], tuple[_DailyMetric, ...]]:
    rows: list[EvaluationObservation] = []
    metrics: list[_DailyMetric] = []
    start = f"{year}-01-01"
    end = f"{year}-12-31"
    positions = {day: index for index, day in enumerate(calendar)}
    for day in calendar:
        if not start <= day <= end:
            continue
        index = positions[day]
        if index < candidate.lookback + 1 or index + candidate.horizon >= len(calendar):
            continue
        end_day = calendar[index + candidate.horizon]
        cross: list[tuple[str, float, float]] = []
        for instrument in execution_members.get(day, ()):
            series = bars.get(instrument)
            if series is None:
                continue
            history_days = calendar[index - candidate.lookback - 1 : index]
            if any(item not in series for item in history_days) or day not in series or end_day not in series:
                continue
            execution = series[day]
            exit_bar = series[end_day]
            if not execution.can_buy_open or not exit_bar.can_sell_open:
                continue
            cache_key = (
                candidate.family,
                candidate.field,
                candidate.lookback,
                instrument,
                day,
            )
            if signal_cache is not None and cache_key in signal_cache:
                signal = signal_cache[cache_key]
            else:
                signal = _signal(candidate, [series[item] for item in history_days])
                if signal_cache is not None:
                    signal_cache[cache_key] = signal
            forward = _safe_return(execution.open, exit_bar.open)
            if signal is None or forward is None:
                continue
            cross.append((instrument, candidate.direction * signal, forward))
        if len(cross) < minimum_cross_section:
            continue
        ordered = sorted(cross, key=lambda item: (item[1], item[0]))
        signals = [item[1] for item in ordered]
        returns = [item[2] for item in ordered]
        if len(set(signals)) < 2 or len(set(returns)) < 2:
            continue
        rank_ic = spearman_correlation(signals, returns)
        bucket = max(1, len(ordered) // 5)
        top = ordered[-bucket:]
        bottom = ordered[:bucket]
        metrics.append(
            _DailyMetric(
                day=day,
                rank_ic=rank_ic,
                top_bottom=mean(item[2] for item in top) - mean(item[2] for item in bottom),
                top_excess=mean(item[2] for item in top) - mean(returns),
                observations=len(ordered),
            )
        )
        rows.extend(
            EvaluationObservation(
                instrument=instrument,
                timestamp=f"{day}T09:30:00+08:00",
                factor_value=signal,
                factor_available_at=f"{calendar[index - 1]}T15:00:00+08:00",
                label_start_at=f"{day}T09:30:00+08:00",
                label_end_at=f"{end_day}T09:30:00+08:00",
                forward_return=forward,
                horizon=f"{candidate.horizon}d",
                subperiod=str(year),
                regime="unspecified",
            )
            for instrument, signal, forward in cross
        )
    return tuple(rows), tuple(metrics)


def _score(year: int, metrics: tuple[_DailyMetric, ...]) -> YearScore:
    if not metrics:
        return YearScore(year, 0, 0, None, None, None, None)
    spreads = [item.top_bottom for item in metrics]
    spread_sharpe = mean(spreads) / stdev(spreads) if len(spreads) >= 2 and stdev(spreads) > 0 else None
    return YearScore(
        year=year,
        dates=len(metrics),
        observations=sum(item.observations for item in metrics),
        mean_rank_ic=mean(item.rank_ic for item in metrics),
        mean_top_bottom_return=mean(spreads),
        mean_top_excess_return=mean(item.top_excess for item in metrics),
        spread_sharpe=spread_sharpe,
    )


def _cpcv(
    candidates: tuple[PriceCandidate, ...],
    daily: dict[str, tuple[_DailyMetric, ...]],
    groups: int,
    test_groups: int,
    *,
    calendar: tuple[str, ...] | None = None,
    snapshot_id: str = "unit_snapshot",
    experiment_id: str = "unit_experiment",
    trial_id: str = "unit_trial",
    code_version: str = "unit",
    embargo_days: int = 5,
) -> CpcvResult:
    common_dates = sorted(
        set.intersection(*({item.day for item in daily[c.fingerprint]} for c in candidates))
    )
    if len(common_dates) < groups:
        raise ValueError("insufficient common CPCV dates")
    size, remainder = divmod(len(common_dates), groups)
    grouped: list[list[str]] = []
    cursor = 0
    for group in range(groups):
        width = size + (1 if group < remainder else 0)
        grouped.append(common_dates[cursor : cursor + width])
        cursor += width
    by_candidate = {
        candidate.fingerprint: {item.day: item.rank_ic for item in daily[candidate.fingerprint]}
        for candidate in candidates
    }
    calendar = calendar or tuple(sorted(common_dates))
    positions = {day: index for index, day in enumerate(calendar)}
    maximum_horizon = max(candidate.horizon for candidate in candidates)
    samples: list[SampleInterval] = []
    for day in common_dates:
        index = positions.get(day)
        if index is None:
            raise ValueError("CPCV calendar does not contain every evaluation date")
        feature_day = calendar[index - 1] if index > 0 else (date.fromisoformat(day) - timedelta(days=1)).isoformat()
        if index + maximum_horizon < len(calendar):
            label_end = calendar[index + maximum_horizon]
        else:
            label_end = (date.fromisoformat(day) + timedelta(days=maximum_horizon * 2)).isoformat()
        samples.append(
            SampleInterval(
                sample_id=day,
                instrument="CROSS_SECTION",
                feature_at=f"{feature_day}T15:00:00+08:00",
                label_start_at=f"{day}T09:30:00+08:00",
                label_end_at=f"{label_end}T09:30:00+08:00",
            )
        )
    manifest = generate_cpcv_manifest(
        tuple(samples),
        SplitLineage(snapshot_id, experiment_id, trial_id, code_version),
        n_groups=groups,
        n_test_groups=test_groups,
        embargo=timedelta(days=embargo_days),
    )
    hygiene = all(finding.passed for finding in audit_manifest(manifest, tuple(samples)))
    fold_by_id = {fold.fold_id: fold for fold in manifest.folds}
    date_group = {day: group for group, days in enumerate(grouped) for day in days}
    path_scores: dict[str, list[float]] = {
        candidate.fingerprint: [] for candidate in candidates
    }
    for path in manifest.paths:
        for candidate in candidates:
            values = by_candidate[candidate.fingerprint]
            path_values: list[float] = []
            for segment in path.segments:
                fold = fold_by_id[segment.fold_id]
                path_values.extend(
                    values[day]
                    for day in fold.test_ids
                    if date_group[day] == segment.group_id
                )
            path_scores[candidate.fingerprint].append(mean(path_values))
    pbo_failures = 0
    path_count = len(manifest.paths)
    if len(candidates) >= 2:
        half = path_count // 2
        for in_sample in combinations(range(path_count), half):
            out_sample = tuple(index for index in range(path_count) if index not in in_sample)
            train_scores = {
                candidate.fingerprint: mean(
                    path_scores[candidate.fingerprint][index] for index in in_sample
                )
                for candidate in candidates
            }
            selected_train = max(train_scores, key=lambda item: (train_scores[item], item))
            test_scores = [
                mean(path_scores[candidate.fingerprint][index] for index in out_sample)
                for candidate in candidates
            ]
            ranks = average_ranks(test_scores)
            selected_rank = ranks[
                [candidate.fingerprint for candidate in candidates].index(selected_train)
            ]
            if selected_rank / (len(candidates) + 1) <= 0.5:
                pbo_failures += 1
    means = {key: mean(values) for key, values in path_scores.items()}
    selected = max(means, key=lambda item: (means[item], item))
    return CpcvResult(
        configurations=len(candidates),
        paths=path_count,
        selected_fingerprint=selected,
        selected_mean_oos_rank_ic=means[selected],
        selected_positive_paths=sum(value > 0 for value in path_scores[selected]),
        pbo=(
            pbo_failures / math.comb(path_count, path_count // 2)
            if len(candidates) >= 2
            else None
        ),
        hygiene_passed=hygiene,
        manifest_sha256=manifest.manifest_sha256,
    )


def _moments(values: list[float]) -> tuple[float, float]:
    if len(values) < 4:
        return 0.0, 0.0
    center = mean(values)
    variance = mean((item - center) ** 2 for item in values)
    if variance <= 0:
        return 0.0, 0.0
    skew = mean((item - center) ** 3 for item in values) / variance ** 1.5
    excess = mean((item - center) ** 4 for item in values) / variance**2 - 3
    return skew, excess


def _drawdown(returns: list[float]) -> float:
    wealth = 1.0
    peak = 1.0
    worst = 0.0
    for value in returns:
        wealth *= 1 + value
        peak = max(peak, wealth)
        worst = min(worst, wealth / peak - 1)
    return worst


def _sleeves(
    candidate: PriceCandidate,
    rows: tuple[EvaluationObservation, ...],
    config: PriceDiscoveryConfig,
) -> SleeveResult:
    grouped: dict[str, list[EvaluationObservation]] = defaultdict(list)
    for row in rows:
        grouped[row.timestamp[:10]].append(row)
    dates = sorted(grouped)
    round_trip_cost = (
        config.commission_bps * 2
        + config.sell_tax_bps
        + config.slippage_bps * 2
        + config.impact_bps * 2
    ) / 10_000
    sharpes: list[float] = []
    drawdowns: list[float] = []
    observations = 0
    for offset in range(candidate.horizon):
        returns: list[float] = []
        for day in dates[offset :: candidate.horizon]:
            cross = grouped[day]
            selected = sorted(cross, key=lambda row: (row.factor_value, row.instrument))[-config.top_k :]
            if len(selected) < config.top_k:
                continue
            gross = mean(row.forward_return for row in selected)
            benchmark = mean(row.forward_return for row in cross)
            returns.append(gross - benchmark - round_trip_cost)
        observations += len(returns)
        if len(returns) >= 2 and stdev(returns) > 0:
            sharpes.append(mean(returns) / stdev(returns) * math.sqrt(252 / candidate.horizon))
            drawdowns.append(_drawdown(returns))
    if not sharpes:
        return SleeveResult(candidate.horizon, candidate.horizon, float("-inf"), float("-inf"), -1.0, observations)
    return SleeveResult(
        horizon=candidate.horizon,
        offsets=candidate.horizon,
        mean_excess_sharpe=mean(sharpes),
        worst_excess_sharpe=min(sharpes),
        worst_drawdown=min(drawdowns),
        observations=observations,
    )


def run_price_discovery_lab(
    daily_dir: str | Path,
    dynamic_membership_path: str | Path,
    *,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    config: PriceDiscoveryConfig | None = None,
) -> PriceDiscoveryReport:
    config = config or PriceDiscoveryConfig()
    config.validate()
    candidates = generate_price_candidates()
    search_space_sha256 = _fingerprint([asdict(item) for item in candidates])
    memberships, membership_sha256 = _load_memberships(dynamic_membership_path, config.dynamic_universe_top_n)
    instruments = tuple(sorted({instrument for members in memberships.values() for instrument in members}))
    end_date = f"{config.shadow_year}-12-31"
    root = Path(daily_dir).expanduser().resolve()
    files = select_qd_daily_files(root, start_date=config.data_start, end_date=end_date)
    daily_manifest = build_selected_files_snapshot_manifest(root, files)
    composite = build_composite_snapshot_manifest({"qd_daily": daily_manifest.snapshot_sha256, "dynamic_universe": membership_sha256})
    snapshot_id = registry.register_snapshot(composite, vendor_version="QD OHLCV + frozen dynamic universe", notes="V3.1 uses 2022-2024 only; 2025-2026 remain sealed.")
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            name="V3.1 broad OHLCV discovery lab",
            hypothesis="A broad predeclared OHLCV grammar should surface attractive price candidates before falsification.",
            dataset_snapshot_id=snapshot_id,
            code_version=code_version,
            search_space=json.dumps({"candidate_count": 630, "search_space_sha256": search_space_sha256}, sort_keys=True),
        )
    )
    dataset = load_qd_daily_directory(root, start_date=config.data_start, end_date=end_date, instruments=instruments)
    calendar = tuple(sorted({bar.trade_date for bar in dataset.bars}))
    bars: dict[str, dict[str, QmtDailyBar]] = defaultdict(dict)
    for bar in dataset.bars:
        bars[bar.instrument][bar.trade_date] = bar
    execution_members = _execution_memberships(memberships, calendar)

    discovery_scores: dict[str, YearScore] = {}
    discovery_daily: dict[str, tuple[_DailyMetric, ...]] = {}
    trial_ids: dict[str, tuple[str, int]] = {}
    signal_cache: dict[tuple[str, str, int, str, str], float | None] = {}
    for candidate in candidates:
        trial_ids[candidate.fingerprint] = registry.create_trial(
            TrialSpec(
                experiment_id=experiment_id,
                model_name="v3.1_predeclared_ohlcv_candidate",
                factor_set=candidate.candidate_id,
                hyperparams=json.dumps(asdict(candidate), sort_keys=True, separators=(",", ":")),
                seed=config.seed,
                train_start="2022-01-01",
                train_end="2022-12-31",
                validation_start="2023-01-01",
                validation_end="2023-12-31",
                test_start="2024-01-01",
                test_end="2024-12-31",
            )
        )
        _, metrics = _panel(
            candidate,
            year=config.discovery_year,
            calendar=calendar,
            bars=bars,
            execution_members=execution_members,
            minimum_cross_section=config.minimum_cross_section,
            signal_cache=signal_cache,
        )
        discovery_daily[candidate.fingerprint] = metrics
        discovery_scores[candidate.fingerprint] = _score(config.discovery_year, metrics)

    eligible = [candidate for candidate in candidates if discovery_scores[candidate.fingerprint].mean_rank_ic is not None]
    ranked = sorted(
        eligible,
        key=lambda item: (
            discovery_scores[item.fingerprint].mean_rank_ic or float("-inf"),
            discovery_scores[item.fingerprint].mean_top_bottom_return or float("-inf"),
            item.fingerprint,
        ),
        reverse=True,
    )
    shortlist = tuple(ranked[: config.freeze_top_n])
    shortlist_sha256 = _fingerprint([item.fingerprint for item in shortlist])
    confirmation: dict[str, YearScore] = {}
    shadow: dict[str, YearScore] = {}
    panels: dict[tuple[str, int], tuple[EvaluationObservation, ...]] = {}
    daily_metrics: dict[tuple[str, int], tuple[_DailyMetric, ...]] = {}
    for candidate in shortlist:
        for year, target in ((config.confirmation_year, confirmation), (config.shadow_year, shadow)):
            panel, metrics = _panel(
                candidate,
                year=year,
                calendar=calendar,
                bars=bars,
                execution_members=execution_members,
                minimum_cross_section=config.minimum_cross_section,
                signal_cache=signal_cache,
            )
            panels[(candidate.fingerprint, year)] = panel
            daily_metrics[(candidate.fingerprint, year)] = metrics
            target[candidate.fingerprint] = _score(year, metrics)

    research_candidates = tuple(
        candidate
        for candidate in shortlist
        if all(
            value is not None and value > 0
            for score in (confirmation[candidate.fingerprint], shadow[candidate.fingerprint])
            for value in (score.mean_rank_ic, score.mean_top_bottom_return, score.mean_top_excess_return)
        )
    )
    court_candidates = research_candidates[: config.court_top_n]
    court: CourtResult
    if not court_candidates:
        court = CourtResult(None, None, None, None, None, None, None, 630, registry.trial_count(experiment_id), "NO_ALPHA_RESEARCH_GATE", ("2023_2024_stability",))
    else:
        cpcv = _cpcv(
            court_candidates,
            {c.fingerprint: discovery_daily[c.fingerprint] for c in court_candidates},
            config.cpcv_groups,
            config.cpcv_test_groups,
            calendar=calendar,
            snapshot_id=snapshot_id,
            experiment_id=experiment_id,
            trial_id=trial_ids[court_candidates[0].fingerprint][0],
            code_version=code_version,
        )
        selected = next(candidate for candidate in court_candidates if candidate.fingerprint == cpcv.selected_fingerprint)
        combined_panel = panels[(selected.fingerprint, config.confirmation_year)] + panels[(selected.fingerprint, config.shadow_year)]
        signal_placebo = run_placebo(combined_panel, horizon=f"{selected.horizon}d", direction=1, method="signal_shuffle", seed=config.seed, repetitions=config.placebo_repetitions, min_cross_section=config.minimum_cross_section)
        return_placebo = run_placebo(combined_panel, horizon=f"{selected.horizon}d", direction=1, method="return_permutation", seed=config.seed, repetitions=config.placebo_repetitions, min_cross_section=config.minimum_cross_section)
        trial_sharpes = [score.spread_sharpe or 0.0 for score in discovery_scores.values()]
        winner_returns = [item.top_bottom for item in discovery_daily[selected.fingerprint]]
        observed = discovery_scores[selected.fingerprint].spread_sharpe or 0.0
        skew, kurtosis = _moments(winner_returns)
        dsr = deflated_sharpe_ratio(observed_sharpe=observed, trial_sharpes=trial_sharpes, recorded_trial_count=630, observations=len(winner_returns), skewness=skew, excess_kurtosis=kurtosis)
        sleeve = _sleeves(selected, combined_panel, config)
        failed: list[str] = []
        if not cpcv.hygiene_passed:
            failed.append("cpcv_hygiene")
        if cpcv.selected_mean_oos_rank_ic <= 0 or cpcv.selected_positive_paths < math.ceil(cpcv.paths * 0.75):
            failed.append("cpcv")
        if cpcv.pbo is not None and cpcv.pbo > config.maximum_pbo:
            failed.append("pbo")
        if signal_placebo.empirical_p_value > config.maximum_placebo_p_value or return_placebo.empirical_p_value > config.maximum_placebo_p_value:
            failed.append("placebo")
        if dsr.probability < config.minimum_dsr_probability:
            failed.append("dsr")
        if sleeve.mean_excess_sharpe < config.court_minimum_excess_sharpe:
            failed.append("economic_sharpe")
        if sleeve.worst_drawdown < -config.court_maximum_drawdown:
            failed.append("drawdown")
        decision = "COURT_PASS" if not failed else "RESEARCH_CANDIDATE"
        court = CourtResult(selected.candidate_id, selected.fingerprint, cpcv, signal_placebo.empirical_p_value, return_placebo.empirical_p_value, dsr.probability, sleeve, 630, registry.trial_count(experiment_id), decision, tuple(failed))

    rank_lookup = {candidate.fingerprint: index for index, candidate in enumerate(ranked, start=1)}
    results: list[CandidateResult] = []
    research_fingerprints = {item.fingerprint for item in research_candidates}
    court_fingerprints = {item.fingerprint for item in court_candidates}
    for candidate in candidates:
        if candidate.fingerprint in court_fingerprints:
            status = "COURT_CANDIDATE"
        elif candidate.fingerprint in research_fingerprints:
            status = "RESEARCH_CANDIDATE"
        elif candidate.fingerprint in {item.fingerprint for item in shortlist}:
            status = "OVERFIT_CANDIDATE"
        else:
            status = "DISCOVERY_REJECT"
        item = CandidateResult(candidate, discovery_scores[candidate.fingerprint], confirmation.get(candidate.fingerprint), shadow.get(candidate.fingerprint), rank_lookup.get(candidate.fingerprint), status)
        results.append(item)
        registry.record_trial_result(trial_ids[candidate.fingerprint][0], json.dumps(asdict(item), sort_keys=True, separators=(",", ":")))

    conclusion = court.decision
    report = PriceDiscoveryReport(
        method_version=PRICE_DISCOVERY_VERSION,
        experiment_id=experiment_id,
        snapshot_id=snapshot_id,
        snapshot_sha256=composite.snapshot_sha256,
        search_space_sha256=search_space_sha256,
        generated_candidates=len(candidates),
        frozen_shortlist_sha256=shortlist_sha256,
        results=tuple(results),
        court=court,
        conclusion=conclusion,
        caveats=(
            "2022-2024 have been inspected in prior project iterations; this is calibration and retrospective shadow evidence, not untouched live evidence.",
            "The dynamic universe is frozen from the existing point-in-time membership artifact; unavailable historical industry membership is not imputed.",
            "2025 and 2026 are not read, listed, ranked, or used for inference.",
            "A long-only top-five feasibility test is reported separately from cross-sectional factor efficacy.",
        ),
    )
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "price-discovery.json").write_text(report.to_json(), encoding="utf-8")
    (destination / "price-discovery.zh.md").write_text(report.to_markdown("zh"), encoding="utf-8")
    (destination / "price-discovery.en.md").write_text(report.to_markdown("en"), encoding="utf-8")
    return report
