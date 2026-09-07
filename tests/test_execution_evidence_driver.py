import importlib.util
import json
import sqlite3

import duckdb
import pytest

from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.workflows.v114_reliable_epoch import write_json


def setup(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "execution_driver", "scripts/audit_execution_evidence.py"
    )
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    parent, inputs, cards, output = [tmp_path / n for n in ("parent", "inputs", "cards", "output")]
    for p in (parent, inputs, cards, parent / "accounts"):
        p.mkdir(parents=True, exist_ok=True)
    parquet = inputs / "daily.parquet"
    with duckdb.connect() as c:
        c.execute(
            "CREATE TABLE d(trade_date DATE,instrument VARCHAR,open DOUBLE,adjustment_factor DOUBLE)"
        )
        c.execute(
            "INSERT INTO d VALUES ('2022-12-30','600001',10,2), ('2023-01-03','600001',10,2), ('2023-01-04','600001',9,2.2)"
        )
        c.execute("COPY d TO ? (FORMAT PARQUET)", [str(parquet)])
    ledger = [
        {
            "source": "daily",
            "file": parquet.name,
            "sha256": driver.file_sha(parquet),
            "max_date": "2023-01-04",
        }
    ]
    monkeypatch.setattr(driver, "SNAPSHOT_SHA", sha256_json(ledger))
    write_json(
        inputs / "manifest.json", {"sources": ledger, "snapshot_sha256": driver.SNAPSHOT_SHA}
    )
    periods = [
        {
            "date": "2023-01-03",
            "orders": [{"instrument": "600001", "executed_notional": 1999.99}],
            "positions": [{"instrument": "600001", "shares": 12.345}],
        },
        {"date": "2023-01-04", "orders": [], "positions": []},
    ]
    records = {}
    for p in driver.POLICIES:
        path = parent / "accounts" / f"baseline_82-{p}.jsonl"
        path.write_text("\n".join(json.dumps(d) for d in periods), encoding="utf-8")
        records[p] = {
            "dates": [d["date"] for d in periods],
            "account_sha256": driver.file_sha(path),
        }
    write_json(
        parent / "RESULT.json",
        {
            "raw_global_trial_lower_bound": 3320,
            "engineering_pass": True,
            "records": {"baseline_82": records},
        },
    )
    for n in ("registry.sqlite3", "first_read_reservations.json"):
        write_json(parent / n, {})
    write_json(parent / "INDEPENDENT_AUDIT.json", {"pass": True})
    card = cards / "card.json"
    write_json(card, {"synthetic": True})
    monkeypatch.setattr(driver, "PARENT_SHA", driver.file_sha(parent / "RESULT.json"))
    monkeypatch.setattr(driver, "CARD_SHA", driver.file_sha(card))
    monkeypatch.setattr(driver, "CLAIM_ROOT", tmp_path / "claims")
    config = tmp_path / "config.json"
    write_json(
        config,
        {
            "parent_dir": str(parent),
            "input_dir": str(inputs),
            "original_card": str(card),
            "output_dir": str(output),
            "preregistration_comment": 1,
        },
    )
    return driver, config, output, parquet


def test_native_reservations_before_source_read_and_claim_not_reusable(tmp_path, monkeypatch):
    driver, config, output, _ = setup(tmp_path, monkeypatch)
    original = driver.extract_prices

    def checked(path, keys):
        with sqlite3.connect(output / "registry.sqlite3") as c:
            assert c.execute("SELECT count(*) FROM trials").fetchone()[0] == 2
            assert (
                c.execute(
                    "SELECT count(*) FROM trial_fit_contracts WHERE stages_json='[]'"
                ).fetchone()[0]
                == 2
            )
        return original(path, keys)

    monkeypatch.setattr(driver, "extract_prices", checked)
    result = driver.run(config)
    assert result["raw_global_trial_lower_bound"] == 3322
    assert result["new_account_trials"] == 0 and result["new_model_fits"] == 0
    assert result["scoped_event_worklist_keys"] == 1  # Dedup across both frozen accounts.
    for policy in driver.POLICIES:
        assert result["records"][policy]["held_factor_change_keys"] == 1
    next_config = tmp_path / "second.json"
    value = json.loads(config.read_text())
    value["output_dir"] = str(tmp_path / "second-output")
    write_json(next_config, value)
    with pytest.raises(FileExistsError):
        driver.run(next_config)


def test_source_change_rejected_before_any_parsed_market_read(tmp_path, monkeypatch):
    driver, config, output, parquet = setup(tmp_path, monkeypatch)
    parquet.write_bytes(b"tampered")
    monkeypatch.setattr(driver, "extract_prices", lambda *a: pytest.fail("must not parse source"))
    with pytest.raises(ValueError, match="source snapshot bytes"):
        driver.run(config)
    assert not output.exists()


def test_failure_after_reservation_preserves_claim_and_debt(tmp_path, monkeypatch):
    driver, config, output, _ = setup(tmp_path, monkeypatch)

    def broken(*_):
        raise ValueError("synthetic loader failure")

    monkeypatch.setattr(driver, "extract_prices", broken)
    with pytest.raises(ValueError, match="synthetic loader"):
        driver.run(config)
    assert json.loads((output / "ABORTED.json").read_text())["reservations_preserved"]
    assert (
        json.loads((output / "first_read_reservations.json").read_text())["reserved_new_trials"]
        == 2
    )
    assert (driver.CLAIM_ROOT / (driver.PARENT_SHA + ".json")).exists()
