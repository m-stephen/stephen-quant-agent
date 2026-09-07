"""Executable scope, identity and provenance contracts; no real-data loader."""

from __future__ import annotations

import hashlib
import json
import math
import platform
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from ..search_power_dsl import SearchCandidate, SearchField

VERSION = "12.0.0"
HISTORICAL_RAW_ATTEMPTS = 3733
SCENARIOS = ("linear", "interaction", "correlated_null", "regime_null")
FIELDS = ("price_state", "flow_state", "liquidity_state", "event_state")
ROLES = ("risk_only", "risk_signal", "signal_only", "shuffle")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def require_hash(value):
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ValueError("canonical SHA-256 required")
    return value


@dataclass(frozen=True)
class ResetSpec:
    version: str = VERSION
    source_kind: str = "generated_synthetic_only"
    scenarios: tuple[str, ...] = SCENARIOS
    looks: tuple[int, ...] = (100, 200, 500)
    calibration_error: float = 0.05
    power_min: float = 0.80
    path_fwer_max: float = 0.05
    costs_bps: tuple[int, ...] = (0, 82, 164)
    capital_cny: int = 3_000_000
    assets: int = 24
    sessions: int = 220
    train_end: int = 95
    evaluation_start: int = 100
    horizons: tuple[int, ...] = (5, 10)
    max_structures: int = 48
    active_mean_min: float = 0.0001
    active_t_min: float = 2.5
    hac_lag: int = 10
    max_seconds: int = 14400
    historical_raw_attempts: int = HISTORICAL_RAW_ATTEMPTS
    real_label_authorized: bool = False
    automatic_next_epoch: bool = False

    def validate(self):
        # This release deliberately has no configurable real-data/provider path.
        frozen = {
            "version": VERSION,
            "source_kind": "generated_synthetic_only",
            "scenarios": SCENARIOS,
            "costs_bps": (0, 82, 164),
            "capital_cny": 3_000_000,
            "assets": 24,
            "sessions": 220,
            "train_end": 95,
            "evaluation_start": 100,
            "horizons": (5, 10),
            "max_structures": 48,
            "historical_raw_attempts": HISTORICAL_RAW_ATTEMPTS,
            "real_label_authorized": False,
            "automatic_next_epoch": False,
        }
        for key, value in frozen.items():
            if getattr(self, key) != value or type(getattr(self, key)) is not type(value):
                raise ValueError(f"V12 frozen scope differs: {key}")
        if self.looks != (100, 200, 500) or any(type(n) is not int for n in self.looks):
            raise ValueError("frozen finite audit looks required")
        for key, value in (
            ("calibration_error", 0.05),
            ("power_min", 0.80),
            ("path_fwer_max", 0.05),
            ("active_mean_min", 0.0001),
            ("active_t_min", 2.5),
        ):
            if not math.isfinite(getattr(self, key)) or getattr(self, key) != value:
                raise ValueError(f"frozen calibration threshold differs: {key}")
        if type(self.hac_lag) is not int or self.hac_lag != 10:
            raise ValueError("frozen HAC lag required")
        if type(self.max_seconds) is not int or not 60 <= self.max_seconds <= 14400:
            raise ValueError("bounded resource budget required")
        return self

    def payload(self):
        self.validate()
        return asdict(self)

    @property
    def sha256(self):
        return digest(self.payload())

    @classmethod
    def from_dict(cls, raw):
        if not isinstance(raw, dict) or set(raw) != set(asdict(cls())):
            raise ValueError("exact spec schema required; no source/ledger path extensions")
        values = dict(raw)
        for key in ("scenarios", "looks", "costs_bps", "horizons"):
            values[key] = tuple(values[key])
        return cls(**values).validate()


