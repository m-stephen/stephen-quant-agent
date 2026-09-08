"""Streaming fingerprint is exact canonical JSON and detects accidental mutation."""

import hashlib
import json

import pytest

from stephen_quant.discovery.account_forensics_memory import (
    assert_memory_unchanged,
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
