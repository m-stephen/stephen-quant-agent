"""Source-only discovery inventory and additive narrative-independent lineage keys.

Never imports catalog modules or expands an empirical search. Canonical expression
matching is deliberately limited; unmatched does not mean economically novel.
Existing V9 lineage IDs and historical Trials are not rewritten.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
from pathlib import Path

VERSION = "11.21-static-1"
REPO_SOURCES = (
    "src/stephen_quant/factors/seeds.py",
    "src/stephen_quant/factors/engine.py",
    "src/stephen_quant/workflows/price_discovery_lab.py",
    "src/stephen_quant/workflows/v4_ohlcv_platform.py",
    "src/stephen_quant/discovery/generator.py",
    "src/stephen_quant/discovery/proposal_generator.py",
    "src/stephen_quant/discovery/mechanism_grammar.py",
    "src/stephen_quant/discovery/mechanism_lineage.py",
    "src/stephen_quant/discovery/v10_generator.py",
    "src/stephen_quant/discovery/temporal_increments.py",
    "src/stephen_quant/discovery/risk_stratified.py",
    "src/stephen_quant/discovery/peer_information.py",
    "src/stephen_quant/discovery/conditional_risk.py",
    "src/stephen_quant/discovery/pairwise_ranking.py",
    "src/stephen_quant/qmt/reliable_panel.py",
)
FAMILIES = {
    "flow_price_divergence": "liquidity_impact_absorption",
    "flow_price_absorption": "liquidity_impact_absorption",
    "liquidity_impact": "liquidity_impact_absorption",
    "flow_response_residual": "liquidity_impact_absorption",
    "liquidity_impact_absorption": "liquidity_impact_absorption",
    "downside_volatility": "price_path_risk",
    "upside_volatility": "price_path_risk",
    "return_skewness": "price_path_risk",
    "price_path_risk": "price_path_risk",
}
CALLS = frozenset(
    {
        "rank",
        "mean",
        "std",
        "sum",
        "abs",
        "log",
        "sqrt",
        "lag",
        "period_return",
        "volatility",
        "rolling_response",
        "response_residual",
        "ridge_rank_score",
    }
)


def sha256_json(value):
    # This module intentionally has only standard-library imports: inspecting a
    # generator's syntax must not import that generator or execute its module.
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def canonical_expression(expression):
    """Small symbolic grammar; no evaluation, rewrites across division, or reassociation."""

    def visit(n):
        if isinstance(n, ast.Name) and not n.id.startswith("_"):
            return ["field", n.id]
        if isinstance(n, ast.Constant) and type(n.value) in (int, float):
            if not math.isfinite(n.value):
                raise ValueError("finite literal required")
            literal = int(n.value) if type(n.value) is float and n.value.is_integer() else n.value
            return ["number", literal]
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            return [type(n.op).__name__, visit(n.operand)]
        if isinstance(n, ast.BinOp) and isinstance(
            n.op, (ast.Add, ast.Mult, ast.Sub, ast.Div, ast.Pow)
        ):
            args = [visit(n.left), visit(n.right)]
            if isinstance(n.op, (ast.Add, ast.Mult)):
                args.sort(key=repr)
            return [type(n.op).__name__, *args]
        if (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id in CALLS
            and not n.keywords
        ):
            return ["call", n.func.id, *map(visit, n.args)]
        raise ValueError("unsupported symbolic expression; manual review required")

    return visit(ast.parse(expression.strip(), mode="eval").body)


def lineage_keys(
    *,
    family,
    expression,
    required_fields,
    sources,
    lookback,
    forecast_sessions,
    direction,
    execution_timing,
    legacy_ids=(),
    narrative="",
):
    """Additive semantic keys; the family alias map is reviewed, not a novelty oracle."""
    del narrative  # Wording is deliberately not an identity or tombstone escape hatch.
    if family not in FAMILIES:
        raise ValueError("unmapped family requires explicit semantic review")
    if any(type(x) is not int or x < 1 for x in (lookback, forecast_sessions)):
        raise ValueError("positive finite integer lookback/horizon required")
    if type(direction) is not int or direction not in (-1, 1):
        raise ValueError("explicit direction required")
    if (
        execution_timing != "T+1_OPEN"
        or not required_fields
        or not sources
        or isinstance(required_fields, str)
        or isinstance(sources, str)
        or any(
            not isinstance(x, str) or not x.strip() or x.strip() != x
            for x in (*required_fields, *sources)
        )
    ):
        raise ValueError("explicit source fields and frozen timing required")
    if any(len(x) != 64 or any(c not in "0123456789abcdef" for c in x) for x in legacy_ids):
        raise ValueError("legacy identity must be SHA256")
    canonical = canonical_expression(expression)
    family_id = sha256_json({"version": VERSION, "family": FAMILIES[family]})
    expression_id = sha256_json(
        {
            "family_id": family_id,
            "expression": canonical,
            "fields": sorted(set(required_fields)),
            "sources": sorted(set(sources)),
        }
    )
    policy_id = sha256_json(
        {
            "expression_id": expression_id,
            "lookback": lookback,
            "forecast_sessions": forecast_sessions,
            "direction": direction,
            "execution_timing": execution_timing,
        }
    )
    return {
        "family": FAMILIES[family],
        "family_id": family_id,
        "expression_id": expression_id,
        "policy_id": policy_id,
        "legacy_ids": sorted(set(legacy_ids)),
        "novelty_status": "NOT_ESTABLISHED_BY_UNMATCHED_HASH",
        "debt_reset_allowed": False,
    }


def freeze_lineage_packet(
    entries, *, budget, policy_tombstones=(), family_tombstones=(), legacy_tombstone_aliases=None
):
    """Finite new-workflow packet gate; old packets/IDs are never mutated.

    Failed-family evidence is not automatically a ban on all future estimators.
    Explicit tombstones are bans; any new within-family research must inherit its
    statistical debt and be separately preregistered, not use a wording escape.
    """
    if type(budget) is not int or budget < 1:
        raise ValueError("positive explicit proposal budget required")
    aliases = {} if legacy_tombstone_aliases is None else dict(legacy_tombstone_aliases)
    hashes = [*policy_tombstones, *family_tombstones, *aliases, *aliases.values()]
    if any(
        not isinstance(h, str) or len(h) != 64 or any(c not in "0123456789abcdef" for c in h)
        for h in hashes
    ):
        raise ValueError("explicit canonical or legacy tombstone hashes required")
    blocked = set(policy_tombstones) | set(aliases.values())
    candidates = []
    for entry in entries:
        if (
            set(entry) != {"name", "lineage"}
            or not isinstance(entry["name"], str)
            or not entry["name"].strip()
        ):
            raise ValueError("named recipe with explicit lineage required")
        keys = lineage_keys(**entry["lineage"])
        candidates.append({"name": entry["name"], "keys": keys, "recipe": entry["lineage"]})
    selected, rejected = {}, []
    for item in sorted(
        candidates, key=lambda e: (e["keys"]["policy_id"], e["name"], sha256_json(e["recipe"]))
    ):
        key = item["keys"]
        if (
            key["policy_id"] in blocked
            or key["family_id"] in family_tombstones
            or set(key["legacy_ids"]) & aliases.keys()
        ):
            reason = "tombstone"
        elif key["policy_id"] in selected:
            reason = "canonical_duplicate"
            # Preserve all legacy identities even when the description was duplicated.
            selected[key["policy_id"]]["keys"]["legacy_ids"] = sorted(
                set(selected[key["policy_id"]]["keys"]["legacy_ids"]) | set(key["legacy_ids"])
            )
        else:
            selected[key["policy_id"]] = item
            continue
        rejected.append({"name": item["name"], "policy_id": key["policy_id"], "reason": reason})
    if len(selected) > budget:
        raise ValueError("finite packet exceeds budget; no implicit winner selection")
    payload = {
        "version": VERSION,
        "budget": budget,
        "proposed": len(candidates),
        "accepted": [selected[k] for k in sorted(selected)],
        "rejected": rejected,
        "tombstones": {
            "policies": sorted(blocked),
            "families": sorted(family_tombstones),
            "legacy_aliases": aliases,
        },
        "historical_debt_reset_allowed": False,
        "empirical_trials_added": 0,
        "requires_empirical_preregistration": True,
    }
    return payload | {"packet_sha256": sha256_json(payload)}


def source_inventory(root: Path, paths=REPO_SOURCES):
    """Parse an explicit list of source files only; dynamic expansion remains unresolved."""
    root = root.resolve()
    if len(paths) != len(set(paths)):
        raise ValueError("duplicate source path")
    units, files = [], {}
    for relative in sorted(paths):
        rel = Path(relative)
        if rel.is_absolute() or ".." in rel.parts or rel.suffix != ".py":
            raise ValueError("relative Python source path required")
        path = (root / rel).resolve()
        if root not in path.parents:
            raise ValueError("source path escapes root")
        raw = path.read_bytes()
        files[rel.as_posix()] = hashlib.sha256(raw).hexdigest()
        tree = ast.parse(raw.decode("utf-8-sig"))

        def add(kind, name, node, details, source_path=rel):
            units.append(
                {
                    "source": source_path.as_posix(),
                    "kind": kind,
                    "name": name,
                    "line": node.lineno,
                    "end_line": node.end_lineno,
                    "ast_sha256": sha256_json(ast.dump(node, include_attributes=False)),
                    "details": details,
                }
            )

        def value(n):
            try:
                literal = ast.literal_eval(n)
                # Sets/bytes can occur in recipes; keep an unevaluated expression instead.
                json.dumps(literal, sort_keys=True, allow_nan=False)
                return {"literal": literal}
            except (TypeError, ValueError, SyntaxError):
                return {"dynamic_source": ast.unparse(n), "requires_expansion_review": True}

        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                add(
                    "function",
                    n.name,
                    n,
                    {
                        "doc": ast.get_docstring(n),
                        "not_expanded": True,
                        "implementation": ast.unparse(n),
                    },
                )
            elif isinstance(n, ast.Assign):
                names = [t.id for t in n.targets if isinstance(t, ast.Name) and t.id.isupper()]
                if names:
                    add("constant", ",".join(names), n, value(n.value))
        for n in ast.walk(tree):
            if (
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id
                in {"_definition", "FactorTemplate", "MechanismRecipe", "V10Field", "SearchField"}
            ):
                add(
                    "declaration",
                    n.func.id,
                    n,
                    {
                        "args": [value(a) for a in n.args],
                        "keywords": {
                            k.arg: value(k.value) for k in n.keywords if k.arg is not None
                        },
                    },
                )
            if isinstance(n, ast.If) and any(
                isinstance(x, ast.Name) and x.id == "family" for x in ast.walk(n.test)
            ):
                add(
                    "family_branch",
                    ast.unparse(n.test),
                    n,
                    {
                        "implementation": [ast.unparse(x) for x in n.body],
                        "not_a_runtime_candidate_enumeration": True,
                    },
                )
    units.sort(key=lambda r: (r["source"], r["line"], r["kind"]))
    payload = {
        "version": VERSION,
        "files": files,
        "units": units,
        "market_rows_read": 0,
        "empirical_trials_added": 0,
        "limits": "source units,not exhaustively expanded candidates; unmatched syntax is not novelty; narrative-independent keys are additive,not historical rewrites",
    }
    return payload | {"inventory_sha256": sha256_json(payload)}
