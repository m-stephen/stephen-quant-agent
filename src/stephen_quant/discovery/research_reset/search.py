"""Finite adaptive search on training labels only; no source/oracle imports."""

from __future__ import annotations

from itertools import combinations

import numpy as np

from .contracts import FIELDS, Candidate


def centered_rank(values, support):
    out = np.zeros(len(values))
    ids = np.flatnonzero(support)
    if not len(ids):
        return out
    order = ids[np.argsort(values[ids], kind="stable")]
    start = 0
    while start < len(order):
        stop = start + 1
        while stop < len(order) and values[order[stop]] == values[order[start]]:
            stop += 1
        out[order[start:stop]] = (start + stop - 1) / (2 * max(1, len(order) - 1)) - 0.5
        start = stop
    return out


def feature_cache(panel):
    panel.validate()
    support = panel.available.all(axis=2)
    ranks = np.zeros_like(panel.features)
    for t in range(len(panel.dates)):
        for j in range(4):
            ranks[t, :, j] = centered_rank(panel.features[t, :, j], support[t])
    return ranks, support


def scores(candidate, ranks):
    candidate.validate()
    cols = [FIELDS.index(f) for f in candidate.fields]
    a = ranks[:, :, cols[0]]
    if candidate.operator == "rank":
        out = a
    elif candidate.operator == "interaction":
        out = a * ranks[:, :, cols[1]]
    else:
        out = a * (ranks[:, :, cols[1]] > 0)
    return out * candidate.direction


def selected_ids(score, support, groups, previous=(), *, role="risk_signal"):
    """All eligibility is decision-time support; never future quote availability."""
    old = set(previous)
    pools = [np.flatnonzero(support & (groups == g)) for g in range(6)]
    if role == "signal_only":
        return tuple(sorted(np.flatnonzero(support), key=lambda i: (-score[i], int(i)))[:6])
    chosen = []
    for pool in pools:
        ordered = sorted(pool, key=lambda i: (-score[i], int(i)))
        retained = [i for i in ordered[:2] if i in old]
        if ordered:
            chosen.append(int(retained[0] if retained else ordered[0]))
    return tuple(chosen)


def training_proxy(candidate, panel, ranks, support, spec):
    """Cheap gross matched-group horizon spread; it is not a native cost account."""
    values = scores(candidate, ranks)
    spreads = []
    h = candidate.horizon
    for t in range(1, spec.train_end - h + 1, h):
        chosen = selected_ids(values[t - 1], support[t - 1], panel.groups)
        if len(chosen) != 6:
            continue
        # All used exits mature inside the training prefix (never test labels).
        future = panel.closing[t + h - 1] / panel.opening[t] - 1
        baseline = []
        for g in range(6):
            pool = np.flatnonzero(support[t - 1] & (panel.groups == g))
            baseline.append(float(np.mean(future[pool])))
        spreads.append((float(np.mean(future[list(chosen)])) - np.mean(baseline)) / h)
    if len(spreads) < 5:
        raise ValueError("insufficient mature training blocks")
    return float(np.mean(spreads))


def initial_catalog(spec):
    candidates = []
    definitions = [("rank", (f,)) for f in FIELDS]
    definitions += [("interaction", pair) for pair in combinations(FIELDS, 2)]
    for operator, fields in definitions:
        for direction in (-1, 1):
            for horizon in spec.horizons:
                candidates.append(Candidate(operator, fields, direction, horizon))
    return tuple(candidates)


def discover(panel, spec, record):
    """Record full identities before each label evaluation; selection never sees oracle."""
    spec.validate()
    ranks, support = feature_cache(panel)
    evaluated, seen = [], set()

    def evaluate(c):
        if c.structure_id in seen:
            record("duplicate", c, None)
            return
        if len(seen) >= spec.max_structures:
            raise ValueError("finite structure budget exhausted")
        record("before_label_read", c, None)
        value = training_proxy(c, panel, ranks, support, spec)
        seen.add(c.structure_id)
        evaluated.append((c, value))
        record("training_score", c, value)

    for c in initial_catalog(spec):
        evaluate(c)
    ranked = sorted(evaluated, key=lambda x: (-x[1], x[0].structure_id))
    # Exactly two distinct parent field origins, chosen on mature training labels.
    parents, origins = [], set()
    for c, _ in ranked:
        origin = c.fields[0]
        if origin not in origins:
            parents.append(c)
            origins.add(origin)
        if len(parents) == 2:
            break
    for parent in parents:
        other_fields = [f for f in FIELDS if f != parent.fields[0]][:2]
        for other in other_fields:
            for direction in (-1, 1):
                child = Candidate(
                    "gate",
                    (parent.fields[0], other),
                    direction,
                    parent.horizon,
                    (parent.structure_id,),
                )
                evaluate(child)
    ranked = sorted(evaluated, key=lambda x: (-x[1], x[0].structure_id))
    winner = ranked[0][0]
    for c, value in ranked:
        record("selected" if c.structure_id == winner.structure_id else "not_selected", c, value)
    return winner, ranks, support, ranked
