from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from stephen_quant.cli import build_parser
from stephen_quant.workflows import v112_candidate_nursery as v112

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "configs" / "v11-forward-protocol.freeze.json"
EVIDENCE = ROOT / "configs" / "v11.1-candidate-evidence.freeze.json"


def _clock(tmp_path: Path, genesis: str = "2026-09-06T00:00:00Z") -> v112.ClockManifest:
    result = v112.load_or_create_clock(
        tmp_path / "clock.json",
        genesis_at=genesis,
        collector_id="test-collector",
        collector_version="1",
    )
    assert result is not None
    return result


def _receipt(
    source: str,
    *,
    day: str = "2026-09-07",
    candidate_ids: tuple[str, ...] = v112.FORWARD_CANDIDATE_IDS,
    ingested: str = "2026-09-07T08:05:00Z",
    cutoff: str = "2026-09-08T01:30:00Z",
    raw_hash: str = "a" * 64,
    revision_id: str = "r1",
    supersedes: str | None = None,
) -> dict[str, object]:
    return {
        "source": source,
        "trade_date": day,
        "candidate_ids": list(candidate_ids),
        "source_event_time": f"{day}T07:00:00Z",
        "vendor_publish_time": f"{day}T07:30:00Z",
        "first_ingested_at": ingested,
        "started_at": ingested,
        "completed_at": ingested,
        "raw_payload_hash": raw_hash,
        "decision_cutoff": cutoff,
        "revision_id": revision_id,
        "supersedes_revision_id": supersedes,
    }


def _protocol() -> dict[str, object]:
    return v112.load_frozen_protocol(PROTOCOL, "runner")[0]


def _domain(name: str, **overrides: object) -> dict[str, object]:
    field_dictionary = {
        field: field.replace("_", " ") for field in v112.DOMAIN_REQUIRED_FIELDS[name]
    }
    result: dict[str, object] = {
        "name": name,
        "authorization_sustainable": True,
        "stable_entity_ids": True,
        "deterministic_dedup": True,
        "pit_semantics_verified": True,
        "revision_semantics_verified": True,
        "raw_snapshot_sha256": "b" * 64,
        "replay_passed": True,
        "label_interfaces": [],
        "coverage_ratio": 0.9,
        "missing_ratio": 0.1,
        "median_delay_hours": 2.0,
        "revision_completeness": 1.0,
        "source_inventory": ["source-a"],
        "field_dictionary": field_dictionary,
        "timestamp_fields": ["effective_at", "available_at", "ingested_at"],
        "revision_policy": "append_only_supersedes_chain",
        "proposed_hypothesis": "announcement surprise predicts a cross-sectional response",
        "negative_control": "shuffle surprise within publication date",
        "primary_horizon": 20,
        "future_trial_budget": 1,
    }
    result.update(overrides)
    return result


def test_v112_cli_and_frozen_spec_are_explicit() -> None:
    args = build_parser().parse_args(
        ["v11.2-candidate-nursery", "--clock-manifest", "clock.json"]
    )
    assert args.command == "v11.2-candidate-nursery"
    assert not hasattr(args, "candidate_budget")
    assert v112.RAW_GLOBAL_TRIALS == 770
    assert v112.SPEC_HASH == "09d5e702580c534c425581a24e06592df908d5fb1cb6610d85e4cef40517dd68"


def test_v112_protocol_is_exact_reference_not_recomputed_wrapper() -> None:
    payload, reference = v112.load_frozen_protocol(PROTOCOL, "new-runner")
    assert reference.protocol_sha256 == v112.EXPECTED_PROTOCOL_SHA256
    assert reference.artifact_sha256 == "bd05436613e94f4333383f66f68c1c6fa22f0703041fabbe23d5b3282deb546c"
    assert reference.frozen_protocol_code_version != reference.runtime_runner_code_version
    assert tuple(item["candidate_id"] for item in payload["candidates"]) == v112.FORWARD_CANDIDATE_IDS


def test_v112_protocol_tamper_fails_closed(tmp_path: Path) -> None:
    payload = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    payload["portfolio"]["top_k"] = 41
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="artifact bytes changed"):
        v112.load_frozen_protocol(changed, "runner")


def test_v112_nursery_migrates_two_forward_one_clue_and_fifteen_rejections() -> None:
    evidence = v112._load_evidence(EVIDENCE)
    records = v112.build_nursery(_protocol(), evidence)
    assert len(records) == 18
    assert sum(item.candidate_state == "FORWARD_CONFIRMATION_CANDIDATE" for item in records) == 2
    assert sum(item.candidate_state == "RESEARCH_CLUE_SPECIFICATION_DEPENDENT" for item in records) == 1
    assert sum(item.candidate_state == "REJECTED_DEVELOPMENT_EVIDENCE" for item in records) == 15
    assert len({item.candidate_id for item in records}) == 18
    assert all(item.status_history for item in records)


