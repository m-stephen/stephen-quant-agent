from __future__ import annotations

import gzip
import hashlib
import json
import sqlite3
import subprocess
import zipfile
import zlib
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from .models import QmtDataError

RAW_ARCHIVE = "raw_archive"
EXTRACTED_FROM_ARCHIVE = "extracted_from_archive"
SOURCE_UNCOMPRESSED = "source_uncompressed"
PROJECT_GENERATED = "project_generated"
UNKNOWN_REVIEW = "unknown_review"
ARCHIVE_SUFFIXES = {".zip", ".7z", ".rar"}
SOURCE_SUFFIXES = {".csv", ".xlsx", ".xls", ".txt", ".json", ".jsonl"}
GENERATED_MARKERS = ("manifest", "report", "backtest", "normalized", "converted", "stephen_quant")
ARCHIVE_INSPECTOR_VERSION = 2


@dataclass(frozen=True)
class InventoryEntry:
    relative_path: str
    size_bytes: int
    mtime_ns: int
    sha256: str
    crc32: str
    status: str
    archive_relative_path: str | None = None
    archive_member_path: str | None = None
    match_method: str | None = None


def _sha256(path: Path) -> tuple[str, str]:
    digest = hashlib.sha256()
    crc = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            crc = zlib.crc32(chunk, crc)
    return digest.hexdigest(), f"{crc & 0xFFFFFFFF:08x}"


def _read_inventory_manifest(path: Path) -> dict[str, object]:
    try:
        if path.name.endswith(".json.gz"):
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                return json.load(handle)
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, json.JSONDecodeError) as exc:
        raise QmtDataError(f"cannot read inventory manifest: {path.name}") from exc


