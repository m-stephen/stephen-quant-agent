from pathlib import Path

import pytest

from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.workflows.v48_sealed_alpha_court import (
    FROZEN_END,
    FROZEN_START,
    V48Config,
    _fingerprint,
    _moments,
    v47_trial_sharpes,
)


def test_v48_identity_and_window_are_frozen() -> None:
    config = V48Config()
    config.validate()
    assert (config.holdout_start, config.holdout_end) == (FROZEN_START, FROZEN_END)
    assert len(_fingerprint()) == 64
    with pytest.raises(ValueError, match="sealed"):
        V48Config(holdout_end="2026-08-17").validate()
    with pytest.raises(ValueError, match="frozen"):
        V48Config(buffer_ranks=5).validate()


def test_v47_reference_fails_closed_when_incomplete(tmp_path: Path) -> None:
    registry = ExperimentRegistry(tmp_path / "empty.sqlite3")
    registry.initialize()
    with pytest.raises(ValueError, match="complete 12-Trial"):
        v47_trial_sharpes(registry)


def test_dsr_moments_use_empirical_series() -> None:
    skewness, excess = _moments((-0.02, -0.01, 0.0, 0.01, 0.08))
    assert skewness > 1
    assert excess > -3
