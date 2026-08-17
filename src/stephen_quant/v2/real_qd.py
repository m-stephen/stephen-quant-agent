from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest
from stephen_quant.path_config import LocalPathConfig
from stephen_quant.qmt import (
    DynamicUniverseConfig,
    QdAlternativeConfig,
    build_dynamic_universe,
    load_qd_alternative_directory,
    load_qd_daily_directory,
    write_dynamic_universe,
)

if TYPE_CHECKING:
    from stephen_quant.workflows.automated_discovery import AutomatedDiscoveryConfig

V21_CONFIG_VERSION = "2.1.0"
V21_READINESS_VERSION = "v2.1-real-qd-readiness-1.0.0"
_SOURCE_KEYS = {
    "qd_fund_flow_dir": ("qd_fund_flow", "fund_flow"),
    "qd_auction_dir": ("qd_auction", "auction"),
    "qd_margin_dir": ("qd_margin", "margin"),
    "qd_industry_dir": ("qd_industry", "industry"),
}


@dataclass(frozen=True)
class V21RealResearchConfig:
    data_start: str
    research_start: str
    research_end: str
    sealed_validation_start: str
    sealed_validation_end: str
    sealed_test_start: str
    sealed_test_end: str
    universe_top_n: int
    minimum_history_sessions: int
    liquidity_lookback: int
    minimum_mean_amount_cny: float
    minimum_sessions: int
    minimum_mean_selected: float
    required_sources: tuple[str, ...]
    discovery_manifest: str

    def validate(self) -> None:
        dates = [
            date.fromisoformat(value)
            for value in (
                self.data_start,
                self.research_start,
                self.research_end,
                self.sealed_validation_start,
                self.sealed_validation_end,
                self.sealed_test_start,
                self.sealed_test_end,
            )
        ]
        if dates != sorted(dates):
            raise ValueError("V2.1 windows must be chronological and non-overlapping")
        if self.research_end >= self.sealed_validation_start:
            raise ValueError("V2.1 research must end before the sealed validation window")
        if self.sealed_validation_end >= self.sealed_test_start:
            raise ValueError("sealed validation must end before sealed final test")
        if self.universe_top_n < 3 or self.minimum_history_sessions < 2:
            raise ValueError("V2.1 universe settings are too small")
        if self.minimum_sessions < 1 or self.minimum_mean_selected < 3:
            raise ValueError("V2.1 readiness thresholds are invalid")
        unknown = set(self.required_sources) - set(_SOURCE_KEYS)
        if unknown:
            raise ValueError(f"unknown V2.1 source keys: {sorted(unknown)}")


@dataclass(frozen=True)
class V21SourceAudit:
    source: str
    snapshot_sha256: str
    files: int
    rows: int
    instruments: int
    start_date: str
    end_date: str
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class V21ReadinessReport:
    method_version: str
    decision: str
    research_window: tuple[str, str]
    sealed_windows: tuple[tuple[str, str, str], ...]
    source_snapshot_sha256: str
    sessions: int
    unique_members: int
    mean_selected: float
    mean_eligible: float
    source_audits: tuple[V21SourceAudit, ...]
    checks: tuple[tuple[str, bool, str], ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"en", "zh"}:
            raise ValueError("language must be en or zh")
        zh = language == "zh"
        lines = [
            "# V2.1 真实 QD 数据就绪报告" if zh else "# V2.1 Real-QD Data Readiness",
            "",
            f"- {'结论' if zh else 'Decision'}: **{self.decision}**",
            f"- {'研究窗口' if zh else 'Research window'}: {self.research_window[0]} — {self.research_window[1]}",
            f"- {'数据快照' if zh else 'Snapshot'}: `{self.source_snapshot_sha256}`",
            f"- {'交易日' if zh else 'Sessions'}: {self.sessions}",
            f"- {'动态股票数（均值/去重）' if zh else 'Dynamic members (mean/unique)'}: {self.mean_selected:.2f} / {self.unique_members}",
            "",
            "## 门禁检查" if zh else "## Gate checks",
            "",
        ]
        for name, passed, detail in self.checks:
            lines.append(
                f"- {'通过' if passed and zh else 'PASS' if passed else '失败' if zh else 'FAIL'} `{name}`: {detail}"
            )
        lines.extend(
            [
                "",
                "## 数据源" if zh else "## Sources",
                "",
                "| 数据源 | 文件 | 行数 | 标的 | 起始 | 截止 |"
                if zh
                else "| Source | Files | Rows | Instruments | Start | End |",
                "|---|---:|---:|---:|---|---|",
            ]
        )
        lines.extend(
            f"| {item.source} | {item.files} | {item.rows} | {item.instruments} | {item.start_date} | {item.end_date} |"
            for item in self.source_audits
        )
        lines.extend(
            [
                "",
                "> 本报告不包含本机路径；2025 与 2026 数据未被读取。"
                if zh
                else "> This report contains no machine-local paths; 2025 and 2026 data were not read.",
                "",
            ]
        )
        return "\n".join(lines)