def cold_archive_inventories(
    output_dir: str | Path,
    *,
    retain_hot: int = 1,
    remove_verified_json: bool = False,
) -> dict[str, object]:
    """Losslessly gzip historical inventory JSON after byte-for-byte verification."""
    if retain_hot < 1:
        raise QmtDataError("retain_hot must be at least one")
    target = Path(output_dir).expanduser().resolve()
    manifests = sorted(
        target.glob("asset-inventory-*.json"),
        key=lambda item: (item.stat().st_mtime_ns, item.name),
        reverse=True,
    )
    archived: list[dict[str, object]] = []
    for source in manifests[retain_hot:]:
        compressed = source.with_suffix(source.suffix + ".gz")
        temporary = compressed.with_suffix(compressed.suffix + ".pending")
        source_sha = _sha256(source)[0]
        digest = hashlib.sha256()
        try:
            with (
                source.open("rb") as input_handle,
                temporary.open("xb") as raw_output,
                gzip.GzipFile(
                    filename="", mode="wb", fileobj=raw_output, compresslevel=9, mtime=0
                ) as output_handle,
            ):
                for chunk in iter(lambda: input_handle.read(1024 * 1024), b""):
                    output_handle.write(chunk)
            with gzip.open(temporary, "rb") as verification:
                for chunk in iter(lambda: verification.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != source_sha:
                raise QmtDataError(f"inventory cold-storage verification failed: {source.name}")
            if compressed.exists():
                if _sha256(compressed)[0] != _sha256(temporary)[0]:
                    raise QmtDataError(f"inventory cold-storage target conflict: {compressed.name}")
                temporary.unlink()
            else:
                temporary.replace(compressed)
            archived.append(
                {
                    "source_name": source.name,
                    "source_sha256": source_sha,
                    "source_size_bytes": source.stat().st_size,
                    "compressed_name": compressed.name,
                    "compressed_sha256": _sha256(compressed)[0],
                    "compressed_size_bytes": compressed.stat().st_size,
                    "verified": True,
                }
            )
            if remove_verified_json:
                source.unlink()
        finally:
            temporary.unlink(missing_ok=True)
    return {
        "status": "COMPLETED",
        "retain_hot": retain_hot,
        "remove_verified_json": remove_verified_json,
        "archived": archived,
        "source_bytes": sum(int(item["source_size_bytes"]) for item in archived),
        "compressed_bytes": sum(int(item["compressed_size_bytes"]) for item in archived),
    }


class HashCache:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS file_hashes ("
            "relative_path TEXT PRIMARY KEY, size_bytes INTEGER NOT NULL, mtime_ns INTEGER NOT NULL, "
            "sha256 TEXT NOT NULL, crc32 TEXT NOT NULL)"
        )

    def hash(self, root: Path, path: Path, *, rehash: bool) -> tuple[str, str, bool]:
        relative = path.relative_to(root).as_posix()
        stat = path.stat()
        if not rehash:
            row = self.connection.execute(
                "SELECT sha256, crc32 FROM file_hashes WHERE relative_path=? AND size_bytes=? AND mtime_ns=?",
                (relative, stat.st_size, stat.st_mtime_ns),
            ).fetchone()
            if row:
                return str(row[0]), str(row[1]), True
        sha, crc = _sha256(path)
        self.connection.execute(
            "INSERT OR REPLACE INTO file_hashes VALUES (?, ?, ?, ?, ?)",
            (relative, stat.st_size, stat.st_mtime_ns, sha, crc),
        )
        self.connection.commit()
        return sha, crc, False

    def close(self) -> None:
        self.connection.close()


def _parse_seven_zip_slt(output: str) -> list[tuple[str, int, str | None]]:
    blocks: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in output.splitlines():
        if not line.strip():
            if current:
                blocks.append(current)
                current = {}
            continue
        if " = " in line:
            key, value = line.split(" = ", 1)
            current[key.strip()] = value.strip()
    if current:
        blocks.append(current)
    members: list[tuple[str, int, str | None]] = []
    for block in blocks:
        member = block.get("Path")
        attributes = block.get("Attributes")
        if not member or attributes is None or "D" in attributes:
            continue
        try:
            size = int(block.get("Size", "-1"))
        except ValueError:
            size = -1
        crc = block.get("CRC") or None
        members.append((member.replace("\\", "/"), size, crc.lower() if crc else None))
    return members


def _archive_members(
    path: Path, seven_zip_executable: Path | None = None
) -> list[tuple[str, int, str | None]]:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            return [
                (item.filename.replace("\\", "/"), item.file_size, f"{item.CRC:08x}")
                for item in archive.infolist()
                if not item.is_dir()
            ]
    if path.suffix.lower() == ".7z":
        if seven_zip_executable is None or not seven_zip_executable.is_file():
            raise QmtDataError("7z archive requires a configured qd_7zip_executable")
        try:
            completed = subprocess.run(
                [
                    str(seven_zip_executable),
                    "l",
                    "-slt",
                    "-sccUTF-8",
                    str(path),
                ],
                check=True,
                capture_output=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise QmtDataError(f"cannot inspect 7z archive {path.name}: {exc}") from exc
        return _parse_seven_zip_slt(completed.stdout.decode("utf-8", errors="replace"))
    try:
        names = subprocess.run(
            ["tar", "-tf", str(path)], check=True, capture_output=True, text=True, errors="replace"
        ).stdout.splitlines()
        verbose = subprocess.run(
            ["tar", "-tvf", str(path)], check=True, capture_output=True, text=True, errors="replace"
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise QmtDataError(f"cannot inspect archive {path.name}: {exc}") from exc
    result: list[tuple[str, int, str | None]] = []
    for name, line in zip(names, verbose, strict=False):
        parts = line.split()
        if name.endswith("/") or len(parts) < 5:
            continue
        try:
            size = int(parts[4])
        except ValueError:
            size = -1
        result.append((name.replace("\\", "/"), size, None))
    return result


def _manifest_hash(
    entries: Iterable[InventoryEntry],
    archive_members: list[dict[str, object]],
    extracted_history: list[dict[str, str]],
    archive_inspector_version: int,
) -> str:
    stable = {
        "entries": [asdict(entry) for entry in entries],
        "archive_members": archive_members,
        "previously_extracted_archive_members": extracted_history,
        "archive_inspector_version": archive_inspector_version,
    }
    payload = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def inventory_assets(
    root: str | Path,
    output_dir: str | Path,
    *,
    rehash_all: bool = False,
    inspect_archives: bool = True,
    seven_zip_executable: str | Path | None = None,
) -> dict[str, object]:
    source_root = Path(root).expanduser().resolve()
    target = Path(output_dir).expanduser().resolve()
    seven_zip = (
        Path(seven_zip_executable).expanduser().resolve() if seven_zip_executable else None
    )
    if not source_root.is_dir():
        raise QmtDataError(f"asset root does not exist: {source_root}")
    if source_root == target or source_root in target.parents:
        raise QmtDataError("inventory output must be outside the read-only source root")
    target.mkdir(parents=True, exist_ok=True)
    files = sorted(
        (path for path in source_root.rglob("*") if path.is_file()),
        key=lambda item: item.relative_to(source_root).as_posix().casefold(),
    )
    if any(path.is_symlink() for path in files):
        raise QmtDataError("symlinks are not accepted in the source inventory")
    cache = HashCache(target / "inventory-cache.sqlite3")
    raw: list[tuple[Path, str, str, bool]] = []
    try:
        for path in files:
            sha, crc, reused = cache.hash(source_root, path, rehash=rehash_all)
            raw.append((path, sha, crc, reused))
    finally:
        cache.close()

    member_index: dict[tuple[str, int], list[tuple[str, str, str | None]]] = defaultdict(list)
    archive_members: list[dict[str, object]] = []
    archive_errors: list[dict[str, str]] = []
    previous_members: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    previous_errors: dict[tuple[str, str], dict[str, str]] = {}
    extracted_history_keys: set[tuple[str, str, str]] = set()
    hot_manifests = list(target.glob("asset-inventory-*.json"))
    previous_manifests = hot_manifests + list(target.glob("asset-inventory-*.json.gz"))
    if previous_manifests:
        try:
            latest_manifest = max(
                hot_manifests or previous_manifests, key=lambda item: item.stat().st_mtime_ns
            )
            previous = _read_inventory_manifest(latest_manifest)
            previous_hashes = {
                str(entry["relative_path"]): str(entry["sha256"])
                for entry in previous.get("entries", [])
            }
            for item in previous.get("archive_members", []):
                key = (str(item["archive_relative_path"]), str(item["archive_sha256"]))
                previous_members[key].append(item)
            if previous.get("archive_inspector_version") == ARCHIVE_INSPECTOR_VERSION:
                for item in previous.get("archive_errors", []):
                    rel = str(item.get("relative_path", ""))
                    if rel in previous_hashes:
                        previous_errors[(rel, previous_hashes[rel])] = item
        except (OSError, KeyError, TypeError, json.JSONDecodeError, QmtDataError):
            previous_members.clear()
            previous_errors.clear()
    for prior_path in previous_manifests:
        try:
            prior = _read_inventory_manifest(prior_path)
            archive_hashes = {
                str(entry["relative_path"]): str(entry["sha256"])
                for entry in prior.get("entries", [])
                if entry.get("status") == RAW_ARCHIVE
            }
            for item in prior.get("previously_extracted_archive_members", []):
                extracted_history_keys.add(
                    (
                        str(item["archive_relative_path"]),
                        str(item["archive_sha256"]),
                        str(item["member_path"]),
                    )
                )
            for entry in prior.get("entries", []):
                if entry.get("status") != EXTRACTED_FROM_ARCHIVE:
                    continue
                archive_rel = str(entry.get("archive_relative_path", ""))
                member_path = str(entry.get("archive_member_path", ""))
                archive_sha = archive_hashes.get(archive_rel)
                if archive_sha and member_path:
                    extracted_history_keys.add((archive_rel, archive_sha, member_path))
        except (OSError, KeyError, TypeError, QmtDataError):
            continue
    if inspect_archives:
        for path, archive_sha, _, _ in raw:
            if path.suffix.lower() not in ARCHIVE_SUFFIXES:
                continue
            rel = path.relative_to(source_root).as_posix()
            cached = previous_members.get((rel, archive_sha))
            if cached:
                archive_members.extend(cached)
                for item in cached:
                    member = str(item["member_path"])
                    size = int(item["member_size_bytes"])
                    crc = item.get("member_crc32")
                    member_index[(PurePosixPath(member).name.casefold(), size)].append(
                        (rel, member, str(crc) if crc is not None else None)
                    )
                continue
            cached_error = previous_errors.get((rel, archive_sha))
            if cached_error:
                archive_errors.append(cached_error)
                continue
            try:
                for member, size, crc in _archive_members(path, seven_zip):
                    member_index[(PurePosixPath(member).name.casefold(), size)].append((rel, member, crc))
                    archive_members.append(
                        {
                            "archive_relative_path": rel,
                            "archive_sha256": archive_sha,
                            "archive_size_bytes": path.stat().st_size,
                            "member_path": member,
                            "member_size_bytes": size,
                            "member_crc32": crc,
                        }
                    )
            except QmtDataError as exc:
                archive_errors.append({"relative_path": rel, "error": str(exc)})

    entries: list[InventoryEntry] = []
    reused_count = 0
    for path, sha, crc, reused in raw:
        reused_count += int(reused)
        rel = path.relative_to(source_root).as_posix()
        suffix = path.suffix.lower()
        archive_rel = member_rel = method = None
        if suffix in ARCHIVE_SUFFIXES:
            status = RAW_ARCHIVE
        else:
            matches = member_index.get((path.name.casefold(), path.stat().st_size), [])
            exact = [match for match in matches if match[2] is None or match[2].lower() == crc]
            if exact:
                archive_rel, member_rel, member_crc = min(exact)
                method = "basename+size+crc32" if member_crc else "basename+size"
                status = EXTRACTED_FROM_ARCHIVE
            elif suffix in {".parquet", ".duckdb"} or any(
                marker in rel.casefold() for marker in GENERATED_MARKERS
            ):
                status = PROJECT_GENERATED
            elif suffix in SOURCE_SUFFIXES:
                status = SOURCE_UNCOMPRESSED
            else:
                status = UNKNOWN_REVIEW
        stat = path.stat()
        entries.append(
            InventoryEntry(
                relative_path=rel,
                size_bytes=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
                sha256=sha,
                crc32=crc,
                status=status,
                archive_relative_path=archive_rel,
                archive_member_path=member_rel,
                match_method=method,
            )
        )

    archive_members.sort(
        key=lambda item: (
            str(item["archive_relative_path"]).casefold(),
            str(item["member_path"]).casefold(),
        )
    )
    archive_hashes = {
        entry.relative_path: entry.sha256 for entry in entries if entry.status == RAW_ARCHIVE
    }
    for entry in entries:
        if entry.status != EXTRACTED_FROM_ARCHIVE:
            continue
        if entry.archive_relative_path and entry.archive_member_path:
            archive_sha = archive_hashes.get(entry.archive_relative_path)
            if archive_sha:
                extracted_history_keys.add(
                    (entry.archive_relative_path, archive_sha, entry.archive_member_path)
                )
    extracted_history = [
        {
            "archive_relative_path": archive_rel,
            "archive_sha256": archive_sha,
            "member_path": member_path,
        }
        for archive_rel, archive_sha, member_path in sorted(extracted_history_keys)
    ]
    snapshot_sha = _manifest_hash(
        entries, archive_members, extracted_history, ARCHIVE_INSPECTOR_VERSION
    )
    counts = Counter(entry.status for entry in entries)
    manifest = {
        "schema_version": 1,
        "archive_inspector_version": ARCHIVE_INSPECTOR_VERSION,
        "seven_zip_configured": seven_zip is not None and seven_zip.is_file(),
        "snapshot_sha256": snapshot_sha,
        "source_root_name": source_root.name,
        "file_count": len(entries),
        "total_size_bytes": sum(entry.size_bytes for entry in entries),
        "status_counts": dict(sorted(counts.items())),
        "hash_cache_reused": reused_count,
        "archive_errors": archive_errors,
        "archive_members": archive_members,
        "previously_extracted_archive_members": extracted_history,
        "entries": [asdict(entry) for entry in entries],
    }
    json_path = target / f"asset-inventory-{snapshot_sha}.json"
    json_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    generated_at = datetime.now(timezone.utc).isoformat()
    lines = [
        "# 数据资产盘点 / Data Asset Inventory",
        "",
        f"- 生成时间 / Generated: `{generated_at}`",
        f"- 快照 / Snapshot: `{snapshot_sha}`",
        f"- 文件数 / Files: `{len(entries)}`",
        f"- 总字节 / Total bytes: `{manifest['total_size_bytes']}`",
        f"- 哈希缓存命中 / Hash cache hits: `{reused_count}`",
        "",
        "| 状态 / Status | 数量 / Count |",
        "|---|---:|",
    ]
    lines.extend(f"| `{key}` | {value} |" for key, value in sorted(counts.items()))
    lines.extend(["", f"源目录只读 / Source root was only read: `{source_root.name}`", ""])
    md_path = target / f"asset-inventory-{snapshot_sha}.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return {
        "snapshot_sha256": snapshot_sha,
        "manifest_path": str(json_path),
        "report_path": str(md_path),
        "file_count": len(entries),
        "total_size_bytes": manifest["total_size_bytes"],
        "status_counts": manifest["status_counts"],
        "hash_cache_reused": reused_count,
        "archive_error_count": len(archive_errors),
    }
