from __future__ import annotations

import pytest

from stephen_quant.qmt import (
    PriceLimitContext,
    classify_a_share_board,
    resolve_price_limit_rule,
)


def test_board_classification_covers_main_chinext_star_and_bse() -> None:
    assert classify_a_share_board("600000.SH") == "MAIN"
    assert classify_a_share_board("000001.SZ") == "MAIN"
    assert classify_a_share_board("300001.SZ") == "CHINEXT"
    assert classify_a_share_board("688001.SH") == "STAR"
    assert classify_a_share_board("920001.BJ") == "BSE"


def test_chinext_reform_boundary_and_risk_warning_rule() -> None:
    before = resolve_price_limit_rule(
        PriceLimitContext("300001.SZ", "2020-08-21", is_st=False, listing_session=100)
    )
    before_st = resolve_price_limit_rule(
        PriceLimitContext("300001.SZ", "2020-08-21", is_st=True, listing_session=100)
    )
    after_st = resolve_price_limit_rule(
        PriceLimitContext("300001.SZ", "2020-08-24", is_st=True, listing_session=100)
    )

    assert before.ratio == pytest.approx(0.10)
    assert before_st.ratio == pytest.approx(0.05)
    assert after_st.ratio == pytest.approx(0.20)


@pytest.mark.parametrize(
    ("instrument", "day", "session", "reason"),
    [
        ("688001.SH", "2022-01-03", 5, "star_first_five_sessions"),
        ("300001.SZ", "2022-01-03", 5, "chinext_registration_first_five_sessions"),
        ("600001.SH", "2023-04-10", 5, "main_registration_first_five_sessions"),
        ("830001.BJ", "2022-01-03", 1, "bse_listing_first_session"),
    ],
)
def test_no_limit_listing_sessions_are_explicit(
    instrument: str, day: str, session: int, reason: str
) -> None:
    rule = resolve_price_limit_rule(
        PriceLimitContext(instrument, day, is_st=False, listing_session=session)
    )

    assert not rule.has_limit
    assert rule.ratio is None
    assert rule.reason == reason
    assert rule.evidence_quality == "exact"


def test_missing_st_and_listing_age_are_never_presented_as_exact() -> None:
    rule = resolve_price_limit_rule(PriceLimitContext("600000.SH", "2024-01-03"))

    assert rule.ratio == pytest.approx(0.10)
    assert "st_state" in rule.evidence_quality
    assert "listing_session" in rule.evidence_quality


def test_unknown_board_and_invalid_listing_session_fail_closed() -> None:
    assert not resolve_price_limit_rule(
        PriceLimitContext("XYZ", "2024-01-03")
    ).has_limit
    with pytest.raises(ValueError, match="listing_session must be positive"):
        resolve_price_limit_rule(
            PriceLimitContext("600000.SH", "2024-01-03", listing_session=0)
        )
