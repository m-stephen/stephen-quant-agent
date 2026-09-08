"""Bounded-buffer fingerprints for accidental mutation of decoded original evidence."""

import hashlib
import json


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
