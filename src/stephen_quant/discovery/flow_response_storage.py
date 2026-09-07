"""Lower-copy JSON operations without changing the frozen evidence contract.

This avoids document-sized *extra* copies, not the retained historical matrix.
The encoder still sorts each mapping and may allocate its largest scalar token.
Neither these functions nor an immutable object authorize market data access.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


class FrozenDict(dict):
    def _reject(self, *args, **kwargs):
        raise TypeError("verified historical cache is immutable")

    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = __ior__ = _reject


def freeze(value):
    """Reuse already-frozen decoder children instead of copying the whole tree."""
    if isinstance(value, FrozenDict):
        return value
    if isinstance(value, dict):
        return FrozenDict({k: freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(v) for v in value)
    return value


def _decoded_object(value):
    # object_hook runs bottom-up. Child mappings are already immutable; only the
    # current mapping and any array containers need conversion here.
    return FrozenDict({k: freeze(v) for k, v in value.items()})


def load_json(path, *, immutable=False):
    # A text stream avoids keeping both raw bytes and the decoded full string.
    # stdlib JSON still loads one document; this is not a streaming JSON parser.
    with Path(path).open(encoding="utf-8") as stream:
        result = json.load(stream, object_hook=_decoded_object if immutable else None)
    return freeze(result) if immutable else result


def streaming_sha256_json(value):
    """Match search_power_dsl.sha256_json, including its nonfinite-token behavior.

    This is evidence encoding, not numeric validation: callers retain their
    finite-value gates. Buffer small encoder chunks, never the entire document.
    """
    encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest, buffer = hashlib.sha256(), bytearray()
    for text in encoder.iterencode(value):
        chunk = text.encode("utf-8")
        if len(buffer) + len(chunk) > 65536:
            digest.update(buffer)
            buffer.clear()
        if len(chunk) >= 65536:
            digest.update(chunk)
        else:
            buffer.extend(chunk)
    digest.update(buffer)
    return digest.hexdigest()
