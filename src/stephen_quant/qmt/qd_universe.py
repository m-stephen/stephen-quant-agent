from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from stephen_quant.integrity.snapshot import build_selected_files_snapshot_manifest

from .csv_adapter import _decode
from .models import QmtDataError
from .qd_csv_adapter import select_qd_daily_files

QD_UNIVERSE_METHOD_VERSION = "qd-training-only-liquidity-universe-1.0.0"
_PARTITION = re.compile(r"^(\d{8})\.csv$", re.IGNORECASE)


@dataclass(frozen=True)
class QdUniverseSelection:
    method_version: str
    source_snapshot_sha256: str
    train_start: str
    train_end: str
    selection_date: str
    trading_sessions: int
    top_n: int
    require_complete_history: bool
    exclude_st: bool
    require_listed_before_train_start: bool
    candidates_seen: int
    complete_history_candidates: int
    unknown_listing_date_records: int
    eligible_candidates: int
    instruments: tuple[str, ...]
    mean_daily_amount_cny: dict[str, float]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)

    @property
    def selection_sha256(self) -> str:
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()

    def to_markdown(self) -> str:
        lines = [
            "# QD training-only universe",
            "",
            f"- Method: `{self.method_version}`",
            f"- Source snapshot: `{self.source_snapshot_sha256}`",
            f"- Training window: {self.train_start} to {self.train_end}",
            f"- Point-in-time selection date: {self.selection_date}",
            f"- Trading sessions: {self.trading_sessions}",
            f"- Candidates seen: {self.candidates_seen}",
            f"- Complete-history candidates: {self.complete_history_candidates}",
            f"- Unknown listing-date records excluded: {self.unknown_listing_date_records}",
            f"- Eligible candidates: {self.eligible_candidates}",
            f"- Selected: {len(self.instruments)}",
            "",
            "| Rank | Instrument | Mean daily amount (CNY) |",
            "|---:|---|---:|",
        ]
        lines.extend(
            f"| {rank} | {instrument} | {self.mean_daily_amount_cny[instrument]:.2f} |"
            for rank, instrument in enumerate(self.instruments, start=1)
        )
        return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class QdUniverseArtifacts:
    json_path: Path
    markdown_path: Path
    stock_file_path: Path
    json_sha256: str
    markdown_sha256: str
    stock_file_sha256: str


def _latest_partition(root: Path, end: date) -> Path:
    candidates: list[tuple[date, Path]] = []
    for path in root.iterdir():
        match = _PARTITION.fullmatch(path.name)
        if not path.is_file() or match is None:
            continue
        raw = match.group(1)
        day = date(int(raw[:4]), int(raw[4:6]), int(raw[6:]))
        if day <= end:
            candidates.append((day, path))
    if not candidates:
        raise QmtDataError(f"no fundamental partition is available on or before {end}")
    return max(candidates)[1]


def _reader(path: Path) -> csv.DictReader:
    text, _ = _decode(path.read_bytes())
    return csv.DictReader(text.splitlines())


