from __future__ import annotations

import hashlib
import json
from pathlib import Path

from stephen_quant.factors import build_seed_registry


def test_v1_8_14_candidate_manifest_is_frozen_and_registry_backed() -> None:
    root = Path(__file__).parents[1]
    manifest = root / "configs" / "v1.8.14-candidates.json"
    raw = manifest.read_bytes()
    payload = json.loads(raw)
    candidates = payload["candidates"]
    candidate_ids = [item["candidate_id"] for item in candidates]
    registry = build_seed_registry()

    assert hashlib.sha256(raw).hexdigest() == (
        "b11a97334b3eee5500b83c9a6178990c198287c5fc7f49d3e586c833ba115b3c"
    )
    assert payload["research_window"]["research_end"] < payload["research_window"][
        "validation_start"
    ]
    assert payload["research_window"]["validation_end"] < payload["research_window"][
        "test_start"
    ]
    assert len(candidates) == 4
    assert len(set(candidate_ids)) == len(candidate_ids)
    assert payload["cpcv"] == {
        "groups": 6,
        "test_groups": 3,
        "embargo_days": 5,
        "purge": "closed_next_open_label_intervals",
    }
    assert payload["research_gates"]["minimum_mean_path_rank_ic"] == 0.02
    assert payload["research_gates"]["maximum_pbo"] == 0.2
    for candidate in candidates:
        for key in candidate["components"]:
            factor_id, version = key.split("@", maxsplit=1)
            assert registry.get(factor_id, version).key == key
