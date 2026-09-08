"""Reference-side query coverage, including writeoff-free open stale tails."""

from .account_forensics_verify import compare
from .account_forensics_verify_events import count


def required_source_keys(references):
    """Inputs are independently derive_events results, not producer event output."""
    keys, accounts = set(), set()
    for reference in references:
        account = reference["account"]
        if account in accounts:
            raise ValueError("duplicate reference account")
        accounts.add(account)
        for row in reference["events"] + reference["open_stale_chains"]:
            chain, name = row["stale_chain"], row["instrument"]
            keys.add((chain["last_marked_date"], name))
            for session in chain["missing_sessions"]:
                keys.add((session["date"], name))
            if row.get("event_type") == "recovery":
                keys.add((row["date"], name))
    return sorted(keys)


def verify_lookup_coverage(references, requested, lookups, receipt):
    """No numerical requery here: verify the actual reader output's complete keyset.

    The final runtime must directly invoke its frozen reader, bind source bytes
    and this code, and supply reference events derived from original reports.
    Caller-invented dictionaries alone are not source-truth evidence.
    """
    expected = required_source_keys(references)
    if list(requested) != expected or set(lookups) != set(expected):
        raise ValueError("independent required/requested/returned key coverage mismatch")
    found = 0
    for key, row in lookups.items():
        if row is not None:
            if not isinstance(row, dict) or (row.get("trade_date"), row.get("instrument")) != key:
                raise ValueError("returned source identity mismatch")
            if set(row) != {"trade_date", "instrument", "name", "open", "close", "amount",
                            "volume", "adjustment_factor", "available_at"}:
                raise ValueError("actual returned row must contain the exact nine-field projection")
            found += 1
    count(receipt["requested_keys"], len(expected))
    count(receipt["matched_rows"], found)
    count(receipt["absent_keys"], len(expected) - found)
    if expected:
        compare(receipt["input_bytes_unchanged"], True)
        compare(receipt["query_projection"], ["trade_date", "instrument", "name", "open", "close",
                                               "amount", "volume", "adjustment_factor", "available_at"])
    return {"independent_lookup_coverage_verified": True, "requested_keys": len(expected),
            "matched_rows": found, "absent_keys": len(expected) - found,
            "actual_suspension_or_delisting_verified": False, "validated_alpha": False}
