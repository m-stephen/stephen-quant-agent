from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .models import ExperimentSpec, TrialSpec, utc_now_iso
from .snapshot import SnapshotManifest

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS data_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    root TEXT NOT NULL,
    snapshot_sha256 TEXT NOT NULL UNIQUE,
    manifest_json TEXT NOT NULL,
    vendor_version TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS experiments (
    experiment_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    name TEXT NOT NULL,
    hypothesis TEXT NOT NULL,
    dataset_snapshot_id TEXT NOT NULL,
    code_version TEXT NOT NULL,
    search_space TEXT NOT NULL,
    status TEXT NOT NULL,
    FOREIGN KEY(dataset_snapshot_id) REFERENCES data_snapshots(snapshot_id)
);

CREATE TABLE IF NOT EXISTS trials (
    trial_id TEXT PRIMARY KEY,
    trial_number INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    experiment_id TEXT NOT NULL,
    model_name TEXT NOT NULL,
    factor_set TEXT NOT NULL,
    hyperparams TEXT NOT NULL,
    seed INTEGER NOT NULL,
    train_start TEXT NOT NULL,
    train_end TEXT NOT NULL,
    validation_start TEXT NOT NULL,
    validation_end TEXT NOT NULL,
    test_start TEXT NOT NULL,
    test_end TEXT NOT NULL,
    result_json TEXT,
    FOREIGN KEY(experiment_id) REFERENCES experiments(experiment_id),
    UNIQUE(experiment_id, trial_number)
);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    trial_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT,
    FOREIGN KEY(trial_id) REFERENCES trials(trial_id)
);
"""


class ExperimentRegistry:
    def __init__(self, db_path: str | Path = "artifacts/registry.sqlite3") -> None:
        self.db_path = Path(db_path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def register_snapshot(
        self,
        manifest: SnapshotManifest,
        vendor_version: str | None = None,
        notes: str | None = None,
    ) -> str:
        self.initialize()
        snapshot_id = f"snap_{manifest.snapshot_sha256[:16]}"
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO data_snapshots
                (snapshot_id, created_at, root, snapshot_sha256, manifest_json, vendor_version, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    utc_now_iso(),
                    manifest.root,
                    manifest.snapshot_sha256,
                    manifest.to_json(),
                    vendor_version,
                    notes,
                ),
            )
        return snapshot_id

    def create_experiment(self, spec: ExperimentSpec) -> str:
        self.initialize()
        experiment_id = f"exp_{uuid.uuid4().hex[:16]}"
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO experiments
                (experiment_id, created_at, name, hypothesis, dataset_snapshot_id,
                 code_version, search_space, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    experiment_id,
                    utc_now_iso(),
                    spec.name,
                    spec.hypothesis,
                    spec.dataset_snapshot_id,
                    spec.code_version,
                    spec.search_space,
                    spec.status,
                ),
            )
        return experiment_id

    def create_trial(self, spec: TrialSpec) -> tuple[str, int]:
        self.initialize()
        trial_id = f"trial_{uuid.uuid4().hex[:16]}"
        with self.connect() as conn:
            current = conn.execute(
                "SELECT COALESCE(MAX(trial_number), 0) FROM trials WHERE experiment_id = ?",
                (spec.experiment_id,),
            ).fetchone()[0]
            trial_number = int(current) + 1
            conn.execute(
                """
                INSERT INTO trials
                (trial_id, trial_number, created_at, experiment_id, model_name, factor_set,
                 hyperparams, seed, train_start, train_end, validation_start, validation_end,
                 test_start, test_end)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trial_id,
                    trial_number,
                    utc_now_iso(),
                    spec.experiment_id,
                    spec.model_name,
                    spec.factor_set,
                    spec.hyperparams,
                    spec.seed,
                    spec.train_start,
                    spec.train_end,
                    spec.validation_start,
                    spec.validation_end,
                    spec.test_start,
                    spec.test_end,
                ),
            )
        return trial_id, trial_number

    def counts(self) -> dict[str, int]:
        self.initialize()
        with self.connect() as conn:
            return {
                "snapshots": conn.execute("SELECT COUNT(*) FROM data_snapshots").fetchone()[0],
                "experiments": conn.execute("SELECT COUNT(*) FROM experiments").fetchone()[0],
                "trials": conn.execute("SELECT COUNT(*) FROM trials").fetchone()[0],
            }