def test_v112_state_transitions_are_one_way_and_v112_cannot_validate() -> None:
    v112.validate_transition("RESEARCH_CLUE", "FORWARD_CONFIRMATION_CANDIDATE")
    with pytest.raises(ValueError, match="backward"):
        v112.validate_transition("REJECTED_DEVELOPMENT_EVIDENCE", "RESEARCH_CLUE")
    with pytest.raises(ValueError, match="cannot emit"):
        v112.validate_transition("FORWARD_CONFIRMATION_CANDIDATE", "VALIDATED_ALPHA")


def test_v112_no_clock_is_explicit_and_reads_no_receipts() -> None:
    runtime = v112.evaluate_forward_runtime(_protocol(), None, [])
    assert runtime.clock_state == "PROSPECTIVE_CLOCK_NOT_ESTABLISHED"
    assert runtime.forward_stage == "FORWARD_COVERAGE_ONLY"
    assert runtime.performance_conclusion is None


def test_v112_clock_cannot_be_redefined(tmp_path: Path) -> None:
    _clock(tmp_path)
    with pytest.raises(ValueError, match="genesis is immutable"):
        v112.load_or_create_clock(
            tmp_path / "clock.json",
            genesis_at="2026-09-07T00:00:00Z",
            collector_id="test-collector",
            collector_version="1",
        )
    with pytest.raises(ValueError, match="collector identity is immutable"):
        v112.load_or_create_clock(
            tmp_path / "clock.json",
            genesis_at=None,
            collector_id="other-collector",
            collector_version="1",
        )


def test_v112_candidate_and_family_calendars_are_separate(tmp_path: Path) -> None:
    clock = _clock(tmp_path)
    receipts = [_receipt("daily"), _receipt("minute", raw_hash="b" * 64)]
    runtime = v112.evaluate_forward_runtime(_protocol(), clock, receipts)
    first, second = v112.FORWARD_CANDIDATE_IDS
    assert runtime.candidate_eligible_calendars[first] == ("2026-09-07",)
    assert runtime.candidate_eligible_calendars[second] == ()
    assert runtime.family_primary_calendar == ()
    assert runtime.forward_stage == "ACTIONABLE_DATES_INSUFFICIENT"


def test_v112_full_source_intersection_makes_one_family_date(tmp_path: Path) -> None:
    receipts = [
        _receipt("daily"),
        _receipt("minute", raw_hash="b" * 64),
        _receipt("chip", candidate_ids=(v112.FORWARD_CANDIDATE_IDS[1],), raw_hash="c" * 64),
    ]
    runtime = v112.evaluate_forward_runtime(_protocol(), _clock(tmp_path), receipts)
    assert runtime.family_primary_calendar == ("2026-09-07",)
    assert runtime.arrival_counts == {"FIRST_SEEN_ACTIONABLE": 3}
    assert runtime.prospective_pbo == "NOT_APPLICABLE"


def test_v112_preexisting_late_revision_duplicate_and_overwrite_are_not_actionable(tmp_path: Path) -> None:
    receipts = [
        _receipt("daily", day="2026-09-05", ingested="2026-09-06T01:00:00Z"),
        _receipt("daily", ingested="2026-09-08T02:00:00Z"),
        _receipt("daily", revision_id="base", ingested="2026-09-07T08:04:00Z"),
        _receipt("daily", revision_id="r2", supersedes="base", raw_hash="b" * 64),
        _receipt("daily", revision_id="r3", raw_hash="c" * 64),
        _receipt("daily", revision_id="r3", raw_hash="c" * 64),
        _receipt("daily", revision_id="r3", raw_hash="d" * 64),
    ]
    runtime = v112.evaluate_forward_runtime(_protocol(), _clock(tmp_path), receipts)
    states = [item.arrival_state for item in runtime.receipt_events]
    assert "PREEXISTING_UNVERIFIED_ARRIVAL" in states
    assert "LATE_NOT_ACTIONABLE" in states
    assert "REVISION_QA_ONLY" in states
    assert "DUPLICATE_REJECTED" in states
    assert "OVERWRITE_REJECTED" in states
    assert all(len(item.receipt_hash) == 64 for item in runtime.receipt_events)


def test_v112_revision_requires_observed_superseded_identity(tmp_path: Path) -> None:
    receipt = _receipt("daily", revision_id="r2", supersedes="missing")
    runtime = v112.evaluate_forward_runtime(_protocol(), _clock(tmp_path), [receipt])
    assert runtime.receipt_events[0].arrival_state == "REVISION_CHAIN_REJECTED"
    assert runtime.candidate_eligible_calendars[v112.FORWARD_CANDIDATE_IDS[0]] == ()


