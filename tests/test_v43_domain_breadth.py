from datetime import date, datetime, timezone

import pytest

from stephen_quant.discovery import v43_sparse_domain_inverse_plan
from stephen_quant.workflows.v43_domain_breadth import (
    DOMAIN_ORDER,
    FORWARD_SHADOW_START,
    ForwardShadowLedger,
    audit_source_readiness,
    build_domain_catalog,
    run_v43_breadth_audit,
)


def test_catalog_is_deterministic_deduplicated_and_domain_budgeted() -> None:
    first, coverage = build_domain_catalog(quotas={domain: 5 for domain in DOMAIN_ORDER})
    second, second_coverage = build_domain_catalog(quotas={domain: 5 for domain in DOMAIN_ORDER})
    assert first == second
    assert coverage == second_coverage
    assert len(first) == 202
    assert sum(item.status != "duplicate" for item in first) == 152
    assert sum(item.status == "duplicate" for item in first) == 50
    assert all(item.admitted <= 5 for item in coverage)
    assert {item.domain for item in coverage} == set(DOMAIN_ORDER)
    assert any(item.cross_source for item in coverage if item.domain != "price")


def test_invalid_domain_quotas_fail_closed() -> None:
    with pytest.raises(ValueError, match="every domain"):
        build_domain_catalog(quotas={"price": 1})


def test_sparse_domain_followup_is_explicitly_counter_directional() -> None:
    plan = v43_sparse_domain_inverse_plan()
    assert len(plan.templates) == 9
    assert all(item.template_id.endswith("_inverse") for item in plan.templates)
    original_directions = (-1, -1, 1, -1, -1, 1, 1, 1, 1)
    assert tuple(item.direction for item in plan.templates) == tuple(-x for x in original_directions)


def test_source_readiness_never_infers_unconfigured_data(tmp_path) -> None:
    daily = tmp_path / "daily"
    daily.mkdir()
    (daily / "20220101.csv").write_text("x\n", encoding="utf-8")
    rows = audit_source_readiness({"qd_daily_dir": daily})
    assert rows[0].status == "READY"
    assert rows[0].files == 1
    assert all(item.status == "UNCONFIGURED" for item in rows[1:-1])
    assert rows[-1].status == "UNAVAILABLE"


def test_report_writes_bilingual_and_machine_readable_outputs(tmp_path) -> None:
    paths = {}
    for domain in DOMAIN_ORDER[:-1]:
        root = tmp_path / domain
        root.mkdir()
        (root / "sample.csv").write_text("x\n", encoding="utf-8")
        key = "qd_daily_dir" if domain == "price" else f"qd_{domain}_dir"
        paths[key] = root
    report = run_v43_breadth_audit(paths, tmp_path / "report")
    assert report.decision == "READY_FOR_BOUNDED_MULTI_DOMAIN_RESEARCH"
    assert report.semantic_domain_count == 7
    assert (tmp_path / "report" / "v4.3-domain-breadth.json").is_file()
    assert (tmp_path / "report" / "v4.3-domain-breadth.zh.md").is_file()
    assert (tmp_path / "report" / "v4.3-domain-breadth.en.md").is_file()


def test_forward_shadow_rejects_retrospective_future_and_overwrite(tmp_path) -> None:
    ledger = ForwardShadowLedger(tmp_path / "ledger")
    now = datetime(2026, 8, 19, 16, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="predates"):
        ledger.record(
            operation_id="old",
            observation_date=date(2026, 8, 18),
            as_of=date(2026, 8, 19),
            recorded_at=now,
            payload={"signal": 1},
        )
    with pytest.raises(ValueError, match="future"):
        ledger.record(
            operation_id="future",
            observation_date=date(2026, 8, 20),
            as_of=date(2026, 8, 19),
            recorded_at=now,
            payload={"signal": 1},
        )
    record = ledger.record(
        operation_id="daily-shadow",
        observation_date=FORWARD_SHADOW_START,
        as_of=FORWARD_SHADOW_START,
        recorded_at=now,
        payload={"signal": 1, "candidate": "frozen"},
    )
    assert len(record.payload_sha256) == 64
    with pytest.raises(FileExistsError):
        ledger.record(
            operation_id="daily-shadow",
            observation_date=FORWARD_SHADOW_START,
            as_of=FORWARD_SHADOW_START,
            recorded_at=now,
            payload={"signal": -1},
        )


def test_forward_shadow_requires_timezone_and_safe_operation_id(tmp_path) -> None:
    ledger = ForwardShadowLedger(tmp_path / "ledger")
    with pytest.raises(ValueError, match="timezone"):
        ledger.record(
            operation_id="safe",
            observation_date=FORWARD_SHADOW_START,
            as_of=FORWARD_SHADOW_START,
            recorded_at=datetime.fromisoformat("2026-08-19T16:00:00"),
            payload={},
        )
    with pytest.raises(ValueError, match="operation_id"):
        ledger.record(
            operation_id="../escape",
            observation_date=FORWARD_SHADOW_START,
            as_of=FORWARD_SHADOW_START,
            recorded_at=datetime(2026, 8, 19, 16, 0, tzinfo=timezone.utc),
            payload={},
        )
