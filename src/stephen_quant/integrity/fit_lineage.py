"""Daily walk-forward model lineage, without a multi-user authorization layer."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from .models import utc_now_iso


@dataclass(frozen=True)
class FitStage:
    stage_id: str
    training_not_before: str
    training_not_after: str
    prediction_start: str
    prediction_end: str


FIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS trial_fit_contracts (
    trial_id TEXT PRIMARY KEY REFERENCES trials(trial_id),
    stages_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trial_model_fits (
    trial_id TEXT NOT NULL REFERENCES trial_fit_contracts(trial_id),
    stage_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    evidence_sha256 TEXT NOT NULL,
    PRIMARY KEY(trial_id, stage_id)
);
"""
for _table in ("trial_fit_contracts", "trial_model_fits"):
    for _action in ("UPDATE", "DELETE"):
        FIT_SCHEMA += f"""
CREATE TRIGGER IF NOT EXISTS {_table}_no_{_action.lower()}
BEFORE {_action} ON {_table}
BEGIN SELECT RAISE(ABORT, 'fit lineage is append-only'); END;
"""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def daily(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError("canonical daily date required")
    return value


def contract_json(stages):
    if stages is None:
        return None  # Legacy only: never infer a fit contract from old scalar columns.
    ordered = sorted(stages, key=lambda s: s.prediction_start)
    if len({s.stage_id for s in ordered}) != len(ordered):
        raise ValueError("duplicate fit stage")
    previous_end = ""
    for s in ordered:
        if not s.stage_id or not s.stage_id.strip():
            raise ValueError("fit stage identity required")
        if not (
            daily(s.training_not_before)
            <= daily(s.training_not_after)
            < daily(s.prediction_start)
            <= daily(s.prediction_end)
        ):
            raise ValueError("invalid fit stage chronology")
        if s.prediction_start <= previous_end:
            raise ValueError("overlapping prediction stages")
        previous_end = s.prediction_end
    return canonical([asdict(s) for s in ordered])


def artifact_digest(path, model):
    raw = Path(path).read_bytes()
    if canonical(json.loads(raw)) != canonical(model):
        raise ValueError("model object differs from artifact bytes")
    return hashlib.sha256(raw).hexdigest()


class FitLineageRegistry:
    """Mixin for ExperimentRegistry. Contract and Trial are created atomically."""

    @staticmethod
    def _declare_fit_contract(conn, trial_id, stages):
        payload = contract_json(stages)
        if payload is not None:
            conn.execute("INSERT INTO trial_fit_contracts VALUES (?,?)", (trial_id, payload))

    @staticmethod
    def _replay_fit_contract(conn, trial_id, stages):
        row = conn.execute(
            "SELECT stages_json FROM trial_fit_contracts WHERE trial_id=?", (trial_id,)
        ).fetchone()
        if (row[0] if row else None) != contract_json(stages):
            raise ValueError("deterministic fit contract identity collision")

    @staticmethod
    def _complete_fits(conn, trial_id):
        row = conn.execute(
            "SELECT stages_json FROM trial_fit_contracts WHERE trial_id=?", (trial_id,)
        ).fetchone()
        if row is None:
            return  # Compatibility, not a claim that a legacy Trial is verified.
        expected = {s["stage_id"] for s in json.loads(row[0])}
        actual = {
            r[0]
            for r in conn.execute(
                "SELECT stage_id FROM trial_model_fits WHERE trial_id=?", (trial_id,)
            )
        }
        if actual != expected:
            raise ValueError("incomplete native model fit lineage")

    def record_model_fit(self, trial_id, stage_id, *, model, artifact_path):
        """Bind fit_year's actual sessions and model bytes; no caller-supplied hash."""
        sessions = model["training_signal_sessions"]
        if not sessions or sessions != sorted(set(sessions)):
            raise ValueError("ordered unique actual training signal sessions required")
        for session in sessions:
            daily(session)
        cutoff, label_end = daily(model["fit_cutoff"]), daily(model["maximum_label_end"])
        if not sessions[-1] < label_end <= cutoff:
            raise ValueError("training labels must mature before fit cutoff")
        if model["training_signal_dates"] != len(sessions):
            raise ValueError("actual training session count mismatch")
        model_sha = artifact_digest(artifact_path, model)
        with self.connect() as conn:
            row = conn.execute(
                "SELECT c.stages_json,t.result_json,e.code_version,s.snapshot_sha256 "
                "FROM trial_fit_contracts c JOIN trials t USING(trial_id) "
                "JOIN experiments e USING(experiment_id) "
                "JOIN data_snapshots s ON s.snapshot_id=e.dataset_snapshot_id "
                "WHERE trial_id=?",
                (trial_id,),
            ).fetchone()
            if row is None:
                raise ValueError("native fit contract required")
            stage = next((s for s in json.loads(row[0]) if s["stage_id"] == stage_id), None)
            if stage is None:
                raise ValueError("undeclared fit stage")
            if (
                not stage["training_not_before"]
                <= sessions[0]
                <= cutoff
                <= stage["training_not_after"]
            ):
                raise ValueError("actual training outside registered bounds")
            if model["year"] != int(stage["prediction_start"][:4]):
                raise ValueError("model prediction year mismatch")
            evidence = {
                "stage": stage,
                "training_signal_sessions": sessions,
                "training_start": sessions[0],
                "training_end": cutoff,
                "maximum_label_end": label_end,
                "artifact_sha256": model_sha,
                "model_content_sha256": digest(model),
                "snapshot_sha256": row[3],
                "code_version": row[2],
            }
            payload = canonical(evidence)
            old = conn.execute(
                "SELECT evidence_json FROM trial_model_fits WHERE trial_id=? AND stage_id=?",
                (trial_id, stage_id),
            ).fetchone()
            if old is not None:
                if old[0] != payload:
                    raise ValueError("immutable fit identity collision")
                return evidence
            if row[1] is not None:
                raise ValueError("cannot attach fit after Trial completion")
            conn.execute(
                "INSERT INTO trial_model_fits VALUES (?,?,?,?,?)",
                (trial_id, stage_id, utc_now_iso(), payload, digest(evidence)),
            )
        return evidence

    def fit_lineage(self, trial_id):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT stages_json FROM trial_fit_contracts WHERE trial_id=?", (trial_id,)
            ).fetchone()
            if row is None:
                raise ValueError("native fit contract required")
            self._complete_fits(conn, trial_id)
            fits = [
                json.loads(r[0])
                for r in conn.execute(
                    "SELECT evidence_json FROM trial_model_fits WHERE trial_id=? ORDER BY stage_id",
                    (trial_id,),
                )
            ]
        return {"stages": json.loads(row[0]), "fits": fits, "sha256": digest(fits)}

    def assert_prediction_fit(
        self, trial_id, *, model, artifact_path, prediction_date, signal_date
    ):
        """Called before features/targets: verify exact runtime model and temporal scope."""
        daily(prediction_date)
        daily(signal_date)
        lineage = self.fit_lineage(trial_id)
        fit = next(
            (
                f
                for f in lineage["fits"]
                if f["stage"]["prediction_start"] <= prediction_date <= f["stage"]["prediction_end"]
            ),
            None,
        )
        if fit is None:
            raise ValueError("no fitted stage covers prediction date")
        if not fit["training_end"] < signal_date < prediction_date:
            raise ValueError("fit and signal must strictly precede prediction")
        if (
            artifact_digest(artifact_path, model) != fit["artifact_sha256"]
            or digest(model) != fit["model_content_sha256"]
        ):
            raise ValueError("runtime model differs from registered fit")
        return fit["stage"]["stage_id"]