@dataclass(frozen=True)
class Candidate:
    """Small typed DSL. Names and units reuse SearchCandidate/SearchField."""

    operator: str
    fields: tuple[str, ...]
    direction: int
    horizon: int
    parents: tuple[str, ...] = ()

    def validate(self):
        arity = {"rank": 1, "interaction": 2, "gate": 2}
        if self.operator not in arity or len(self.fields) != arity[self.operator]:
            raise ValueError("unsupported typed operator/arity")
        if any(f not in FIELDS for f in self.fields) or len(set(self.fields)) != len(self.fields):
            raise ValueError("unknown or repeated synthetic field")
        if type(self.direction) is not int or self.direction not in (-1, 1):
            raise ValueError("signed direction required")
        if type(self.horizon) is not int or self.horizon not in (5, 10):
            raise ValueError("unsupported horizon")
        for parent in self.parents:
            require_hash(parent)
        return self

    @property
    def expression(self):
        self.validate()
        fields = sorted(self.fields) if self.operator == "interaction" else self.fields
        return f"{self.operator}({','.join(fields)})"

    @property
    def structure_id(self):
        return digest(
            {
                "ast": self.expression,
                "direction": self.direction,
                "horizon": self.horizon,
                "version": VERSION,
            }
        )

    def identity(self, cost, role="risk_signal"):
        if type(cost) is not int or cost not in (0, 82, 164) or role not in ROLES:
            raise ValueError("unknown account identity")
        return digest(
            {
                "structure": self.structure_id,
                "universe": "synthetic-24-asof-common-support",
                "risk": "six-fixed-groups-one-name-each" if role != "signal_only" else "ablation",
                "mapping": "six-equal-long-only",
                "maintenance": "top2-buffer-target-changes",
                "execution": "stateful-next-open-v1",
                "roundtrip_bps": cost,
                "role": role,
                "capital_cny": 3_000_000,
            }
        )

    def shared_candidate(self, cost):
        return SearchCandidate(
            self.identity(cost),
            self.expression,
            "synthetic_reset",
            self.operator,
            tuple(SearchField(f, "generated", "dimensionless") for f in self.fields),
            self.direction,
            self.horizon,
            "synthetic-24-asof-common-support",
            "six-fixed-groups-one-name-each",
            f"HOLD_{self.horizon}_TOP2_BUFFER",
            "NEXT_SESSION_OPEN",
            f"ROUNDTRIP_{cost}BPS",
            1 + len(self.fields),
            self.parents,
        )


def code_manifest():
    """Hash exactly executable dependencies; never enumerate any data directory."""
    root = Path(__file__).resolve().parents[4]
    names = [
        "contracts.py",
        "statistics.py",
        "sources.py",
        "search.py",
        "accounts.py",
        "runner.py",
        "cli.py",
    ]
    paths = ["src/stephen_quant/discovery/research_reset/" + n for n in names]
    paths += [
        "src/stephen_quant/cli.py",
        "src/stephen_quant/baseline/stateful.py",
        "src/stephen_quant/baseline/models.py",
        "src/stephen_quant/discovery/search_power_dsl.py",
        "src/stephen_quant/integrity/registry.py",
        "src/stephen_quant/integrity/models.py",
        "src/stephen_quant/integrity/snapshot.py",
        "src/stephen_quant/integrity/fit_lineage.py",
        "src/stephen_quant/integrity/feature_sources.py",
    ]
    return {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths}


def runtime_manifest():
    return {"python": sys.version, "numpy": np.__version__, "platform": platform.platform()}


def evidence_state(calibration):
    if calibration not in ("NOT_TESTED", "PASS", "FAIL", "INCONCLUSIVE", "ENGINEERING_FAIL"):
        raise ValueError("unknown capability state")
    return {
        "scope": "M0-M2_SYNTHETIC_ONLY",
        "calibration": calibration,
        "real_label_authorized": False,
        "automatic_next_epoch": False,
        "validated_alpha": False,
        "historical_raw_attempts": HISTORICAL_RAW_ATTEMPTS,
        "empirical_trial_delta": 0,
        "court": {
            "status": "NOT_IDENTIFIABLE",
            "dsr": None,
            "pbo": None,
            "placebo": None,
            "reason": "historical comparable matrix unavailable; "
            "economic-search calibration is not full historical Court certification",
        },
        "forward_protocol": "V11.2_UNCHANGED_NOT_EVALUATED",
        "new_domain": "OPTIONAL_NOT_EVALUATED",
    }
