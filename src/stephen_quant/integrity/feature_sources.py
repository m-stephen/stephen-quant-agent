"""Native, predeclared shared feature-fit consumers; no authentication layer.

One provider Trial owns label-free model artifacts. Consumer Trials retain their
own supervised fits or explicit no-fit contract. Legacy Trials are unchanged.
"""

from __future__ import annotations

import json

from .fit_lineage import canonical, digest
from .models import utc_now_iso

FEATURE_SOURCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS trial_feature_contracts (
    trial_id TEXT PRIMARY KEY REFERENCES trials(trial_id),
    providers_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trial_feature_bindings (
    trial_id TEXT NOT NULL REFERENCES trial_feature_contracts(trial_id),
    provider_id TEXT NOT NULL REFERENCES trials(trial_id),
    created_at TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    evidence_sha256 TEXT NOT NULL,
    PRIMARY KEY(trial_id, provider_id)
);
"""
for _table in ("trial_feature_contracts", "trial_feature_bindings"):
    for _action in ("UPDATE", "DELETE"):
        FEATURE_SOURCE_SCHEMA += f"""
CREATE TRIGGER IF NOT EXISTS {_table}_no_{_action.lower()}
BEFORE {_action} ON {_table}
BEGIN SELECT RAISE(ABORT, 'feature lineage is append-only'); END;
"""


class FeatureSourceRegistry:
    @staticmethod
    def _provider_evidence(conn, provider_id):
        row = conn.execute(
            "SELECT t.result_json,t.experiment_id,c.providers_json,f.stages_json "
            "FROM trials t JOIN trial_feature_contracts c USING(trial_id) "
            "JOIN trial_fit_contracts f USING(trial_id) WHERE t.trial_id=?",
            (provider_id,),
        ).fetchone()
        if row is None or row[0] is None or json.loads(row[2]) != []:
            raise ValueError("completed leaf feature provider required")
        stages = json.loads(row[3])
        if not stages or any(s.get("fit_kind") != "unsupervised" for s in stages):
            raise ValueError("provider requires native label-free stages")
        fits = [
            json.loads(r[0])
            for r in conn.execute(
                "SELECT evidence_json FROM trial_model_fits WHERE trial_id=? ORDER BY stage_id",
                (provider_id,),
            )
        ]
        if {s["stage_id"] for s in stages} != {f["stage"]["stage_id"] for f in fits}:
            raise ValueError("incomplete provider fits")
        result = json.loads(row[0])
        if (
            not isinstance(result, dict)
            or result.get("feature_provider_ready") is not True
            or result.get("native_fit_lineage_sha256") != digest(fits)
        ):
            raise ValueError("provider outcome must certify its exact completed fit lineage")
        return {
            "provider_id": provider_id,
            "experiment_id": row[1],
            "provider_result_sha256": digest(result),
            "native_fit_lineage_sha256": digest(fits),
            "fit_stage_count": len(fits),
        }

    def declare_feature_sources(self, trial_id, provider_ids):
        if not isinstance(provider_ids, tuple) or len(provider_ids) != len(set(provider_ids)):
            raise ValueError("unique provider tuple required")
        payload = canonical(sorted(provider_ids))
        self.initialize()
        with self.connect() as conn:
            old = conn.execute(
                "SELECT providers_json FROM trial_feature_contracts WHERE trial_id=?", (trial_id,)
            ).fetchone()
            if old is not None:
                if old[0] != payload:
                    raise ValueError("immutable feature contract collision")
                return
            owner = conn.execute(
                "SELECT experiment_id,result_json FROM trials WHERE trial_id=?", (trial_id,)
            ).fetchone()
            if (
                owner is None
                or owner[1] is not None
                or conn.execute(
                    "SELECT 1 FROM trial_model_fits WHERE trial_id=?", (trial_id,)
                ).fetchone()
            ):
                raise ValueError("feature contract must precede consumer fitting")
            for provider in provider_ids:
                row = conn.execute(
                    "SELECT t.experiment_id,t.result_json,c.providers_json,f.stages_json "
                    "FROM trials t JOIN trial_feature_contracts c USING(trial_id) "
                    "JOIN trial_fit_contracts f USING(trial_id) WHERE t.trial_id=?",
                    (provider,),
                ).fetchone()
                if (
                    provider == trial_id
                    or row is None
                    or row[0] != owner[0]
                    or row[1] is not None
                    or json.loads(row[2]) != []
                    or not json.loads(row[3])
                    or any(s.get("fit_kind") != "unsupervised" for s in json.loads(row[3]))
                    or conn.execute(
                        "SELECT 1 FROM trial_model_fits WHERE trial_id=?", (provider,)
                    ).fetchone()
                ):
                    raise ValueError(
                        "unfitted same-experiment leaf provider must be declared first"
                    )
            conn.execute("INSERT INTO trial_feature_contracts VALUES (?,?)", (trial_id, payload))

    @staticmethod
    def _complete_feature_sources(conn, trial_id):
        contract = conn.execute(
            "SELECT providers_json FROM trial_feature_contracts WHERE trial_id=?", (trial_id,)
        ).fetchone()
        if contract is None:
            return  # Explicitly legacy, not evidence of verified feature lineage.
        bindings = conn.execute(
            "SELECT provider_id,evidence_json,evidence_sha256 FROM trial_feature_bindings "
            "WHERE trial_id=? ORDER BY provider_id",
            (trial_id,),
        ).fetchall()
        if [r[0] for r in bindings] != json.loads(contract[0]):
            raise ValueError("incomplete native feature source lineage")
        for provider, payload, expected_sha in bindings:
            evidence = FeatureSourceRegistry._provider_evidence(conn, provider)
            if canonical(evidence) != payload or digest(evidence) != expected_sha:
                raise ValueError("provider feature evidence changed")

    def bind_feature_source(self, trial_id, provider_id):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT c.providers_json,t.result_json,t.experiment_id FROM trial_feature_contracts c "
                "JOIN trials t USING(trial_id) WHERE trial_id=?",
                (trial_id,),
            ).fetchone()
            if row is None or provider_id not in json.loads(row[0]):
                raise ValueError("predeclared feature source required")
            evidence = self._provider_evidence(conn, provider_id)
            if evidence["experiment_id"] != row[2]:
                raise ValueError("different source experiment")
            old = conn.execute(
                "SELECT evidence_json FROM trial_feature_bindings WHERE trial_id=? AND provider_id=?",
                (trial_id, provider_id),
            ).fetchone()
            if old is not None:
                if old[0] != canonical(evidence):
                    raise ValueError("immutable feature evidence collision")
                return evidence
            if (
                row[1] is not None
                or conn.execute(
                    "SELECT 1 FROM trial_model_fits WHERE trial_id=?", (trial_id,)
                ).fetchone()
            ):
                raise ValueError("bind feature source before consumer fitting or completion")
            conn.execute(
                "INSERT INTO trial_feature_bindings VALUES (?,?,?,?,?)",
                (trial_id, provider_id, utc_now_iso(), canonical(evidence), digest(evidence)),
            )
            return evidence

    def feature_sources(self, trial_id):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT providers_json FROM trial_feature_contracts WHERE trial_id=?", (trial_id,)
            ).fetchone()
            if row is None:
                raise ValueError("explicit native feature source contract required")
            self._complete_feature_sources(conn, trial_id)
            bindings = [
                json.loads(r[0])
                for r in conn.execute(
                    "SELECT evidence_json FROM trial_feature_bindings WHERE trial_id=? ORDER BY provider_id",
                    (trial_id,),
                )
            ]
            return {
                "providers": json.loads(row[0]),
                "bindings": bindings,
                "sha256": digest(bindings),
            }