def select_qd_training_universe(
    daily_dir: str | Path,
    fundamental_dir: str | Path,
    *,
    train_start: str,
    train_end: str,
    top_n: int,
) -> QdUniverseSelection:
    """Select a fixed test universe using training data and point-in-time metadata only."""

    if top_n < 1:
        raise QmtDataError("top_n must be positive")
    try:
        start, end = date.fromisoformat(train_start), date.fromisoformat(train_end)
    except ValueError as exc:
        raise QmtDataError("training boundaries must be ISO dates") from exc
    if start > end:
        raise QmtDataError("train_start must not be after train_end")
    daily_root = Path(daily_dir).expanduser().resolve()
    fundamental_root = Path(fundamental_dir).expanduser().resolve()
    if not fundamental_root.is_dir():
        raise QmtDataError(f"QD fundamental source is not a directory: {fundamental_root}")
    daily_files = select_qd_daily_files(
        daily_root,
        start_date=train_start,
        end_date=train_end,
    )
    fundamental_file = _latest_partition(fundamental_root, end)
    common_root = Path(os.path.commonpath((daily_root, fundamental_root)))
    snapshot = build_selected_files_snapshot_manifest(
        common_root, (*daily_files, fundamental_file)
    )

    counts: dict[str, int] = defaultdict(int)
    amount_sums: dict[str, float] = defaultdict(float)
    for path in daily_files:
        reader = _reader(path)
        required = {"代码", "成交额(千元)"}
        if not reader.fieldnames or not required <= set(reader.fieldnames):
            raise QmtDataError(f"{path.name}: missing QD universe columns")
        seen_in_file: set[str] = set()
        for row_number, row in enumerate(reader, start=2):
            instrument = (row.get("代码") or "").strip().upper()
            if not instrument:
                raise QmtDataError(f"{path.name} row {row_number}: missing instrument")
            if instrument in seen_in_file:
                raise QmtDataError(f"{path.name}: duplicate instrument {instrument}")
            seen_in_file.add(instrument)
            try:
                amount = float((row.get("成交额(千元)") or "").strip()) * 1000
            except ValueError as exc:
                raise QmtDataError(f"{path.name} row {row_number}: invalid amount") from exc
            if amount <= 0:
                continue
            counts[instrument] += 1
            amount_sums[instrument] += amount

    metadata: dict[str, tuple[str, date]] = {}
    unknown_listing_date_records = 0
    reader = _reader(fundamental_file)
    required = {"代码", "名称", "上市日期"}
    if not reader.fieldnames or not required <= set(reader.fieldnames):
        raise QmtDataError(f"{fundamental_file.name}: missing QD fundamental columns")
    for row_number, row in enumerate(reader, start=2):
        instrument = (row.get("代码") or "").strip().upper()
        name = (row.get("名称") or "").strip().upper()
        raw_listed = (row.get("上市日期") or "").strip()
        if raw_listed in {"", "0"}:
            unknown_listing_date_records += 1
            continue
        try:
            listed = date(int(raw_listed[:4]), int(raw_listed[4:6]), int(raw_listed[6:8]))
        except (ValueError, IndexError) as exc:
            raise QmtDataError(
                f"{fundamental_file.name} row {row_number}: invalid listing date"
            ) from exc
        metadata[instrument] = (name, listed)

    complete = [instrument for instrument, count in counts.items() if count == len(daily_files)]
    eligible = [
        instrument
        for instrument in complete
        if instrument in metadata
        and "ST" not in metadata[instrument][0]
        and metadata[instrument][1] <= start
    ]
    ranked = sorted(
        eligible,
        key=lambda instrument: (
            -amount_sums[instrument] / counts[instrument],
            instrument,
        ),
    )
    if len(ranked) < top_n:
        raise QmtDataError(f"only {len(ranked)} QD instruments satisfy the universe contract")
    selected = tuple(ranked[:top_n])
    return QdUniverseSelection(
        method_version=QD_UNIVERSE_METHOD_VERSION,
        source_snapshot_sha256=snapshot.snapshot_sha256,
        train_start=start.isoformat(),
        train_end=end.isoformat(),
        selection_date=date(
            int(fundamental_file.stem[:4]),
            int(fundamental_file.stem[4:6]),
            int(fundamental_file.stem[6:]),
        ).isoformat(),
        trading_sessions=len(daily_files),
        top_n=top_n,
        require_complete_history=True,
        exclude_st=True,
        require_listed_before_train_start=True,
        candidates_seen=len(counts),
        complete_history_candidates=len(complete),
        unknown_listing_date_records=unknown_listing_date_records,
        eligible_candidates=len(eligible),
        instruments=selected,
        mean_daily_amount_cny={
            instrument: amount_sums[instrument] / counts[instrument]
            for instrument in selected
        },
    )


def _write(path: Path, content: str) -> str:
    path.write_text(content, encoding="utf-8", newline="\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def write_qd_universe(
    selection: QdUniverseSelection, output_dir: str | Path
) -> QdUniverseArtifacts:
    directory = Path(output_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "qd-universe.json"
    markdown_path = directory / "qd-universe.md"
    stock_file_path = directory / "qd-universe.txt"
    json_content = selection.to_json() + "\n"
    markdown_content = selection.to_markdown()
    stock_content = "\n".join(selection.instruments) + "\n"
    return QdUniverseArtifacts(
        json_path=json_path,
        markdown_path=markdown_path,
        stock_file_path=stock_file_path,
        json_sha256=_write(json_path, json_content),
        markdown_sha256=_write(markdown_path, markdown_content),
        stock_file_sha256=_write(stock_file_path, stock_content),
    )