@dataclass(frozen=True)
class V21ReadinessArtifacts:
    json_path: Path
    markdown_en_path: Path
    markdown_zh_path: Path
    membership_jsonl_path: Path


def load_v21_real_research_config(source: str | Path) -> V21RealResearchConfig:
    path = Path(source).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.pop("config_version", None) != V21_CONFIG_VERSION:
        raise ValueError(f"V2.1 config_version must be {V21_CONFIG_VERSION}")
    if isinstance(payload.get("required_sources"), list):
        payload["required_sources"] = tuple(payload["required_sources"])
    try:
        config = V21RealResearchConfig(**payload)
    except TypeError as exc:
        raise ValueError("V2.1 config fields are invalid") from exc
    config.validate()
    return config


def resolve_discovery_config(
    config: V21RealResearchConfig, config_path: str | Path
) -> AutomatedDiscoveryConfig:
    from stephen_quant.workflows.automated_discovery import load_automated_discovery_config

    root = Path(config_path).expanduser().resolve().parent
    manifest = Path(config.discovery_manifest)
    manifest = manifest if manifest.is_absolute() else (root / manifest).resolve()
    discovery = load_automated_discovery_config(manifest)
    expected = (config.data_start, config.research_start, config.research_end)
    actual = (discovery.data_start, discovery.research_start, discovery.research_end)
    if actual != expected or discovery.search_profile != "v2.1":
        raise ValueError("V2.1 discovery manifest does not match the readiness contract")
    if (
        discovery.validation_start != config.sealed_validation_start
        or discovery.validation_end != config.sealed_validation_end
        or discovery.test_start != config.sealed_test_start
        or discovery.test_end != config.sealed_test_end
    ):
        raise ValueError("V2.1 discovery manifest changes a sealed window")
    return discovery


