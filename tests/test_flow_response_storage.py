import json
import math
from decimal import Decimal

import numpy as np
import pytest

from stephen_quant.discovery.flow_response_storage import (
    FrozenDict,
    freeze,
    load_json,
    streaming_sha256_json,
)
from stephen_quant.discovery.search_power_dsl import sha256_json


@pytest.mark.parametrize(
    "value",
    [
        {},
        [],
        {"中文": [None, True, False, -0.0, 1e-300, 1e300, 1.2345678901234567]},
        {"large": "股" * 100000},
        {"a": (1, {"z": "\n\t\u0000", "b": [2.0, 3]})},
        {"nonfinite_encoding_not_validation": [math.nan, math.inf, -math.inf]},
    ],
)
def test_streamed_hash_preserves_legacy_exact_canonical_bytes(value):
    assert streaming_sha256_json(value) == sha256_json(value)
    assert streaming_sha256_json(freeze(value)) == sha256_json(value)


def test_many_keys_and_float_values_preserve_canonical_encoding():
    rng = np.random.default_rng(184006)
    value = {
        f"date-{i:04d}": {
            f"stock-{n:03d}": {"ranks": rng.normal(size=8).tolist(), "cell": n % 20}
            for n in range(17)
        }
        for i in range(13)
    }
    assert streaming_sha256_json(value) == sha256_json(value)


def test_streaming_hash_does_not_use_document_sized_dumps(monkeypatch):
    value = {"z": [1.0, "x"], "a": {"q": False}}
    expected = sha256_json(value)

    def forbidden(*args, **kwargs):
        pytest.fail("document-sized serialization called")

    monkeypatch.setattr(json, "dumps", forbidden)
    assert streaming_sha256_json(value) == expected


def test_unsupported_values_still_fail_like_legacy_encoder():
    with pytest.raises(TypeError):
        streaming_sha256_json({"bad": Decimal("1.2")})


def test_immutable_decode_preserves_values_and_closes_every_mutation_path(tmp_path):
    value = {"calendar": ["2022-01-03"], "rows": [{"a": 1.5, "nested": [[1, 2], {"b": 3}]}]}
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    mutable = load_json(path)
    frozen = load_json(path, immutable=True)
    assert mutable == value
    assert streaming_sha256_json(frozen) == sha256_json(value)
    assert isinstance(frozen, FrozenDict)
    assert isinstance(frozen["rows"], tuple)
    assert isinstance(frozen["rows"][0]["nested"][1], FrozenDict)
    assert isinstance(frozen["rows"][0]["nested"][0], tuple)
    for operation in (
        lambda: frozen.update({"calendar": ()}),
        lambda: frozen["rows"][0].__setitem__("a", 9),
        lambda: frozen["rows"][0]["nested"][1].pop("b"),
        lambda: frozen.clear(),
    ):
        with pytest.raises(TypeError, match="immutable"):
            operation()
    assert freeze(frozen) is frozen


def test_immutable_decoder_accepts_top_level_lists_and_scalars(tmp_path):
    path = tmp_path / "fixture.json"
    for value in ([{"a": [1, 2]}], True, None, 3.5, "文本"):
        path.write_text(json.dumps(value), encoding="utf-8")
        assert streaming_sha256_json(load_json(path, immutable=True)) == sha256_json(value)


def test_immutable_decode_rejects_malformed_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"rows": [}', encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_json(path, immutable=True)
