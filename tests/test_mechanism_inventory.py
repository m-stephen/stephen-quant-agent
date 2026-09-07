import hashlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from stephen_quant.discovery.mechanism_lineage import build_proposal_lineage
from stephen_quant.discovery.proposal_generator import ProposalSpec, compile_proposal
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.mechanism_inventory import (
    REPO_SOURCES,
    canonical_expression,
    freeze_lineage_packet,
    lineage_keys,
    source_inventory,
)


def keys(**changes):
    args = {
        "family": "flow_price_absorption",
        "expression": "rank(flow) * (1-rank(ret))",
        "required_fields": ("flow", "ret"),
        "sources": ("qd_daily", "qd_fund_flow"),
        "lookback": 60,
        "forecast_sessions": 20,
        "direction": -1,
        "execution_timing": "T+1_OPEN",
    }
    return lineage_keys(**(args | changes))


def test_catalog_reads_source_bytes_without_executing_code(tmp_path):
    text = 'raise RuntimeError("must not execute")\nX = 2\nY = missing_function()\nZ = {1, 2}\n'
    (tmp_path / "a.py").write_text(text, encoding="utf-8")
    (tmp_path / "b.py").write_text("def sample():\n    return 1\n", encoding="utf-8")
    first = source_inventory(tmp_path, ("a.py", "b.py"))
    assert first == source_inventory(tmp_path, ("b.py", "a.py"))
    assert first["files"]["a.py"] == hashlib.sha256((tmp_path / "a.py").read_bytes()).hexdigest()
    assert first["market_rows_read"] == first["empirical_trials_added"] == 0
    assert [u["details"].get("requires_expansion_review") for u in first["units"][:3]] == [
        None,
        True,
        True,
    ]
    assert json.loads(json.dumps(first)) == first
    payload = {k: v for k, v in first.items() if k != "inventory_sha256"}
    assert first["inventory_sha256"] == sha256_json(payload)
    (tmp_path / "a.py").write_text(text + "# altered bytes\n", encoding="utf-8")
    second = source_inventory(tmp_path, ("a.py", "b.py"))
    assert first["inventory_sha256"] != second["inventory_sha256"]
    assert first["units"] == second["units"]


@pytest.mark.parametrize("paths", [("a.py", "a.py"), ("../a.py",), ("a.csv",), ("/a.py",)])
def test_inventory_path_guards(tmp_path, paths):
    with pytest.raises(ValueError):
        source_inventory(tmp_path, paths)


def test_actual_inventory_captures_existing_families_and_not_full_runtime():
    result = source_inventory(Path(__file__).resolve().parents[1])
    assert len(result["files"]) == len(REPO_SOURCES) == 15
    rendered = json.dumps(result)
    for name in (
        "downside_vol_20",
        "return_skewness",
        "flow_price_divergence",
        "flow_price_absorption",
        "semantic_plan_id",
        "net_inflow_ratio",
    ):
        assert name in rendered
    assert "not exhaustively expanded candidates" in result["limits"]
    assert not any("artifacts/" in p for p in result["files"])


def test_canonicalization_is_limited_not_a_novelty_claim():
    assert keys(expression="mean(flow, 20)") == keys(expression="mean(flow, 20.0)")
    assert canonical_expression(" rank(flow)*(1 - rank(ret)) ") == canonical_expression(
        "(1-rank(ret))*rank(flow)"
    )
    for a, b in (("a-b", "b-a"), ("a/b", "b/a"), ("a+(b+c)", "(a+b)+c")):
        assert canonical_expression(a) != canonical_expression(b)
    assert keys()["novelty_status"] == "NOT_ESTABLISHED_BY_UNMATCHED_HASH"


@pytest.mark.parametrize(
    "expression",
    ["obj.method(x)", "__import__(x)", "x[0]", "rank(x, axis=0)", "True", "1e999", "_secret"],
)
def test_unsupported_syntax_requires_review(expression):
    with pytest.raises(ValueError):
        canonical_expression(expression)


def test_new_keys_preserve_debt_family_and_ignore_narrative_not_policy():
    original = keys(legacy_ids=("a" * 64,), narrative="absorption")
    changed = keys(
        family="flow_response_residual",
        required_fields=("ret", "flow"),
        sources=("qd_fund_flow", "qd_daily"),
        legacy_ids=("a" * 64,),
        narrative="an entirely new amazing title",
    )
    assert original == changed
    assert original["legacy_ids"] == ["a" * 64] and not original["debt_reset_allowed"]
    opposite = keys(direction=1)
    assert original["family_id"] == opposite["family_id"]
    assert original["expression_id"] == opposite["expression_id"]
    assert original["policy_id"] != opposite["policy_id"]
    distinct = keys(expression="response_residual(flow, ret)")
    assert distinct["family_id"] == original["family_id"]
    assert distinct["expression_id"] != original["expression_id"]


