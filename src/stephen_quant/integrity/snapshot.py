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
