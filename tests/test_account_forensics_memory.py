"""Streaming fingerprint is exact canonical JSON and detects accidental mutation."""

import hashlib
import json
from datetime import datetime

import pytest

from stephen_quant.discovery.account_forensics_memory import (
    assert_lookups_unchanged,
    assert_memory_unchanged,
    lookup_fingerprint,
    memory_fingerprint,
)


def test_streaming_matches_canonical_bytes():
    value = {"交易日": [{"value": i / 3, "instrument": str(i), "missing": None,
                       "held": i % 2 == 0} for i in range(1000)], "empty": {}}
    expected = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                         ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()
    assert memory_fingerprint(value) == expected
    assert assert_memory_unchanged(value, expected) == expected
    assert memory_fingerprint(dict(reversed(list(value.items())))) == expected


@pytest.mark.parametrize("field", ["ranks", "bars", "calendar", "report"])
def test_in_memory_changes_are_refused(field):
    value = {"ranks": {"A": 1}, "bars": {"A": {"close": 2}},
             "calendar": ["2023-01-03"], "report": {"end_nav": 100}}
    digest = memory_fingerprint(value)
    value[field] = None
    with pytest.raises(ValueError, match="in memory"):
        assert_memory_unchanged(value, digest)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), {1, 2}])
def test_unhashable_or_nonfinite_fails_closed(value):
    with pytest.raises((ValueError, TypeError)):
        memory_fingerprint({"value": value})


def test_typed_lookup_preserves_actual_reader_datetime(tmp_path):
    from test_account_forensics_inputs import parquet

    from stephen_quant.discovery.account_forensics_inputs import read_daily_lookups

    key = ("2023-01-04", "S1")
    lookups, _ = read_daily_lookups(parquet(tmp_path), [key])
    original = lookups[key]["available_at"]
    assert isinstance(original, datetime) and original.tzinfo is not None
    fingerprint = lookup_fingerprint(lookups)
    assert assert_lookups_unchanged(lookups, fingerprint) == fingerprint
    assert lookups[key]["available_at"] is original
    lookups[key]["available_at"] = original.isoformat()
    with pytest.raises(ValueError, match="in memory"):
        assert_lookups_unchanged(lookups, fingerprint)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), -0.0])
def test_nonfinite_lookup_is_hashed_not_repaired(value):
    key = ("2023-01-04", "S1")
    lookup = {key: {"volume": value}, ("2023-01-05", "S1"): None}
    fingerprint = lookup_fingerprint(lookup)
    assert lookup[key]["volume"] is value
    assert assert_lookups_unchanged(lookup, fingerprint) == fingerprint
    lookup[key]["volume"] = value.hex()
    with pytest.raises(ValueError):
        assert_lookups_unchanged(lookup, fingerprint)


def test_lookup_unsupported_scalar_refused():
    with pytest.raises(ValueError):
        lookup_fingerprint({("2023-01-04", "S1"): {"volume": object()}})


def test_nan_volume_lookup_can_still_be_diagnosed():
    from test_account_forensics_source import DT, inputs, trace

    from stephen_quant.discovery.account_forensics_verify_source import verify_source_row

    source, bar = inputs()
    source.update(name=None, volume=float("nan"), available_at=datetime.fromisoformat(source["available_at"]))
    lookups = {(DT, "S1"): source}
    before = lookup_fingerprint(lookups)
    result = trace(source, bar)
    assert result["classification"] == "source_and_saved_bar_match"
    verify_source_row(DT, "S1", source, bar, result)
    assert_lookups_unchanged(lookups, before)
