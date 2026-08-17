from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from itertools import pairwise
from pathlib import Path

from .models import QmtDataError

INDUSTRY_PROXY_AUDIT_VERSION = "1.0.0"
ALLOWED_YEARS = (2022, 2023, 2024)
_FILE_NAME = re.compile(r"^(2022|2023|2024)(\d{4})\.csv$")
_REQUIRED_COLUMNS = ("日期", "代码", "行业")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(payload: object) -> str:
    raw = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class IndustryProxyFile:
    path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class IndustryProxyManifest:
    version: int
    audit_version: str
    years: tuple[int, ...]
    files: tuple[IndustryProxyFile, ...]
    manifest_sha256: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class IndustryProxyAudit:
    audit_version: str
    manifest_sha256: str
    classification: str
    research_usage: str
    inferential_trial_delta: int
    files: int
    rows: int
    securities: int
    industries: int
    missing_industry_rows: int
    missing_industry_rate: float
    duplicate_keys: int
    conflicting_keys: int
    eligible_change_securities: int
    changed_securities: int
    changed_security_rate: float
    label_transitions: int
    yearly_rows: dict[str, int]
    yearly_industries: dict[str, int]
    yearly_missing_rate: dict[str, float]
    yearly_distribution_jsd: dict[str, float]
    reasons: tuple[str, ...]
    result_sha256: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    def to_markdown(self, *, language: str) -> str:
        zh = language == "zh"
        title = "日 K 行业代理 PIT 审计" if zh else "Daily-bar Industry Proxy PIT Audit"
        labels = {
            "classification": "结论" if zh else "Classification",
            "usage": "允许用途" if zh else "Permitted use",
            "manifest": "输入 Manifest" if zh else "Input manifest",
            "files": "文件数" if zh else "Files",
            "rows": "记录数" if zh else "Rows",
            "securities": "股票数" if zh else "Securities",
            "industries": "行业数" if zh else "Industries",
            "missing": "行业缺失率" if zh else "Industry missing rate",
            "conflicts": "同日股票冲突" if zh else "Same-day security conflicts",
            "changed": "历史标签变化股票" if zh else "Securities with historical label changes",
            "transitions": "标签跳变次数" if zh else "Label transitions",
            "trials": "推断性试验增量" if zh else "Inferential trial delta",
            "reasons": "判定依据" if zh else "Decision evidence",
        }
        lines = [
            f"# {title}",
            "",
            f"- {labels['classification']}: `{self.classification}`",
            f"- {labels['usage']}: `{self.research_usage}`",
            f"- {labels['manifest']}: `{self.manifest_sha256}`",
            f"- {labels['files']}: {self.files:,}",
            f"- {labels['rows']}: {self.rows:,}",
            f"- {labels['securities']}: {self.securities:,}",
            f"- {labels['industries']}: {self.industries:,}",
            f"- {labels['missing']}: {self.missing_industry_rate:.4%}",
            f"- {labels['conflicts']}: {self.conflicting_keys:,}",
            (
                f"- {labels['changed']}: {self.changed_securities:,} / "
                f"{self.eligible_change_securities:,} ({self.changed_security_rate:.4%})"
            ),
            f"- {labels['transitions']}: {self.label_transitions:,}",
            f"- {labels['trials']}: {self.inferential_trial_delta}",
            "",
            f"## {labels['reasons']}",
            "",
        ]
        lines.extend(f"- {reason}" for reason in self.reasons)
        lines.extend(
            [
                "",
                (
                    "该结论仅决定临时代理行业的研究资格，不替代 Issue #92 的权威历史行业成员数据。"
                    if zh
                    else "This result only governs temporary proxy-industry research eligibility; "
                    "it does not replace authoritative historical membership in Issue #92."
                ),
                "",
            ]
        )
        return "\n".join(lines)


@dataclass(frozen=True)
class IndustryProxyArtifacts:
    manifest_path: Path
    json_path: Path
    markdown_zh_path: Path
    markdown_en_path: Path