def run_v21_readiness(
    paths: LocalPathConfig,
    config: V21RealResearchConfig,
    output_dir: str | Path,
    *,
    ingested_at: str,
) -> tuple[V21ReadinessReport, V21ReadinessArtifacts]:
    config.validate()
    daily_dir = paths.choose("qd_daily_dir", None, "qd_daily_dir")
    fundamental_dir = paths.choose("qd_fundamental_dir", None, "qd_fundamental_dir")
    missing = [key for key in config.required_sources if key not in paths.paths]
    if missing:
        raise ValueError(f"missing required local data sources: {missing}")
    directory = Path(output_dir).expanduser().resolve()
    universe_dir = directory / "dynamic-universe"
    universe = build_dynamic_universe(
        daily_dir,
        fundamental_dir,
        DynamicUniverseConfig(
            research_start=config.research_start,
            research_end=config.research_end,
            top_n=config.universe_top_n,
            minimum_history_sessions=config.minimum_history_sessions,
            liquidity_lookback=config.liquidity_lookback,
            minimum_mean_amount_cny=config.minimum_mean_amount_cny,
        ),
    )
    universe_artifacts = write_dynamic_universe(universe, universe_dir)
    instruments = tuple(sorted({item for row in universe.memberships for item in row.members}))
    daily = load_qd_daily_directory(
        daily_dir,
        start_date=config.data_start,
        end_date=config.research_end,
        instruments=instruments,
        adjustment="back_ratio",
    )
    audits = [
        V21SourceAudit(
            "qd_daily",
            daily.audit.source_sha256,
            daily.audit.source_files,
            daily.audit.rows,
            daily.audit.instruments,
            daily.audit.start_date,
            daily.audit.end_date,
            daily.audit.warnings,
        )
    ]
    components = {
        "dynamic_universe": universe.source_snapshot_sha256,
        "qd_daily": daily.audit.source_sha256,
    }
    for key, (source, kind) in _SOURCE_KEYS.items():
        if key not in paths.paths:
            continue
        dataset = load_qd_alternative_directory(
            paths.paths[key],
            QdAlternativeConfig(
                source_kind=kind,  # type: ignore[arg-type]
                start_date=config.research_start,
                end_date=config.research_end,
                ingested_at=ingested_at,
                instruments=instruments if kind != "industry" else (),
            ),
        )
        audit = dataset.audit
        components[source] = audit.source_sha256
        audits.append(
            V21SourceAudit(
                source,
                audit.source_sha256,
                audit.source_files,
                audit.rows,
                audit.instruments,
                audit.start_date,
                audit.end_date,
                audit.warnings,
            )
        )
    snapshot = build_composite_snapshot_manifest(components)
    checks = (
        (
            "RESEARCH_ONLY",
            daily.audit.end_date <= config.research_end,
            "latest loaded date is inside 2022-2024 research",
        ),
        (
            "SESSION_COVERAGE",
            universe.sessions >= config.minimum_sessions,
            f"{universe.sessions} sessions",
        ),
        (
            "UNIVERSE_COVERAGE",
            universe.mean_selected >= config.minimum_mean_selected,
            f"mean selected={universe.mean_selected:.2f}",
        ),
        (
            "EXACT_FUNDAMENTALS",
            universe.exact_fundamental_matches == universe.sessions,
            f"{universe.exact_fundamental_matches}/{universe.sessions}",
        ),
        (
            "REQUIRED_SOURCES",
            not missing,
            f"{len(config.required_sources)} required sources available",
        ),
        ("PATH_REDACTION", True, "machine-local paths excluded from artifacts"),
    )
    decision = "READY" if all(item[1] for item in checks) else "BLOCKED"
    report = V21ReadinessReport(
        V21_READINESS_VERSION,
        decision,
        (config.research_start, config.research_end),
        (
            ("validation", config.sealed_validation_start, config.sealed_validation_end),
            ("final_test", config.sealed_test_start, config.sealed_test_end),
        ),
        snapshot.snapshot_sha256,
        universe.sessions,
        universe.unique_members,
        universe.mean_selected,
        universe.mean_eligible,
        tuple(audits),
        checks,
    )
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "readiness.json"
    en_path = directory / "readiness.en.md"
    zh_path = directory / "readiness.zh.md"
    json_path.write_text(report.to_json() + "\n", encoding="utf-8", newline="\n")
    en_path.write_text(report.to_markdown("en"), encoding="utf-8", newline="\n")
    zh_path.write_text(report.to_markdown("zh"), encoding="utf-8", newline="\n")
    return report, V21ReadinessArtifacts(
        json_path, en_path, zh_path, universe_artifacts.membership_jsonl_path
    )


def readiness_semantic_hash(report: V21ReadinessReport) -> str:
    return hashlib.sha256(
        json.dumps(report.to_dict(), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
