from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import stdev

from stephen_quant.baseline import BaselineReport

from .csv_adapter import _decode, _parse_date
from .models import QmtDataError

BENCHMARK_METHOD_VERSION = "next-open-benchmark-comparison-1.0.0"


@dataclass(frozen=True)
class BenchmarkComparison:
    method_version: str
    benchmark_name: str
    benchmark_source_sha256: str
    skipped_missing_open_rows: int
    periods: int
    strategy_net_total_return: float
    benchmark_total_return: float
    excess_total_return: float
    benchmark_annualized_return: float
    benchmark_annualized_volatility: float | None
    benchmark_sharpe: float | None
    benchmark_max_drawdown: float
    tracking_error: float | None
    information_ratio: float | None

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self) -> str:
        return "\n".join(
            (
                f"# Benchmark comparison: {self.benchmark_name}",
                "",
                f"- Method: `{self.method_version}`",
                f"- Source SHA-256: `{self.benchmark_source_sha256}`",
                f"- Source rows with missing open excluded: {self.skipped_missing_open_rows}",
                f"- Periods: {self.periods}",
                f"- Strategy net total return: {self.strategy_net_total_return:.6%}",
                f"- Benchmark total return: {self.benchmark_total_return:.6%}",
                f"- Excess total return: {self.excess_total_return:.6%}",
                f"- Benchmark annualized return: {self.benchmark_annualized_return:.6%}",
                f"- Benchmark Sharpe: {self.benchmark_sharpe if self.benchmark_sharpe is not None else 'N/A'}",
                f"- Benchmark maximum drawdown: {self.benchmark_max_drawdown:.6%}",
                f"- Tracking error: {self.tracking_error if self.tracking_error is not None else 'N/A'}",
                f"- Information ratio: {self.information_ratio if self.information_ratio is not None else 'N/A'}",
                "",
            )
        )


@dataclass(frozen=True)
class BenchmarkArtifacts:
    json_path: Path
    markdown_path: Path
    json_sha256: str
    markdown_sha256: str


def compare_to_benchmark(
    report: BaselineReport,
    source: str | Path,
    *,
    benchmark_name: str,
) -> BenchmarkComparison:
    path = Path(source).expanduser().resolve()
    if not path.is_file():
        raise QmtDataError(f"benchmark CSV does not exist: {path}")
    raw = path.read_bytes()
    text, _ = _decode(raw)
    reader = csv.DictReader(text.splitlines())
    required = {"日期", "开盘价"}
    if not reader.fieldnames or not required <= set(reader.fieldnames):
        raise QmtDataError("benchmark CSV is missing 日期 or 开盘价")
    opens: dict[str, float] = {}
    skipped_missing_open_rows = 0
    for row_number, row in enumerate(reader, start=2):
        day = _parse_date(row["日期"], row_number=row_number)
        raw_open = (row.get("开盘价") or "").strip()
        if not raw_open:
            skipped_missing_open_rows += 1
            continue
        try:
            value = float(raw_open)
        except ValueError as exc:
            raise QmtDataError(f"benchmark row {row_number}: invalid open") from exc
        if value <= 0 or not math.isfinite(value):
            raise QmtDataError(f"benchmark row {row_number}: open must be positive")
        if day in opens:
            raise QmtDataError(f"benchmark row {row_number}: duplicate date {day}")
        opens[day] = value

    benchmark_returns: list[float] = []
    strategy_returns: list[float] = []
    for period in report.periods:
        start = period.execution_at[:10]
        end = period.return_end_at[:10]
        if start not in opens or end not in opens:
            raise QmtDataError(f"benchmark is missing return window {start} to {end}")
        benchmark_returns.append(opens[end] / opens[start] - 1)
        strategy_returns.append(period.net_return)
    periods = len(benchmark_returns)
    total = math.prod(1 + value for value in benchmark_returns) - 1
    annualized = (1 + total) ** (252 / periods) - 1
    volatility = stdev(benchmark_returns) * math.sqrt(252) if periods > 1 else None
    sharpe = None
    if volatility not in (None, 0.0):
        sharpe = statistics_mean(benchmark_returns) / stdev(benchmark_returns) * math.sqrt(252)
    nav = 1.0
    peak = 1.0
    drawdown = 0.0
    for value in benchmark_returns:
        nav *= 1 + value
        peak = max(peak, nav)
        drawdown = min(drawdown, nav / peak - 1)
    excess = [left - right for left, right in zip(strategy_returns, benchmark_returns, strict=True)]
    tracking = stdev(excess) * math.sqrt(252) if len(excess) > 1 else None
    information = None
    if tracking not in (None, 0.0):
        information = statistics_mean(excess) / stdev(excess) * math.sqrt(252)
    return BenchmarkComparison(
        method_version=BENCHMARK_METHOD_VERSION,
        benchmark_name=benchmark_name,
        benchmark_source_sha256=hashlib.sha256(raw).hexdigest(),
        skipped_missing_open_rows=skipped_missing_open_rows,
        periods=periods,
        strategy_net_total_return=report.metrics.net_total_return,
        benchmark_total_return=total,
        excess_total_return=report.metrics.net_total_return - total,
        benchmark_annualized_return=annualized,
        benchmark_annualized_volatility=volatility,
        benchmark_sharpe=sharpe,
        benchmark_max_drawdown=drawdown,
        tracking_error=tracking,
        information_ratio=information,
    )


def statistics_mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _write(path: Path, content: str) -> str:
    path.write_text(content, encoding="utf-8", newline="\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def write_benchmark_comparison(
    comparison: BenchmarkComparison, output_dir: str | Path
) -> BenchmarkArtifacts:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "benchmark-comparison.json"
    markdown_path = directory / "benchmark-comparison.md"
    json_content = comparison.to_json() + "\n"
    markdown_content = comparison.to_markdown()
    return BenchmarkArtifacts(
        json_path=json_path,
        markdown_path=markdown_path,
        json_sha256=_write(json_path, json_content),
        markdown_sha256=_write(markdown_path, markdown_content),
    )
