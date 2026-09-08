"""Renderer contract tests use metadata fixtures, never a numerical account run."""

import json

import pytest
from test_account_forensics_acceptance import (
    proof as proof,  # noqa: PLC0414 -- explicitly re-export pytest fixture.
)
from test_account_forensics_acceptance import rebind, save

from stephen_quant.discovery.account_forensics_acceptance import accept_saved_artifacts, read
from stephen_quant.discovery.account_forensics_report import (
    METRICS,
    STATUS,
    format_number,
    project_report,
    render_markdown,
    verify_reports,
    write_reports,
)
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.qmt.reliable_panel import file_sha


@pytest.fixture
def report_fixture(proof):
    root, kwargs = proof
    summary = read(root / "SUMMARY.json")
    for name, account in summary["accounts"].items():
        for window in ("2023", "2024", "continuous"):
            row = account["continuous"] if window == "continuous" else account["years"][window]
            row.update({k: 0 if spec[2] == "count" else 0.0 for k, spec in METRICS.items()})
            opening, closing = {"2023": (3000000.0, 2400000.0), "2024": (2400000.0, 2880000.0),
                                "continuous": (3000000.0, 2880000.0)}[window]
            row.update(opening_nav_cny=opening, closing_nav_cny=closing, profit_cny=closing-opening,
                       net_return=closing/opening-1, sharpe_252_zero_risk_free=None,
                       writeoff_events=1, writeoff_cny=100.0)
        portable = name.replace("/", "--") + ".json"
        path = root / "exposures" / portable
        exposed = read(path)
        for row in exposed["daily"]:
            row.update(cell_invested_weights=[0.04] * 20, unknown_invested_weight=0.2,
                       unknown_names=["UNKNOWN_NAME"], cash_nav_weight=0.1)
        rebind(root, "exposures/" + portable, exposed)
        receipt_rel = "verification/" + portable
        receipt = read(root / receipt_rel)
        receipt["summary_sha256"] = sha256_json(account)
        receipt["output_files"]["exposures/" + portable] = file_sha(path)
        rebind(root, receipt_rel, receipt)
    verification = read(root / "VERIFICATION.json")
    for policy in ("global_response", "global_risk"):
        rel = f"membership/{policy}.json"
        detail = read(root / rel)
        for i, event in enumerate(detail["membership"]["maintenance_events"]):
            event.update(selected_count=40, entered=40 if i < 4 else 10,
                         exited=0 if i < 4 else 10, retention_fraction=None if i < 4 else 0.75)
        for event in detail["support"]["maintenance_events"]:
            event.update(previous_selected_lost_support=["S1", "S2"],
                         previous_selected_exited_still_eligible=["S3"])
        rebind(root, rel, detail)
        verification["membership"][policy]["output_sha256"] = file_sha(root / rel)
    rebind(root, "VERIFICATION.json", verification)
    for item in summary["primary"].values():
        for window, row in item["windows"].items():
            difference = 1.0 if window == "2024" else -1.0
            row.update(net_return_difference_pp=difference, profit_difference_cny=difference * 30000,
                       paired_mean_net_return_difference_bps=difference)
    summary["output_files"] = read(root / "SUMMARY.json")["output_files"]
    rebind(root, "SUMMARY.json", summary)
    acceptance = accept_saved_artifacts(root, **kwargs)
    return root, kwargs, acceptance


def test_complete_bilingual_projection_and_independent_readback(report_fixture):
    root, _, acceptance = report_fixture
    before = dict(acceptance["verified_artifact_files"])
    receipt = write_reports(root, acceptance)
    assert receipt["status"] == STATUS and receipt["validated_alpha"] is False
    payload = read(root / "reader-report/report.json")
    assert len(payload["account_windows"]) == 36 and len(payload["primary"]) == 6
    assert payload["primary_direction"] == "MIXED"
    assert {r["account"] for r in payload["account_windows"]} == set(payload["account_keys"])
    assert all(r["opening_nav_cny"] == 2400000 for r in payload["account_windows"] if r["window"] == "2024")
    assert all(r["profit_cny"] == 480000 for r in payload["account_windows"] if r["window"] == "2024")
    for item in payload["exposures"].values():
        assert len(item["daily"]) == 484
        assert item["daily"][0]["unknown_invested_weight"] == 0.2
        assert len(item["daily"][0]["cell_invested_weights"]) == 20
    assert all(len(v["membership"]["maintenance_events"]) == 97 for v in payload["membership"].values())
    en = (root / "reader-report/report.en.md").read_text(encoding="utf-8")
    zh = (root / "reader-report/report.zh.md").read_text(encoding="utf-8")
    for text in (zh, en):
        assert "2,400,000.00" in text and "480,000.00" in text and "0.0000%" in text
        assert "UNKNOWN_NAME" not in text  # detail lives in exact JSON, not a invented text cohort.
        assert str(root) not in text
        for name in payload["account_keys"]:
            assert name in text
        assert "S2" in text  # an unknown unresolved tail must not disappear.
    assert "未识别" in zh and "未保存" in zh and "未定义" in zh and "无前期/不适用" in zh
    assert "Undefined" in en and "No prior membership/N.A." in en and "Open stale tail" in en
    assert "round-trip" in en and "not a market index" in en and "not recovery cash receipts" in en
    assert verify_reports(root, acceptance) == receipt
    assert {r: file_sha(root / r) for r in before} == before
    with pytest.raises(FileExistsError):
        write_reports(root, acceptance)


