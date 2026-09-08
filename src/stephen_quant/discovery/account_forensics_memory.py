"""Bounded-buffer fingerprints for accidental mutation of decoded original evidence."""

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal


def memory_fingerprint(value):
    """Hash canonical JSON without materializing a second serialized history.

    Encoder scalar chunks may exceed the small batching threshold; market row
    scalars are bounded by the frozen data contract. This is not an OS memory cap.
    Reject nonfinite floats, circular structures and unencodable values. The same
    policy is used before and after producer calls, inside total supervision.
    """
    encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"),
                               ensure_ascii=True, allow_nan=False)
    digest, pending, size = hashlib.sha256(), [], 0
    for part in encoder.iterencode(value):
        pending.append(part)
        size += len(part)
        if size >= 16384:
            digest.update("".join(pending).encode("ascii"))
            pending, size = [], 0
    if pending:
        digest.update("".join(pending).encode("ascii"))
    return digest.hexdigest()


def assert_memory_unchanged(value, expected):
    actual = memory_fingerprint(value)
    if actual != expected:
        raise ValueError("decoded original evidence changed in memory")
    return actual


def lookup_fingerprint(lookups):
    """Typed scalar fingerprint for actual Parquet rows, without modifying them.

    Unlike original JSON history, reader rows can contain datetime or NaN/inf.
    Preserve their type and value as tagged strings for hashing, not as repaired
    source values. Row-sized encoding avoids copying the full query projection.
    Unexpected non-scalar types fail closed rather than invoking arbitrary repr.
    """
    def tagged(value):
        if value is None:
            return ["null"]
        if type(value) is bool:
            return ["bool", value]
        if type(value) is int:
            return ["int", str(value)]
        if type(value) is float:
            return ["float", value.hex()]
        if isinstance(value, str):
            return ["str", value]
        if isinstance(value, datetime):
            return ["datetime", value.isoformat(), value.fold]
        if isinstance(value, date):
            return ["date", value.isoformat()]
        if isinstance(value, Decimal):
            return ["decimal", str(value)]
        raise ValueError("unsupported source scalar fingerprint type")

    digest = hashlib.sha256()
    for key in sorted(lookups):
        row = lookups[key]
        encoded = [list(key), None if row is None else
                   [[name, tagged(row[name])] for name in sorted(row)]]
        digest.update(json.dumps(encoded, ensure_ascii=True, allow_nan=False,
                                 separators=(",", ":")).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def assert_lookups_unchanged(lookups, expected):
    actual = lookup_fingerprint(lookups)
    if actual != expected:
        raise ValueError("original source lookup changed in memory")
    return actual
