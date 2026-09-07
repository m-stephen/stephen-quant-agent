import copy
from datetime import date, timedelta

import pytest

from stephen_quant.discovery.flow_response_model_audit import (
    reference_fit,
    reference_pairs,
    reference_targets,
)
from stephen_quant.discovery.flow_response_reference import FIELDS
from stephen_quant.discovery.flow_response_source_audit import compare


def history():
    days = [str(date(2022, 1, 1) + timedelta(days=i)) for i in range(240)] + [
        "2023-01-03",
        "2023-01-04",
    ]
    ranks = {
        d: {
            n: {
                "cell": 0,
                "vol": 0.01 + j * 0.001,
                "ranks": {f: (-0.5 if j == 0 else 0.5) for f in FIELDS},
            }
            for j, n in enumerate(("A", "B"))
        }
        for d in days
    }
    bars = {
        d: {
            n: {
                "open_price": 10 + (j + 1) * i / 100,
                "close_price": 10 + (j + 1) * i / 100 + 0.01,
                "trade_date": d,
            }
            for j, n in enumerate(("A", "B"))
        }
        for i, d in enumerate(days)
    }
    return {"calendar": days, "ranks": ranks, "bars": bars}


def test_independent_mature_labels_embargo_and_missing_endpoint_use_past_mark():
    h = history()
    days, pairs = reference_pairs(h, 2023)
    assert days[-1] == h["calendar"][234]
    assert max(p["label_end"] for p in pairs) <= days[-1]
    first = pairs[0]
    left = first["left"]
    assert first["left_label"]["return"] == pytest.approx(
        h["bars"][days[21]][left]["open_price"] / h["bars"][days[1]][left]["open_price"] - 1
    )
    h["bars"][days[21]].pop(left)
    _, after = reference_pairs(h, 2023)
    assert after[0]["left_label"]["mark_date"] == days[20]
    assert not after[0]["left_label"]["fresh_end"]
    assert after[0]["left_label"]["end_price"] == h["bars"][days[20]][left]["close_price"]
    h["bars"][days[1]].pop(left)
    _, missing = reference_pairs(h, 2023)
    assert not any(p["date"] == days[0] for p in missing)


@pytest.mark.parametrize(
    "policy",
    [
        "response",
        "response_interaction",
        "risk",
        "raw_flow_return",
        "standardized_flow_return",
        "old_absorption",
        "shuffle",
    ],
)
def test_independent_fit_zero_labels_and_future_poison(policy):
    h = history()
    for bars in h["bars"].values():
        for b in bars.values():
            b.update(open_price=10.0, close_price=10.0)
    before = reference_fit(h, 2023, policy)
    assert before["training_signal_dates"] >= 30
    assert all(abs(w) < 1e-12 for w in before["weights"])
    for d in h["calendar"][235:]:
        h["bars"][d] = "must_not_read"
        h["ranks"][d] = "must_not_read"
    assert before == reference_fit(h, 2023, policy)


def test_reference_targets_use_frozen_model_and_current_support_only():
    h = history()
    more = [str(date(2023, 1, 5) + timedelta(days=i)) for i in range(45)]
    h["calendar"].extend(more)
    for d in more:
        h["ranks"][d] = copy.deepcopy(h["ranks"]["2023-01-03"])
    h["ranks"]["2023-01-03"] = {}
    targets, diagnostics = reference_targets(h, "lowvol")
    assert targets[1]["weights"] == {}
    assert diagnostics[0]["selected"] == 0
    assert sum(targets[16]["weights"].values()) == pytest.approx(0.0375)
    assert all(t["decided_at"][:10] < t["trade_date"] for t in targets if t["rebalance"])
    broken = copy.deepcopy(targets)
    broken[6]["weights"]["A"] = 0.9
    with pytest.raises(ValueError):
        compare(broken, targets)
