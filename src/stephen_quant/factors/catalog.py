from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .models import FactorDefinition
from .seeds import SEED_FACTORS

CATALOG_VERSION = "factor-catalog-1.0.0"
QD_SUPPORTED_FIELDS = frozenset({"open", "high", "low", "close", "volume", "amount"})
V1_8_8_FACTOR_IDS = frozenset(
    {
        "mom_120_skip_20",
        "trend_efficiency_20",
        "range_position_20",
        "intraday_strength_20",
        "volume_surprise_5_20",
        "signed_volume_mom_20",
        "dollar_liquidity_20",
        "parkinson_vol_20",
    }
)
V1_8_14_FACTOR_IDS = frozenset({"overnight_gap_reversal_20", "close_location_20"})


@dataclass(frozen=True)
class FactorCatalogEntry:
    definition: FactorDefinition
    qd_compatible: bool
    research_status: str
    status_reason: str


@dataclass(frozen=True)
class FactorCatalog:
    catalog_version: str
    entries: tuple[FactorCatalogEntry, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self) -> str:
        lines = [
            "# Factor catalog",
            "",
            f"- Catalog version: `{self.catalog_version}`",
            f"- Definitions: {len(self.entries)}",
            f"- QD-compatible: {sum(entry.qd_compatible for entry in self.entries)}",
            "",
            "| Factor | Category | Direction | Lookback | QD | Status |",
            "|---|---|---:|---:|---|---|",
        ]
        lines.extend(
            "| "
            f"`{entry.definition.key}` | {entry.definition.category} | "
            f"{entry.definition.direction:+d} | {entry.definition.lookback_periods} | "
            f"{'yes' if entry.qd_compatible else 'no'} | {entry.research_status} |"
            for entry in self.entries
        )
        lines.extend(["", "## Status notes", ""])
        lines.extend(
            f"- `{entry.definition.key}`: {entry.status_reason}"
            for entry in self.entries
            if entry.research_status != "available_untested"
        )
        return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class FactorCatalogArtifacts:
    json_path: Path
    markdown_path: Path
    json_sha256: str
    markdown_sha256: str


def build_factor_catalog(
    definitions: tuple[FactorDefinition, ...] = SEED_FACTORS,
) -> FactorCatalog:
    entries: list[FactorCatalogEntry] = []
    for definition in sorted(definitions, key=lambda item: item.key):
        if definition.factor_id == "ret_60":
            status = "rejected_validation"
            reason = "Rejected by the frozen V1.8.7 validation and placebo evidence."
        elif definition.factor_id in V1_8_8_FACTOR_IDS:
            status = "predeclared_unvalidated"
            reason = "Predeclared in V1.8.8; no return-based selection has been performed."
        elif definition.factor_id in V1_8_14_FACTOR_IDS:
            status = "predeclared_v1_8_14"
            reason = "Predeclared in V1.8.14 before CPCV or return evaluation."
        else:
            status = "available_untested"
            reason = "Registered seed definition; requires its own Trial before interpretation."
        entries.append(
            FactorCatalogEntry(
                definition=definition,
                qd_compatible=set(definition.required_fields) <= QD_SUPPORTED_FIELDS,
                research_status=status,
                status_reason=reason,
            )
        )
    return FactorCatalog(catalog_version=CATALOG_VERSION, entries=tuple(entries))


def _write(path: Path, content: str) -> str:
    path.write_text(content, encoding="utf-8", newline="\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def write_factor_catalog(
    catalog: FactorCatalog, output_dir: str | Path
) -> FactorCatalogArtifacts:
    directory = Path(output_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "factor-catalog.json"
    markdown_path = directory / "factor-catalog.md"
    json_content = catalog.to_json() + "\n"
    markdown_content = catalog.to_markdown()
    return FactorCatalogArtifacts(
        json_path=json_path,
        markdown_path=markdown_path,
        json_sha256=_write(json_path, json_content),
        markdown_sha256=_write(markdown_path, markdown_content),
    )
