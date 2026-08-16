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

CREATE TABLE IF NOT EXISTS factor_candidates (
    candidate_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    trial_id TEXT NOT NULL UNIQUE,
    factor_id TEXT NOT NULL,
    version TEXT NOT NULL,
    formula TEXT NOT NULL,
    fingerprint TEXT NOT NULL UNIQUE,
    proposal_json TEXT NOT NULL,
    status TEXT NOT NULL,
    FOREIGN KEY(trial_id) REFERENCES trials(trial_id)
);

CREATE TABLE IF NOT EXISTS research_campaigns (
    campaign_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    experiment_id TEXT NOT NULL,
    name TEXT NOT NULL,
    schema_budget INTEGER NOT NULL,
    cpcv_budget INTEGER NOT NULL,
    execution_budget INTEGER NOT NULL,
    specification_json TEXT NOT NULL,
    status TEXT NOT NULL,
    FOREIGN KEY(experiment_id) REFERENCES experiments(experiment_id)
);

CREATE TABLE IF NOT EXISTS campaign_proposals (
    proposal_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    campaign_id TEXT NOT NULL,
    proposal_number INTEGER NOT NULL,
    fingerprint TEXT NOT NULL,
    schema_json TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT,
    trial_id TEXT,
    FOREIGN KEY(campaign_id) REFERENCES research_campaigns(campaign_id),
    FOREIGN KEY(trial_id) REFERENCES trials(trial_id),
    UNIQUE(campaign_id, proposal_number)
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

    def trial_count(self, experiment_id: str) -> int:
        """Count every registered attempt, including failed or result-less trials."""

        self.initialize()
        with self.connect() as conn:
            experiment = conn.execute(
                "SELECT 1 FROM experiments WHERE experiment_id = ?", (experiment_id,)
            ).fetchone()
            if experiment is None:
                raise ValueError(f"unknown experiment: {experiment_id}")
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM trials WHERE experiment_id = ?", (experiment_id,)
                ).fetchone()[0]
            )

    def experiment_snapshot_id(self, experiment_id: str) -> str:
        self.initialize()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT dataset_snapshot_id FROM experiments WHERE experiment_id = ?",
                (experiment_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"unknown experiment: {experiment_id}")
            return str(row[0])

    def record_trial_result(self, trial_id: str, result_json: str) -> None:
        """Write a trial outcome once; rejected attempts remain immutable evidence."""

        self.initialize()
        with self.connect() as conn:
            updated = conn.execute(
                "UPDATE trials SET result_json = ? WHERE trial_id = ? AND result_json IS NULL",
                (result_json, trial_id),
            ).rowcount
            if updated != 1:
                raise ValueError(f"unknown or already completed trial: {trial_id}")

    def register_factor_candidate(
        self,
        *,
        trial_id: str,
        factor_id: str,
        version: str,
        formula: str,
        fingerprint: str,
        proposal_json: str,
    ) -> tuple[str, bool]:
        """Persist a proposed candidate or return the existing duplicate."""

        self.initialize()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT candidate_id FROM factor_candidates WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
            if existing is not None:
                return str(existing[0]), False
            candidate_id = f"candidate_{uuid.uuid4().hex[:16]}"
            conn.execute(
                """
                INSERT INTO factor_candidates
                (candidate_id, created_at, trial_id, factor_id, version, formula,
                 fingerprint, proposal_json, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'proposed')
                """,
                (
                    candidate_id,
                    utc_now_iso(),
                    trial_id,
                    factor_id,
                    version,
                    formula,
                    fingerprint,
                    proposal_json,
                ),
            )
            return candidate_id, True

    def candidate_count(self) -> int:
        self.initialize()
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM factor_candidates").fetchone()[0])

    def create_research_campaign(
        self,
        *,
        experiment_id: str,
        name: str,
        schema_budget: int,
        cpcv_budget: int,
        execution_budget: int,
        specification_json: str,
    ) -> str:
        """Freeze one bounded factor-search campaign before proposals are measured."""

        if not name.strip():
            raise ValueError("campaign name cannot be empty")
        if schema_budget < 1:
            raise ValueError("schema_budget must be positive")
        if not 0 <= execution_budget <= cpcv_budget <= schema_budget:
            raise ValueError("campaign budgets must satisfy execution <= cpcv <= schema")
        self.initialize()
        campaign_id = f"campaign_{uuid.uuid4().hex[:16]}"
        with self.connect() as conn:
            if conn.execute(
                "SELECT 1 FROM experiments WHERE experiment_id = ?", (experiment_id,)
            ).fetchone() is None:
                raise ValueError(f"unknown experiment: {experiment_id}")
            conn.execute(
                """
                INSERT INTO research_campaigns
                (campaign_id, created_at, experiment_id, name, schema_budget, cpcv_budget,
                 execution_budget, specification_json, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')
                """,
                (
                    campaign_id,
                    utc_now_iso(),
                    experiment_id,
                    name.strip(),
                    schema_budget,
                    cpcv_budget,
                    execution_budget,
                    specification_json,
                ),
            )
        return campaign_id

    def record_campaign_proposal(
        self,
        *,
        campaign_id: str,
        fingerprint: str,
        schema_json: str,
        decision: str,
        reason: str | None = None,
        trial_id: str | None = None,
    ) -> tuple[str, int]:
        """Record every proposal, including duplicates and static rejections."""

        allowed_decisions = {"generated", "duplicate", "rejected", "shortlisted", "evaluated"}
        if decision not in allowed_decisions:
            raise ValueError(f"unsupported campaign decision: {decision}")
        if not fingerprint or not schema_json:
            raise ValueError("campaign proposal fingerprint and schema cannot be empty")
        self.initialize()
        proposal_id = f"proposal_{uuid.uuid4().hex[:16]}"
        with self.connect() as conn:
            campaign = conn.execute(
                "SELECT schema_budget FROM research_campaigns WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
            if campaign is None:
                raise ValueError(f"unknown campaign: {campaign_id}")
            proposal_number = int(
                conn.execute(
                    "SELECT COALESCE(MAX(proposal_number), 0) FROM campaign_proposals "
                    "WHERE campaign_id = ?",
                    (campaign_id,),
                ).fetchone()[0]
            ) + 1
            if proposal_number > int(campaign[0]):
                raise ValueError(f"campaign schema budget exhausted: {campaign_id}")
            conn.execute(
                """
                INSERT INTO campaign_proposals
                (proposal_id, created_at, campaign_id, proposal_number, fingerprint,
                 schema_json, decision, reason, trial_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal_id,
                    utc_now_iso(),
                    campaign_id,
                    proposal_number,
                    fingerprint,
                    schema_json,
                    decision,
                    reason,
                    trial_id,
                ),
            )
        return proposal_id, proposal_number

    def campaign_summary(self, campaign_id: str) -> dict[str, object]:
        self.initialize()
        with self.connect() as conn:
            campaign = conn.execute(
                """
                SELECT experiment_id, name, schema_budget, cpcv_budget, execution_budget, status
                FROM research_campaigns WHERE campaign_id = ?
                """,
                (campaign_id,),
            ).fetchone()
            if campaign is None:
                raise ValueError(f"unknown campaign: {campaign_id}")
            rows = conn.execute(
                """
                SELECT decision, COUNT(*) AS count FROM campaign_proposals
                WHERE campaign_id = ? GROUP BY decision
                """,
                (campaign_id,),
            ).fetchall()
            decisions = {str(row[0]): int(row[1]) for row in rows}
            return {
                "campaign_id": campaign_id,
                "experiment_id": str(campaign[0]),
                "name": str(campaign[1]),
                "schema_budget": int(campaign[2]),
                "cpcv_budget": int(campaign[3]),
                "execution_budget": int(campaign[4]),
                "status": str(campaign[5]),
                "proposal_count": sum(decisions.values()),
                "decisions": decisions,
            }

    def campaign_fingerprints(self, campaign_id: str) -> dict[str, str]:
        """Return the first persisted proposal for each fingerprint."""

        self.initialize()
        with self.connect() as conn:
            if conn.execute(
                "SELECT 1 FROM research_campaigns WHERE campaign_id = ?", (campaign_id,)
            ).fetchone() is None:
                raise ValueError(f"unknown campaign: {campaign_id}")
            rows = conn.execute(
                """
                SELECT fingerprint, proposal_id FROM campaign_proposals
                WHERE campaign_id = ? ORDER BY proposal_number
                """,
                (campaign_id,),
            ).fetchall()
            result: dict[str, str] = {}
            for row in rows:
                result.setdefault(str(row[0]), str(row[1]))
            return result

    def register_artifact(
        self,
        *,
        trial_id: str,
        kind: str,
        path: str,
        sha256: str | None = None,
    ) -> str:
        """Attach a generated artifact to a registered Trial."""

        if not kind or not path:
            raise ValueError("artifact kind and path cannot be empty")
        artifact_id = f"artifact_{uuid.uuid4().hex[:16]}"
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO artifacts (artifact_id, created_at, trial_id, kind, path, sha256)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (artifact_id, utc_now_iso(), trial_id, kind, path, sha256),
            )
        return artifact_id

    def trial_result(self, trial_id: str) -> str | None:
        self.initialize()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT result_json FROM trials WHERE trial_id = ?", (trial_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"unknown trial: {trial_id}")
            return None if row[0] is None else str(row[0])

    def artifact_count(self, trial_id: str) -> int:
        self.initialize()
        with self.connect() as conn:
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM artifacts WHERE trial_id = ?", (trial_id,)
                ).fetchone()[0]
            )