def build_industry_proxy_manifest(root: str | Path) -> IndustryProxyManifest:
    directory = Path(root).expanduser().resolve()
    if not directory.is_dir():
        raise QmtDataError(f"daily directory does not exist: {directory}")
    paths: list[Path] = []
    for year in ALLOWED_YEARS:
        paths.extend(sorted(directory.glob(f"{year}*.csv")))
    if not paths:
        raise QmtDataError("no explicit 2022-2024 daily files found")
    files: list[IndustryProxyFile] = []
    for path in sorted(paths, key=lambda item: item.name):
        if path.parent.resolve() != directory or not _FILE_NAME.fullmatch(path.name):
            raise QmtDataError(f"file outside explicit 2022-2024 policy: {path}")
        files.append(
            IndustryProxyFile(path=path.name, size_bytes=path.stat().st_size, sha256=_sha256(path))
        )
    payload = {
        "version": 1,
        "audit_version": INDUSTRY_PROXY_AUDIT_VERSION,
        "years": list(ALLOWED_YEARS),
        "files": [asdict(item) for item in files],
    }
    return IndustryProxyManifest(
        version=1,
        audit_version=INDUSTRY_PROXY_AUDIT_VERSION,
        years=ALLOWED_YEARS,
        files=tuple(files),
        manifest_sha256=_canonical_sha256(payload),
    )


def _js_divergence(left: Counter[str], right: Counter[str]) -> float:
    left_total = sum(left.values())
    right_total = sum(right.values())
    if left_total == 0 or right_total == 0:
        return 1.0
    keys = set(left) | set(right)
    result = 0.0
    for key in keys:
        p = left[key] / left_total
        q = right[key] / right_total
        midpoint = (p + q) / 2
        if p:
            result += 0.5 * p * math.log2(p / midpoint)
        if q:
            result += 0.5 * q * math.log2(q / midpoint)
    return result


def _validate_manifest(root: Path, manifest: IndustryProxyManifest) -> tuple[Path, ...]:
    if manifest.years != ALLOWED_YEARS or manifest.audit_version != INDUSTRY_PROXY_AUDIT_VERSION:
        raise QmtDataError("manifest policy/version mismatch")
    if len({item.path for item in manifest.files}) != len(manifest.files):
        raise QmtDataError("manifest contains duplicate paths")
    payload = {
        "version": manifest.version,
        "audit_version": manifest.audit_version,
        "years": list(manifest.years),
        "files": [asdict(item) for item in manifest.files],
    }
    if _canonical_sha256(payload) != manifest.manifest_sha256:
        raise QmtDataError("manifest SHA-256 mismatch")
    paths: list[Path] = []
    for item in manifest.files:
        if not _FILE_NAME.fullmatch(item.path) or Path(item.path).name != item.path:
            raise QmtDataError(f"invalid allowlisted path: {item.path}")
        path = (root / item.path).resolve()
        if path.parent != root or not path.is_file():
            raise QmtDataError(f"allowlisted file missing or escaped root: {item.path}")
        if path.stat().st_size != item.size_bytes or _sha256(path) != item.sha256:
            raise QmtDataError(f"allowlisted file changed: {item.path}")
        paths.append(path)
    return tuple(paths)