def test_old_narrative_ids_do_change_but_additive_semantic_key_does_not():
    item = compile_proposal(
        ProposalSpec(
            "mean(net_inflow_amount, 20)/(mean(amount, 20)+1)-period_return(close, 20)",
            "Flow absorption",
            "continuous_ranking",
            "20d",
            -1,
            "symbolic",
            "synthetic-test",
        )
    )
    renamed = replace(item, proposal=replace(item.proposal, hypothesis="Different wording"))
    old, renamed_old = build_proposal_lineage(item), build_proposal_lineage(renamed)
    assert old.policy_variant_id != renamed_old.policy_variant_id
    assert old.mechanism_family_id != renamed_old.mechanism_family_id
    common = {
        "family": old.mechanism_family,
        "expression": item.schema.formula,
        "required_fields": item.schema.required_fields,
        "sources": item.schema.data_sources,
        "lookback": 20,
        "forecast_sessions": 20,
        "direction": -1,
        "execution_timing": "T+1_OPEN",
        "legacy_ids": (old.policy_variant_id, renamed_old.policy_variant_id),
    }
    a = lineage_keys(**common, narrative=item.proposal.hypothesis)
    b = lineage_keys(**common, narrative=renamed.proposal.hypothesis)
    assert a == b
    # A canonical tombstone lookup now has the same key; old packet integration is pending.
    tombstones = {a["family_id"]}
    assert b["family_id"] in tombstones
    assert len(a["legacy_ids"]) == 2 and not a["debt_reset_allowed"]


@pytest.mark.parametrize(
    "change",
    [
        {"family": "unknown"},
        {"lookback": 0},
        {"forecast_sessions": True},
        {"direction": 0},
        {"execution_timing": "SAME_OPEN"},
        {"sources": "qd_daily"},
        {"required_fields": (" ",)},
        {"legacy_ids": ("not-hash",)},
    ],
)
def test_invalid_identity_contract(change):
    with pytest.raises(ValueError):
        keys(**change)


def test_inventory_cli_does_not_import_discovery_or_overwrite(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "inventory.json"
    env = {
        k: v
        for k, v in os.environ.items()
        if k.upper() not in {"ALPHAPAI_API_KEY", "ALPHAPAI_BASE_URL"}
    }
    env["PYTHONPATH"] = str(root / "src")
    code = (
        "import runpy,sys; "
        "sys.argv=['inventory_research_mechanisms.py','--output',sys.argv[1]]; "
        "runpy.run_path('scripts/inventory_research_mechanisms.py',run_name='__main__'); "
        "assert not any(n.startswith(('stephen_quant.discovery','stephen_quant.qmt',"
        "'stephen_quant.factors','stephen_quant.workflows')) for n in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(output)],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["source_files"] == 15 and summary["empirical_trials_added"] == 0
    original = output.read_bytes()
    retry = subprocess.run(
        [sys.executable, "-c", code, str(output)],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert retry.returncode != 0 and "FileExistsError" in retry.stderr
    assert original == output.read_bytes()


def recipe(name="candidate", expression="rank(flow) * (1-rank(ret))", **changes):
    return {
        "name": name,
        "lineage": {
            "family": "flow_price_absorption",
            "expression": expression,
            "required_fields": ("flow", "ret"),
            "sources": ("qd_daily", "qd_fund_flow"),
            "lookback": 60,
            "forecast_sessions": 20,
            "direction": -1,
            "execution_timing": "T+1_OPEN",
            **changes,
        },
    }


def test_new_packet_canonicalizes_renamed_recipes_without_losing_old_ids():
    a = recipe("A", legacy_ids=("a" * 64,), narrative="first")
    b = recipe("B", "(1-rank(ret))*rank(flow)", legacy_ids=("b" * 64,), narrative="new title")
    packet = freeze_lineage_packet([a, b], budget=1)
    assert packet == freeze_lineage_packet([b, a], budget=1)
    b_same_name = b | {"name": "A"}
    assert freeze_lineage_packet([a, b_same_name], budget=1) == freeze_lineage_packet(
        [b_same_name, a], budget=1
    )
    assert len(packet["accepted"]) == 1 and packet["proposed"] == 2
    assert packet["accepted"][0]["keys"]["legacy_ids"] == ["a" * 64, "b" * 64]
    assert packet["rejected"][0]["reason"] == "canonical_duplicate"
    assert not packet["historical_debt_reset_allowed"] and packet["empirical_trials_added"] == 0


@pytest.mark.parametrize("kind", ["policy", "family", "legacy_alias"])
def test_packet_tombstones_cannot_be_evaded_by_new_names(kind):
    original = recipe()
    identity = lineage_keys(**original["lineage"])
    kwargs = {
        "policy": {"policy_tombstones": [identity["policy_id"]]},
        "family": {"family_tombstones": [identity["family_id"]]},
        "legacy_alias": {"legacy_tombstone_aliases": {"a" * 64: identity["policy_id"]}},
    }[kind]
    changed = recipe("New title", "(1-rank(ret))*rank(flow)", narrative="new hypothesis")
    packet = freeze_lineage_packet([changed], budget=1, **kwargs)
    assert not packet["accepted"] and packet["rejected"][0]["reason"] == "tombstone"


def test_packet_rejects_over_budget_instead_of_silently_selecting():
    with pytest.raises(ValueError, match="exceeds budget"):
        freeze_lineage_packet([recipe(), recipe("other", "rank(flow)")], budget=1)
    with pytest.raises(ValueError, match="tombstone hashes"):
        freeze_lineage_packet([recipe()], budget=1, policy_tombstones=("not-hash",))
