"""Separate version contracts: never relax or rewrite the consumed V12.0 audit."""

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path

from ..research_reset.contracts import ResetSpec, code_manifest, digest

LENGTHS = (120, 360, 720)
DEVELOPMENT_SEED = 2026090801


@dataclass(frozen=True)
class PowerSpec(ResetSpec):
    version: str = "12.1.0"
    sessions: int = 220
    strength_multiplier: float = 1.0

    def validate(self):
        baseline = asdict(ResetSpec())
        for key, expected in baseline.items():
            if key in ("version", "sessions"):
                continue
            if getattr(self, key) != expected or type(getattr(self, key)) is not type(expected):
                raise ValueError(f"frozen V12.1 field differs: {key}")
        if self.version != "12.1.0" or type(self.sessions) is not int:
            raise ValueError("V12.1 version and session type required")
        if self.sessions - self.evaluation_start not in LENGTHS:
            raise ValueError("predeclared evaluation length required")
        if type(self.strength_multiplier) is not float or self.strength_multiplier not in (
            0.5,
            1.0,
        ):
            raise ValueError("frozen planted strength multiplier required")
        return self


def pipeline_manifest():
    root = Path(__file__).resolve().parents[4]
    names = ["contracts.py", "sources.py", "measurement.py", "runner.py"]
    result = code_manifest()
    for name in names:
        path = "src/stephen_quant/discovery/power_design/" + name
        result[path] = hashlib.sha256((root / path).read_bytes()).hexdigest()
    return result


def seed_for(master, scenario, index):
    return int(digest({"master": master, "scenario": scenario, "index": index})[:15], 16)