def audit_industry_proxy(
    root: str | Path, manifest: IndustryProxyManifest
) -> IndustryProxyAudit:
    directory = Path(root).expanduser().resolve()
    paths = _validate_manifest(directory, manifest)
    rows = 0
    missing = 0
    duplicate_keys = 0
    conflicting_keys = 0
    seen: dict[tuple[str, str], str] = {}
    history: dict[str, list[tuple[str, str]]] = defaultdict(list)
    yearly_rows: Counter[str] = Counter()
    yearly_missing: Counter[str] = Counter()
    yearly_industry: dict[str, Counter[str]] = defaultdict(Counter)
    industries: Counter[str] = Counter()
    for path in paths:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or any(
                column not in reader.fieldnames for column in _REQUIRED_COLUMNS
            ):
                raise QmtDataError(f"required industry audit columns missing: {path.name}")
            for row in reader:
                day = str(row["日期"]).strip()
                code = str(row["代码"]).strip().upper()
                industry = str(row["行业"] or "").strip()
                if not re.fullmatch(r"202[234]\d{4}", day):
                    raise QmtDataError(f"row outside 2022-2024 firewall: {path.name}:{day}")
                if day != path.stem:
                    raise QmtDataError(f"row date/file partition mismatch: {path.name}:{day}")
                if not code:
                    raise QmtDataError(f"blank security code: {path.name}:{day}")
                year = day[:4]
                rows += 1
                yearly_rows[year] += 1
                if not industry:
                    missing += 1
                    yearly_missing[year] += 1
                else:
                    industries[industry] += 1
                    yearly_industry[year][industry] += 1
                key = (day, code)
                if key in seen:
                    duplicate_keys += 1
                    if seen[key] != industry:
                        conflicting_keys += 1
                    continue
                seen[key] = industry
                history[code].append((day, industry))
    eligible = 0
    changed = 0
    transitions = 0
    for observations in history.values():
        non_missing = [(day, label) for day, label in observations if label]
        if len(non_missing) < 20:
            continue
        eligible += 1
        labels = [label for _, label in sorted(non_missing)]
        count = sum(left != right for left, right in pairwise(labels))
        if count:
            changed += 1
            transitions += count
    missing_rate = missing / rows if rows else 1.0
    changed_rate = changed / eligible if eligible else 0.0
    yearly_missing_rate = {
        year: yearly_missing[year] / yearly_rows[year] if yearly_rows[year] else 1.0
        for year in map(str, ALLOWED_YEARS)
    }
    yearly_distribution_jsd = {
        f"{left}-{right}": _js_divergence(yearly_industry[left], yearly_industry[right])
        for left, right in (("2022", "2023"), ("2023", "2024"))
    }
    reasons: list[str] = []
    hard_failure = (
        rows == 0
        or missing_rate > 0.02
        or conflicting_keys > 0
        or len(industries) < 10
        or any(yearly_rows[str(year)] == 0 for year in ALLOWED_YEARS)
    )
    evidence_of_change = changed >= 5 and changed_rate >= 0.002
    if hard_failure:
        classification = "C_UNUSABLE"
        usage = "NO_RESEARCH_USE"
        reasons.append("Coverage, conflicts, cardinality, or yearly completeness failed a hard gate.")
    elif evidence_of_change:
        classification = "A_PROXY_PIT_CANDIDATE"
        usage = "PROVISIONAL_PROXY_INDUSTRY"
        reasons.append("Daily labels contain measurable within-security historical transitions.")
        reasons.append("Quality gates passed; authority and historical effective intervals remain unproven.")
    else:
        classification = "B_CURRENT_LABEL_BACKFILL"
        usage = "DIAGNOSTICS_ONLY"
        reasons.append("Quality gates passed but within-security historical variation is insufficient.")
        reasons.append("Treat the field as possible current-label backfill until authoritative evidence exists.")
    provisional = {
        "audit_version": INDUSTRY_PROXY_AUDIT_VERSION,
        "manifest_sha256": manifest.manifest_sha256,
        "classification": classification,
        "research_usage": usage,
        "inferential_trial_delta": 0,
        "files": len(paths),
        "rows": rows,
        "securities": len(history),
        "industries": len(industries),
        "missing_industry_rows": missing,
        "missing_industry_rate": missing_rate,
        "duplicate_keys": duplicate_keys,
        "conflicting_keys": conflicting_keys,
        "eligible_change_securities": eligible,
        "changed_securities": changed,
        "changed_security_rate": changed_rate,
        "label_transitions": transitions,
        "yearly_rows": dict(sorted(yearly_rows.items())),
        "yearly_industries": {
            year: len(yearly_industry[year]) for year in map(str, ALLOWED_YEARS)
        },
        "yearly_missing_rate": yearly_missing_rate,
        "yearly_distribution_jsd": yearly_distribution_jsd,
        "reasons": tuple(reasons),
    }
    return IndustryProxyAudit(**provisional, result_sha256=_canonical_sha256(provisional))


def write_industry_proxy_audit(
    root: str | Path, output_dir: str | Path
) -> tuple[IndustryProxyAudit, IndustryProxyArtifacts]:
    directory = Path(output_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    manifest = build_industry_proxy_manifest(root)
    audit = audit_industry_proxy(root, manifest)
    manifest_path = directory / "industry-proxy-manifest.json"
    json_path = directory / "industry-proxy-audit.json"
    markdown_zh_path = directory / "industry-proxy-audit.zh.md"
    markdown_en_path = directory / "industry-proxy-audit.en.md"
    manifest_path.write_text(
        json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    json_path.write_text(audit.to_json() + "\n", encoding="utf-8")
    markdown_zh_path.write_text(audit.to_markdown(language="zh"), encoding="utf-8")
    markdown_en_path.write_text(audit.to_markdown(language="en"), encoding="utf-8")
    return audit, IndustryProxyArtifacts(
        manifest_path=manifest_path,
        json_path=json_path,
        markdown_zh_path=markdown_zh_path,
        markdown_en_path=markdown_en_path,
    )
