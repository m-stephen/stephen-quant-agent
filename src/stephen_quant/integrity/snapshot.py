from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class SnapshotFile:
    path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class SnapshotManifest:
    root: str
    files: tuple[SnapshotFile, ...]
    snapshot_sha256: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "root": self.root,
                "files": [asdict(item) for item in self.files],
                "snapshot_sha256": self.snapshot_sha256,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file():
            yield path


def build_snapshot_manifest(root: str | Path) -> SnapshotManifest:
    root_path = Path(root).expanduser().resolve()
    if not root_path.exists() or not root_path.is_dir():
        raise ValueError(f"Snapshot root is not a directory: {root_path}")

    files: list[SnapshotFile] = []
    snapshot_digest = hashlib.sha256()

    for path in _iter_files(root_path):
        relative = path.relative_to(root_path).as_posix()
        file_hash = _sha256_file(path)
        size = path.stat().st_size
        item = SnapshotFile(path=relative, sha256=file_hash, size_bytes=size)
        files.append(item)
        snapshot_digest.update(relative.encode("utf-8"))
        snapshot_digest.update(b"\0")
        snapshot_digest.update(file_hash.encode("ascii"))
        snapshot_digest.update(b"\0")
        snapshot_digest.update(str(size).encode("ascii"))
        snapshot_digest.update(b"\n")

    return SnapshotManifest(
        root=str(root_path),
        files=tuple(files),
        snapshot_sha256=snapshot_digest.hexdigest(),
    )


def build_file_snapshot_manifest(file: str | Path) -> SnapshotManifest:
    """Freeze exactly one source file without hashing unrelated sibling files."""

    file_path = Path(file).expanduser().resolve()
    if not file_path.exists() or not file_path.is_file():
        raise ValueError(f"Snapshot source is not a file: {file_path}")
    root_path = file_path.parent
    relative = file_path.name
    file_hash = _sha256_file(file_path)
    size = file_path.stat().st_size
    snapshot_digest = hashlib.sha256()
    snapshot_digest.update(relative.encode("utf-8"))
    snapshot_digest.update(b"\0")
    snapshot_digest.update(file_hash.encode("ascii"))
    snapshot_digest.update(b"\0")
    snapshot_digest.update(str(size).encode("ascii"))
    snapshot_digest.update(b"\n")
    return SnapshotManifest(
        root=str(root_path),
        files=(SnapshotFile(path=relative, sha256=file_hash, size_bytes=size),),
        snapshot_sha256=snapshot_digest.hexdigest(),
    )


def build_selected_files_snapshot_manifest(
    root: str | Path,
    files: Iterable[str | Path],
) -> SnapshotManifest:
    """Freeze an explicit file set without hashing unrelated sibling data."""

    root_path = Path(root).expanduser().resolve()
    if not root_path.exists() or not root_path.is_dir():
        raise ValueError(f"Snapshot root is not a directory: {root_path}")
    selected = sorted({Path(item).expanduser().resolve() for item in files})
    if not selected:
        raise ValueError("Snapshot file selection cannot be empty")

    items: list[SnapshotFile] = []
    snapshot_digest = hashlib.sha256()
    for path in selected:
        try:
            relative = path.relative_to(root_path).as_posix()
        except ValueError as exc:
            raise ValueError(f"Snapshot file is outside root: {path}") from exc
        if not path.is_file():
            raise ValueError(f"Snapshot source is not a file: {path}")
        file_hash = _sha256_file(path)
        size = path.stat().st_size
        items.append(SnapshotFile(path=relative, sha256=file_hash, size_bytes=size))
        snapshot_digest.update(relative.encode("utf-8"))
        snapshot_digest.update(b"\0")
        snapshot_digest.update(file_hash.encode("ascii"))
        snapshot_digest.update(b"\0")
        snapshot_digest.update(str(size).encode("ascii"))
        snapshot_digest.update(b"\n")
    return SnapshotManifest(
        root=str(root_path),
        files=tuple(items),
        snapshot_sha256=snapshot_digest.hexdigest(),
    )
