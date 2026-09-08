"""Independent event identities from original marks and explicit saved bars.

No calls to producer event extraction or chain reconciliation. This verifies
saved accounting evidence, not vendor completeness or actual corporate events.
"""

from copy import deepcopy

from .account_forensics_verify import compare


def count(actual, expected):
    if type(actual) is not int or actual != expected:
        raise ValueError("exact integer event count required")


def index(rows):
    result = {r["instrument"]: r for r in rows}
    if len(result) != len(rows):
        raise ValueError("duplicate saved identity")
    return result


def integer_ages(event):
    if "stale_sessions" in event:
        count(event["stale_sessions"], int(event["stale_sessions"]))
    for row in event["stale_chain"]["missing_sessions"]:
        count(row["stale_sessions"], int(row["stale_sessions"]))


def derive_events(account, report, *, calendar, bars):
    """Reference events/tails from raw saved account/history, never producer chains."""
    dates = list(calendar)
    if (not dates or dates != sorted(set(dates))
            or [p["trade_date"] for p in report["periods"]] != dates
            or any(dt not in bars for dt in dates)):
        raise ValueError("complete independent event calendar required")
    count(report["config"]["stale_writeoff_sessions"], 20)
    previous, missing, expected = {}, {}, {}
    last_date, totals = None, {"writeoff": 0, "recovery": 0}
    for p in report["periods"]:
        dt = p["trade_date"]
        current, orders = index(p["marks"]), index(p["orders"])
        for name in current.keys() - previous.keys():
            mark, bar = current[name], bars[dt].get(name)
            count(mark["stale_sessions"], 0)
            if (bar is None or bar["trade_date"] != dt or bar["instrument"] != name
                    or mark["source"] != "current_close" or mark["shares"] <= 0):
                raise ValueError("new holding requires a current saved bar and positive shares")
        losses, recoveries = [], []
        for name, prior in previous.items():
            mark, bar = current.get(name), bars[dt].get(name)
            if bar is None:
                if mark is None:
                    raise ValueError("missing-bar holding disappeared")
                age = prior["stale_sessions"] + 1
                count(mark["stale_sessions"], age)
                compare(mark["shares"], prior["shares"])
                if name not in missing:
                    count(prior["stale_sessions"], 0)
                    missing[name] = {"last_marked_date": last_date,
                                     "last_mark_price": prior["mark_price"],
                                     "prior_shares": prior["shares"], "missing_sessions": []}
                missing[name]["missing_sessions"].append(
                    {"date": dt, "stale_sessions": age, "saved_bar_present": False})
                if age >= 20:
                    compare(mark["mark_price"], 0)
                    if mark["source"] != "conservative_zero_writeoff":
                        raise ValueError("stale20 zero-source mismatch")
                if age == 20:
                    value = prior["shares"] * prior["mark_price"]
                    compare(value, prior["market_value"])
                    losses.append(value)
                    expected[(dt, name, "writeoff")] = {
                        "account": account, "date": dt, "instrument": name,
                        "event_type": "writeoff", "amount_cny": value,
                        "prior_shares": prior["shares"], "prior_mark_price": prior["mark_price"],
                        "prior_date": last_date, "stale_sessions": age,
                        "stale_chain": deepcopy(missing[name]),
                    }
            else:
                if bar["trade_date"] != dt or bar["instrument"] != name:
                    raise ValueError("saved source-bar identity mismatch")
                if prior["stale_sessions"] >= 20:
                    if name not in missing or bar["open_price"] <= 0:
                        raise ValueError("complete missing chain and positive recovery open required")
                    value = prior["shares"] * bar["open_price"]
                    recoveries.append(value)
                    expected[(dt, name, "recovery")] = {
                        "account": account, "date": dt, "instrument": name,
                        "event_type": "recovery", "prior_shares": prior["shares"],
                        "prior_date": last_date, "disposed_by_close": mark is None,
                        "saved_bar_recovery_cny": value, "saved_bar_open_price": bar["open_price"],
                        "stale_chain": deepcopy(missing[name]),
                        "recovery_order": orders.get(name), "recovery_end_mark": mark,
                    }
                missing.pop(name, None)
                if mark is not None:
                    count(mark["stale_sessions"], 0)
        for kind, values, field in (("writeoff", losses, "writeoff_loss"),
                                    ("recovery", recoveries, "recovery_value")):
            count(p[kind + "_positions"], len(values))
            compare(p[field], sum(values))
            totals[kind] += len(values)
        count(p["stale_position_days"], sum(m["stale_sessions"] > 0 for m in current.values()))
        previous, last_date = current, dt
    tails = [{"account": account, "instrument": name, "through_date": dates[-1],
              "written_down_at_end": previous[name]["stale_sessions"] >= 20, "stale_chain": chain}
             for name, chain in sorted(missing.items())]
    for kind, n in totals.items():
        count(report["metrics"][kind + "_events"], n)
    return {"account": account, "events": [expected[k] for k in sorted(expected)],
            "open_stale_chains": tails, "sessions": len(dates), "totals": totals}


def verify_events(account, report, emitted, *, calendar, bars):
    reference = derive_events(account, report, calendar=calendar, bars=bars)
    return verify_derived_events(reference, emitted)


def verify_derived_events(reference, emitted):
    """Used after derive_events on original inputs; not a public certification receipt."""
    expected = {(e["date"], e["instrument"], e["event_type"]): e for e in reference["events"]}
    actual = {(e["date"], e["instrument"], e["event_type"]): e for e in emitted["events"]}
    if len(actual) != len(emitted["events"]) or set(actual) != set(expected):
        raise ValueError("independent complete event identity set mismatch")
    for key, event in expected.items():
        integer_ages(actual[key])
        compare({field: actual[key][field] for field in event}, event)
    tails = reference["open_stale_chains"]
    for tail in emitted["open_stale_chains"]:
        integer_ages(tail)
    compare(emitted["open_stale_chains"], tails)
    compare(emitted["account"], reference["account"])
    count(emitted["sessions_checked"], reference["sessions"])
    return {"saved_event_identities_verified": True, "sessions": reference["sessions"],
            "writeoff_events": reference["totals"]["writeoff"],
            "recovery_events": reference["totals"]["recovery"],
            "open_stale_chains": len(tails), "source_truth_verified": False,
            "validated_alpha": False}