@pytest.mark.parametrize("case", ["text", "payload", "missing_language", "receipt_only", "post_source", "subset", "missing_render_receipt", "render_receipt"])
def test_renderer_tampering_and_partial_evidence_refused(report_fixture, case):
    root, _, acceptance = report_fixture
    if case == "receipt_only":
        acceptance["verified_artifact_files"].pop("SUMMARY.json")
        with pytest.raises(ValueError):
            write_reports(root, acceptance)
        assert not (root / "reader-report").exists()
        return
    receipt = write_reports(root, acceptance)
    out = root / "reader-report"
    if case == "text":
        path = out / "report.zh.md"
        path.write_text(path.read_text(encoding="utf-8").replace("2,400,000.00", "3,000,000.00"), encoding="utf-8")
    elif case == "payload":
        obj = read(out / "report.json")
        obj["account_windows"][0]["profit_cny"] += 1
        save(out / "report.json", obj)
    elif case == "missing_language":
        (out / "report.en.md").unlink()
    elif case == "post_source":
        save(root / "SUMMARY.json", {"changed": True})
    elif case == "missing_render_receipt":
        (out / "RENDERED.json").unlink()
    elif case == "render_receipt":
        receipt["validated_alpha"] = True
        save(out / "RENDERED.json", receipt)
    else:
        obj = read(out / "report.json")
        obj["account_windows"].pop()
        save(out / "report.json", obj)
    if case not in ("missing_language", "post_source", "missing_render_receipt", "render_receipt"):
        receipt["files"] = {rel: file_sha(out / rel) for rel in receipt["files"]}
        save(out / "RENDERED.json", receipt)  # a locally rehashed receipt cannot bless drift.
    with pytest.raises((ValueError, KeyError, FileNotFoundError)):
        verify_reports(root, acceptance)


@pytest.mark.parametrize("values,direction", [([1.0, -1.0], "MIXED"), ([0.0, 0.0], "NONPOSITIVE"),
    ([-1.0, -2.0], "NONPOSITIVE"), ([1.0, 2.0], "NONNEGATIVE_DESCRIPTIVE_ONLY")])
def test_direction_never_promotes_alpha(report_fixture, values, direction):
    root, _, acceptance = report_fixture
    payload = project_report(root, acceptance)
    summary = read(root / "SUMMARY.json")
    for i, cost in enumerate(("82", "164")):
        for window in summary["primary"][cost]["windows"].values():
            window["net_return_difference_pp"] = values[i]
    rebind(root, "SUMMARY.json", summary)
    # This isolated formatting fixture is not a new external/numerical acceptance.
    acceptance["verified_artifact_files"]["SUMMARY.json"] = file_sha(root / "SUMMARY.json")
    acceptance["verified_artifact_files"]["TERMINAL.json"] = file_sha(root / "TERMINAL.json")
    payload = project_report(root, acceptance)
    assert payload["primary_direction"] == direction
    assert payload["validated_alpha"] is False
    for lang in ("zh", "en"):
        assert render_markdown(payload, lang)


def test_reasoned_null_and_true_zero_are_distinct():
    assert format_number(None, "number", "en") == "Undefined"
    assert format_number(0.0, "number", "en") == "0.000000"
    with pytest.raises(ValueError):
        format_number(False, "number", "en")


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_numeric_format_refused(value):
    with pytest.raises(ValueError):
        format_number(value, "money", "en")


def test_no_absolute_paths_in_machine_projection(report_fixture):
    root, _, acceptance = report_fixture
    raw = json.dumps(project_report(root, acceptance))
    assert str(root) not in raw and "input_files" not in raw
