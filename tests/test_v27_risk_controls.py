from __future__ import annotations

import json
import math
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest

from stephen_quant.cli import main
from stephen_quant.workflows.v27_risk_controls import (
    PRICE_CONTROL_SCHEMA,
    CandidateControlRow,
    PriceRiskObservation,
    build_causal_price_exposures,
    fit_fold_local_residualizer,
    fit_fold_local_risk_state,
    load_v27_m2_config,
    residualize_heldout,
    run_v27_m2_engineering_audit,
    transform_heldout_risk_exposures,
    transform_training_risk_exposures,
    verify_v27_m2_replay,
)

CONFIG = "configs/v2.7-m2-price-risk.json"
SNAPSHOT = "9" * 64


def _observations(days: int = 155) -> tuple[PriceRiskObservation, ...]:
    rows: list[PriceRiskObservation] = []
    market = 100.0
    closes = {"000001.SZ": 20.0, "600000.SH": 12.0}
    for offset in range(days):
        current = date(2022, 1, 1) + timedelta(days=offset)
        market_return = 0.001 + 0.003 * math.sin(offset / 7)
        market *= 1 + market_return
        for index, instrument in enumerate(closes):
            stock_return = (0.8 + index * 0.5) * market_return + 0.002 * math.cos(offset / (5 + index))
            closes[instrument] *= 1 + stock_return
            rows.append(
                PriceRiskObservation(
                    instrument,
                    f"{current.isoformat()}T15:00:00+08:00",
                    closes[instrument],
                    50_000_000.0 + offset * 100_000 + index * 1_000_000,
                    market,
                )
            )
    return tuple(rows)


def _raw():
    config = load_v27_m2_config(CONFIG)
    return build_causal_price_exposures(_observations(), config.risk), config


def test_price_exposures_are_strictly_causal() -> None:
    observations = list(_observations())
    config = load_v27_m2_config(CONFIG)
    original = build_causal_price_exposures(observations, config.risk)
    target = observations[-2]
    observations[-2] = replace(target, close=target.close * 10, amount=target.amount * 10)
    changed = build_causal_price_exposures(observations, config.risk)
    key = (target.instrument, target.decision_at)
    left = next(row for row in original if (row.instrument, row.decision_at) == key)
    right = next(row for row in changed if (row.instrument, row.decision_at) == key)
    assert left == right
    assert left.history_end_at < left.decision_at
    assert left.feature_names == PRICE_CONTROL_SCHEMA


def test_fold_fit_is_unchanged_by_heldout_values() -> None:
    raw, config = _raw()
    split = sorted({row.decision_at for row in raw})[-10]
    state = fit_fold_local_risk_state(
        raw,
        training_start=raw[0].decision_at,
        training_end=split,
        source_snapshot_sha256=SNAPSHOT,
        config=config.risk,
    )
    changed = tuple(
        replace(row, values=tuple(value * 1_000 for value in row.values))
        if row.decision_at > split
        else row
        for row in raw
    )
    repeated = fit_fold_local_risk_state(
        changed,
        training_start=raw[0].decision_at,
        training_end=split,
        source_snapshot_sha256=SNAPSHOT,
        config=config.risk,
    )
    assert repeated == state
    heldout = [row for row in raw if row.decision_at > split]
    transformed = transform_heldout_risk_exposures(state, heldout)
    assert transformed and all(row.fit_state_sha256 == state.state_sha256 for row in transformed)


def test_fold_transform_rejects_leakage_and_schema_change() -> None:
    raw, config = _raw()
    split = sorted({row.decision_at for row in raw})[-10]
    state = fit_fold_local_risk_state(
        raw,
        training_start=raw[0].decision_at,
        training_end=split,
        source_snapshot_sha256=SNAPSHOT,
        config=config.risk,
    )
    with pytest.raises(ValueError, match="training-time"):
        transform_heldout_risk_exposures(state, [raw[0]])
    broken = replace(raw[-1], feature_names=("wrong",), values=(1.0,))
    with pytest.raises(ValueError, match="schema"):
        transform_heldout_risk_exposures(state, [broken])
    tampered = replace(state, medians=tuple(value + 1 for value in state.medians))
    with pytest.raises(ValueError, match="hash mismatch"):
        transform_heldout_risk_exposures(tampered, [raw[-1]])