@pytest.mark.parametrize(
    ("days", "expected"),
    [(24, "ACTIONABLE_DATES_INSUFFICIENT"), (25, "FORWARD_RUNTIME_CHECKPOINT"), (126, "FORWARD_INTERIM_DESCRIPTIVE"), (252, "FORWARD_PRIMARY_EVIDENCE_REQUIRED")],
)
def test_v112_family_checkpoint_boundaries(tmp_path: Path, days: int, expected: str) -> None:
    receipts = []
    for index in range(days):
        day = date_from_index(index)
        cutoff = f"{day}T23:00:00Z"
        ingested = f"{day}T08:00:00Z"
        receipts.extend(
            [
                _receipt("daily", day=day, ingested=ingested, cutoff=cutoff, revision_id=f"d-{index}"),
                _receipt("minute", day=day, ingested=ingested, cutoff=cutoff, raw_hash="b" * 64, revision_id=f"m-{index}"),
                _receipt("chip", day=day, candidate_ids=(v112.FORWARD_CANDIDATE_IDS[1],), ingested=ingested, cutoff=cutoff, raw_hash="c" * 64, revision_id=f"c-{index}"),
            ]
        )
    runtime = v112.evaluate_forward_runtime(_protocol(), _clock(tmp_path), receipts)
    assert runtime.forward_stage == expected
    assert runtime.performance_conclusion is None


def date_from_index(index: int) -> str:
    return (date(2026, 9, 7) + timedelta(days=index)).isoformat()


def test_v112_receipts_reject_label_interfaces(tmp_path: Path) -> None:
    receipt = _receipt("daily")
    receipt["forward_return"] = 0.1
    with pytest.raises(ValueError, match="forbidden"):
        v112.evaluate_forward_runtime(_protocol(), _clock(tmp_path), [receipt])


def test_v112_orthogonal_domain_uses_hard_gates_and_priority() -> None:
    payload = {
        "domains": [
            _domain("announcement_expectation_surprise", pit_semantics_verified=False),
            _domain("share_supply_corporate_action_shocks"),
        ]
    }
    result = v112.evaluate_orthogonal_domains(payload)
    assert result.selected_domain == "share_supply_corporate_action_shocks"
    assert result.state == "ORTHOGONAL_DATA_READY_FOR_PREREGISTRATION"
    assert result.evaluations[0]["passed"] is False
    assert result.label_accesses == 0


def test_v112_orthogonal_domain_rejects_any_return_or_price_key() -> None:
    with pytest.raises(ValueError, match="cannot expose"):
        v112.evaluate_orthogonal_domains(
            {"domains": [{**_domain("announcement_expectation_surprise"), "return": 0.1}]}
        )


def test_v112_orthogonal_domain_missing_contract_artifact_fails_hard_gate() -> None:
    domain = _domain("announcement_expectation_surprise")
    del domain["field_dictionary"]
    result = v112.evaluate_orthogonal_domains({"domains": [domain]})
    assert result.selected_domain is None
    assert "HARD_GATE_FIELD_DICTIONARY" in result.evaluations[0]["reason_codes"]


def test_v112_run_is_deterministic_content_but_unique_envelope(tmp_path: Path) -> None:
    clock_path = tmp_path / "clock.json"
    common = {
        "frozen_protocol": PROTOCOL,
        "v111_evidence": EVIDENCE,
        "clock_manifest": clock_path,
        "output_root": tmp_path / "runs",
        "runtime_code_version": "c" * 40,
        "genesis_at": "2026-09-06T00:00:00Z",
        "created_at": "2026-09-06T00:01:00Z",
    }
    first = v112.run_v112_candidate_nursery(**common, operation_id="one")
    second = v112.run_v112_candidate_nursery(**common, operation_id="two")
    assert first.content_hash == second.content_hash
    assert first.run_envelope["run_envelope_hash"] != second.run_envelope["run_envelope_hash"]
    assert first.content["inferential_trials_added"] == 0
    assert first.content["unauthorized_sealed_label_reads"] == 0
    for name in ("V11_2_RESULT.json", "V11_2_RESULT.zh.md", "V11_2_RESULT.en.md", "RUN_ENVELOPE.json"):
        assert (tmp_path / "runs" / "one" / name).is_file()
    assert not list((tmp_path / "runs" / "one").glob("*.tmp"))
    with pytest.raises(FileExistsError):
        v112.run_v112_candidate_nursery(**common, operation_id="one")
    with pytest.raises(ValueError, match="unsafe"):
        v112.run_v112_candidate_nursery(**common, operation_id="..")


def test_v112_atomic_write_cleans_partial_file_on_interruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "result.json"

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("simulated interruption")

    monkeypatch.setattr(v112.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated"):
        v112._atomic_write(target, "{}\n")
    assert not target.exists()
    assert not list(tmp_path.glob("*.tmp"))
