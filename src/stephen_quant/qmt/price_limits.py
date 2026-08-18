from __future__ import annotations

from dataclasses import dataclass
from datetime import date

PRICE_LIMIT_RULE_VERSION = "a-share-price-limit-1.0.0"
CHINEXT_REFORM_DATE = date(2020, 8, 24)
BSE_OPEN_DATE = date(2021, 11, 15)
MAIN_REGISTRATION_DATE = date(2023, 4, 10)


@dataclass(frozen=True)
class PriceLimitContext:
    instrument: str
    trade_date: str
    is_st: bool | None = None
    listing_session: int | None = None


@dataclass(frozen=True)
class PriceLimitRule:
    board: str
    ratio: float | None
    has_limit: bool
    evidence_quality: str
    reason: str
    version: str = PRICE_LIMIT_RULE_VERSION


def classify_a_share_board(instrument: str) -> str:
    code = instrument.split(".", 1)[0].upper()
    if code.startswith(("688", "689")):
        return "STAR"
    if code.startswith(("300", "301")):
        return "CHINEXT"
    if code.startswith(("4", "8", "92")):
        return "BSE"
    if code.startswith(("600", "601", "603", "605", "000", "001", "002", "003")):
        return "MAIN"
    return "UNKNOWN"


def resolve_price_limit_rule(context: PriceLimitContext) -> PriceLimitRule:
    """Resolve a rule while exposing absent ST and listing-age evidence."""
    try:
        trade_day = date.fromisoformat(context.trade_date[:10])
    except ValueError as exc:
        raise ValueError("trade_date must use ISO YYYY-MM-DD") from exc
    if context.listing_session is not None and context.listing_session < 1:
        raise ValueError("listing_session must be positive")
    board = classify_a_share_board(context.instrument)
    if board == "UNKNOWN":
        return PriceLimitRule(board, None, False, "unresolved", "unknown_board")

    session = context.listing_session
    no_limit = False
    reason = "regular_session"
    if session is not None:
        if board == "STAR" and session <= 5:
            no_limit, reason = True, "star_first_five_sessions"
        elif board == "CHINEXT" and trade_day >= CHINEXT_REFORM_DATE and session <= 5:
            no_limit, reason = True, "chinext_registration_first_five_sessions"
        elif board == "BSE" and trade_day >= BSE_OPEN_DATE and session == 1:
            no_limit, reason = True, "bse_listing_first_session"
        elif board == "MAIN" and trade_day >= MAIN_REGISTRATION_DATE and session <= 5:
            no_limit, reason = True, "main_registration_first_five_sessions"
        elif board == "MAIN" and trade_day < MAIN_REGISTRATION_DATE and session == 1:
            no_limit, reason = True, "legacy_main_listing_first_session"
    if no_limit:
        return PriceLimitRule(board, None, False, "exact", reason)

    if board == "STAR":
        ratio = 0.20
    elif board == "CHINEXT":
        ratio = 0.20 if trade_day >= CHINEXT_REFORM_DATE else (0.05 if context.is_st else 0.10)
    elif board == "BSE":
        if trade_day < BSE_OPEN_DATE:
            return PriceLimitRule(board, None, False, "unresolved", "pre_bse_history")
        ratio = 0.30
    else:
        ratio = 0.05 if context.is_st else 0.10

    missing: list[str] = []
    if context.is_st is None and board in {"MAIN", "CHINEXT"}:
        missing.append("st_state")
    if session is None:
        missing.append("listing_session")
    quality = "exact" if not missing else "board_proxy_missing_" + "_and_".join(missing)
    return PriceLimitRule(board, ratio, True, quality, reason)