def test_residualizer_is_fold_local_and_never_alpha_court_eligible() -> None:
    raw, config = _raw()
    dates = sorted({row.decision_at for row in raw})
    split = dates[-10]
    state = fit_fold_local_risk_state(
        raw,
        training_start=raw[0].decision_at,
        training_end=split,
        source_snapshot_sha256=SNAPSHOT,
        config=config.risk,
    )
    training_raw = [row for row in raw if row.decision_at <= split]
    heldout_raw = [row for row in raw if row.decision_at > split]
    training = transform_training_risk_exposures(state, training_raw)
    heldout = transform_heldout_risk_exposures(state, heldout_raw)

    def candidate(row) -> float:
        return 0.4 + sum((index + 1) * value for index, value in enumerate(row.values))

    train_rows = [CandidateControlRow(row.instrument, row.decision_at, candidate(row), row) for row in training]
    residualizer = fit_fold_local_residualizer(
        train_rows,
        candidate_name="synthetic_conformance_only",
        training_start=state.training_start,
        training_end=state.training_end,
        risk_state_sha256=state.state_sha256,
        ridge=config.risk.ridge,
    )
    assert residualizer.model_scope == "PARTIAL_RISK_MODEL_ONLY"
    assert residualizer.alpha_court_eligible is False
    test_rows = [CandidateControlRow(row.instrument, row.decision_at, candidate(row), row) for row in heldout]
    residuals = residualize_heldout(residualizer, test_rows)
    assert residuals and max(abs(value) for _, _, value in residuals) < 1e-5
    with pytest.raises(ValueError, match="hash mismatch"):
        residualize_heldout(replace(residualizer, coefficients=(0.0,) * 6), test_rows)


def test_m2_audit_is_partial_and_label_free(tmp_path: Path) -> None:
    report, artifacts = run_v27_m2_engineering_audit(CONFIG, tmp_path)
    assert report.decision == "M2_PARTIAL_RISK_MODEL_READY"
    assert report.full_risk_model_status == "DATA_NOT_RESEARCH_READY"
    assert report.alpha_court_eligible is False
    assert report.new_inferential_trials == 0
    assert report.cumulative_inferential_trials == 48
    assert report.candidate_return_observations == 0
    assert report.directory_enumerations == 0
    assert report.consumed_window_accesses == 0
    assert report.sealed_window_accesses == 0
    assert verify_v27_m2_replay(artifacts.replay_manifest_path).passed


def test_m2_config_cannot_expand_m1_authorization(tmp_path: Path) -> None:
    payload = json.loads(Path(CONFIG).read_text(encoding="utf-8"))
    payload["expected_m1_config_sha256"] = "0" * 64
    payload["m1_config"] = str(Path("configs/v2.7-m1-pit-readiness.json").resolve())
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="frozen M1"):
        load_v27_m2_config(path)


def test_m2_replay_detects_tampering(tmp_path: Path) -> None:
    _, artifacts = run_v27_m2_engineering_audit(CONFIG, tmp_path)
    artifacts.markdown_en_path.write_text("changed", encoding="utf-8")
    replay = verify_v27_m2_replay(artifacts.replay_manifest_path)
    assert not replay.passed
    assert artifacts.markdown_en_path.name in replay.mismatches


def test_m2_cli_audit_and_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["stephen-quant", "v2-risk-controls", "--config", CONFIG, "--output", str(tmp_path)],
    )
    main()
    audit = json.loads(capsys.readouterr().out)
    assert audit["report"]["decision"] == "M2_PARTIAL_RISK_MODEL_READY"
    monkeypatch.setattr(
        "sys.argv",
        [
            "stephen-quant",
            "v2-risk-controls",
            "--mode",
            "replay",
            "--replay-manifest",
            audit["replay_manifest_path"],
        ],
    )
    main()
    assert json.loads(capsys.readouterr().out)["passed"] is True


def test_m2_rejects_duplicate_observations() -> None:
    config = load_v27_m2_config(CONFIG)
    row = _observations(1)[0]
    with pytest.raises(ValueError, match="duplicate"):
        build_causal_price_exposures([row, row], config.risk)


def test_m2_rejects_nonfinite_values() -> None:
    config = load_v27_m2_config(CONFIG)
    row = replace(_observations(1)[0], close=float("nan"))
    with pytest.raises(ValueError, match="finite"):
        build_causal_price_exposures([row], config.risk)


def test_m2_rejects_inconsistent_market_series() -> None:
    config = load_v27_m2_config(CONFIG)
    rows = list(_observations(1))
    rows[1] = replace(rows[1], market_close=rows[1].market_close + 1)
    with pytest.raises(ValueError, match="market close differs"):
        build_causal_price_exposures(rows, config.risk)


def test_m2_report_hash_is_deterministic(tmp_path: Path) -> None:
    first, _ = run_v27_m2_engineering_audit(CONFIG, tmp_path / "a")
    second, _ = run_v27_m2_engineering_audit(CONFIG, tmp_path / "b")
    assert first.decision_sha256 == second.decision_sha256
