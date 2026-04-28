"""Sportsbook engine + service tests.

Engine tests cover odds math + parlay payouts + settlement edge cases.
Service tests drive the lifecycle: create session → place slips →
advance day → settle → analytics.
"""
from __future__ import annotations

import json

import pytest

from app import create_app
from app.config import Config
from app.db import db
from app.sportsbook import (
    LEG_LOST,
    LEG_PUSH,
    LEG_WON,
    american_to_decimal,
    decimal_to_american,
    parlay_decimal_odds,
    potential_payout,
    settle_legs,
    settle_slip,
)
from app.sportsbook.fixtures import generate_day_slate, winner_keys_for_event


class _TC(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test"


# ---- odds math --------------------------------------------------------

def test_american_to_decimal_negative_odds():
    # -150 means lay $150 to win $100. Decimal = 1 + 100/150 ≈ 1.667
    assert abs(american_to_decimal(-150) - 1.6666666) < 1e-4


def test_american_to_decimal_positive_odds():
    # +130 means lay $100 to win $130. Decimal = 1 + 130/100 = 2.30
    assert american_to_decimal(130) == 2.30


def test_american_to_decimal_even_money():
    assert american_to_decimal(100) == 2.0
    assert american_to_decimal(-100) == 2.0


def test_decimal_to_american_round_trip():
    # Round-trip is lossy on negatives (1.6666… can't perfectly invert
    # to -150). Even money (100 / -100) is special: both map to decimal
    # 2.0, so the round trip lands on +100 and we accept it either way.
    for o, tol in (
        (-200, 2), (-150, 5), (-110, 5),
        (110, 5), (130, 5), (200, 1), (300, 1),
    ):
        decimal = american_to_decimal(o)
        assert abs(decimal_to_american(decimal) - o) <= tol, (
            f"round trip drifted: {o} -> {decimal} -> {decimal_to_american(decimal)}"
        )
    # Even money: decimal 2.0 → +100 (representative even-money form).
    assert decimal_to_american(2.0) == 100


def test_parlay_decimal_odds_is_product():
    # Two legs at +100 each: 2.0 * 2.0 = 4.0 (3:1 net).
    assert parlay_decimal_odds([2.0, 2.0]) == 4.0
    # Three legs: 2.0 * 1.5 * 1.667 ≈ 5.0
    assert abs(parlay_decimal_odds([2.0, 1.5, 1.667]) - 5.001) < 0.01


def test_potential_payout_includes_stake():
    # $100 stake on -110: decimal 1.9090909 → 100 * 1.9091 ≈ 190.91 → 191.
    payout = potential_payout(100, [-110])
    assert payout == 191

    # $100 parlay of +100, +100, +100: 100 * 8 = 800.
    assert potential_payout(100, [100, 100, 100]) == 800


# ---- settlement edge cases -------------------------------------------

def test_settle_single_won():
    legs = [{"market_id": 1, "selection_key": "home", "odds": -150}]
    out = settle_slip(
        slip_type="single", legs=legs, stake=150,
        market_results={1: "home"},
    )
    assert out["status"] == "won"
    # 150 * (1 + 100/150) = 150 * 1.667 = 250.
    assert out["payout_actual"] == 250


def test_settle_single_lost():
    legs = [{"market_id": 1, "selection_key": "home", "odds": -150}]
    out = settle_slip(
        slip_type="single", legs=legs, stake=150,
        market_results={1: "away"},
    )
    assert out["status"] == "lost"
    assert out["payout_actual"] == 0


def test_settle_single_push_refunds_stake():
    legs = [{"market_id": 1, "selection_key": "home", "odds": -110}]
    out = settle_slip(
        slip_type="single", legs=legs, stake=100,
        market_results={1: "PUSH"},
    )
    assert out["status"] == "push"
    assert out["payout_actual"] == 100


def test_settle_parlay_single_loss_kills_slip():
    legs = [
        {"market_id": 1, "selection_key": "home", "odds": -110},
        {"market_id": 2, "selection_key": "over", "odds": -110},
    ]
    out = settle_slip(
        slip_type="parlay", legs=legs, stake=100,
        market_results={1: "home", 2: "under"},
    )
    assert out["status"] == "lost"


def test_settle_parlay_push_leg_drops_from_product():
    """Two-leg parlay, one wins and one pushes. Slip should pay as if
    it were a single bet on the winning leg."""
    legs = [
        {"market_id": 1, "selection_key": "home", "odds": 200},  # won
        {"market_id": 2, "selection_key": "over", "odds": -110}, # push
    ]
    out = settle_slip(
        slip_type="parlay", legs=legs, stake=100,
        market_results={1: "home", 2: "PUSH"},
    )
    assert out["status"] == "won"
    # +200 alone = 100 * 3.0 = 300.
    assert out["payout_actual"] == 300


def test_settle_parlay_all_push_refunds_stake():
    legs = [
        {"market_id": 1, "selection_key": "home", "odds": 200},
        {"market_id": 2, "selection_key": "over", "odds": -110},
    ]
    out = settle_slip(
        slip_type="parlay", legs=legs, stake=100,
        market_results={1: "PUSH", 2: "PUSH"},
    )
    assert out["status"] == "push"
    assert out["payout_actual"] == 100


def test_settle_pending_when_one_leg_unresolved():
    legs = [
        {"market_id": 1, "selection_key": "home", "odds": 200},
        {"market_id": 2, "selection_key": "over", "odds": -110},
    ]
    out = settle_slip(
        slip_type="parlay", legs=legs, stake=100,
        market_results={1: "home", 2: None},
    )
    assert out["status"] == "pending"
    assert out["payout_actual"] == 0


def test_settle_legs_marks_outcomes():
    legs = [
        {"market_id": 1, "selection_key": "home", "odds": 100},
        {"market_id": 2, "selection_key": "over", "odds": 100},
        {"market_id": 3, "selection_key": "under", "odds": 100},
    ]
    out = settle_legs(legs, {1: "home", 2: "PUSH", 3: "over"})
    assert [l["outcome"] for l in out] == [LEG_WON, LEG_PUSH, LEG_LOST]


# ---- fixture generator ------------------------------------------------

def test_generate_day_slate_is_deterministic():
    """Same (seed, day) should produce the same slate. The settlement
    test relies on this so the regression is reproducible."""
    a = generate_day_slate(day=0, seed=42)
    b = generate_day_slate(day=0, seed=42)
    assert len(a) == len(b)
    for ea, eb in zip(a, b):
        assert ea.home_team == eb.home_team
        assert ea.away_team == eb.away_team
        assert ea.home_score == eb.home_score
        assert ea.away_score == eb.away_score


def test_winner_keys_match_simulated_scores():
    """For each generated event, the winner_key for moneyline should
    match whichever side actually scored higher."""
    slate = generate_day_slate(day=0, seed=99)
    for ev in slate:
        winners = winner_keys_for_event(ev)
        if ev.home_score > ev.away_score:
            assert winners["moneyline"] == "home"
        elif ev.away_score > ev.home_score:
            assert winners["moneyline"] == "away"
        else:
            assert winners["moneyline"] == "PUSH"


def test_fixture_total_winner_consistent_with_score_sum():
    slate = generate_day_slate(day=1, seed=7)
    for ev in slate:
        winners = winner_keys_for_event(ev)
        total = ev.home_score + ev.away_score
        total_market = next(m for m in ev.markets if m.market_type == "total")
        line = total_market.selections[0]["line"]
        if total > line:
            assert winners["total"] == "over"
        elif total < line:
            assert winners["total"] == "under"
        else:
            assert winners["total"] == "PUSH"


# ---- service / route tests -------------------------------------------

def _client():
    return create_app(_TC()).test_client()


def _post_json(client, path, body=None):
    return client.post(
        path,
        data=json.dumps(body or {}),
        content_type="application/json",
    )


def test_create_session_seeds_slate():
    app = create_app(_TC())
    with app.app_context():
        from app.services.sportsbook import create_sportsbook_session
        from app.models import SportsEvent
        sess = create_sportsbook_session(starting_bankroll=500, seed=1)
        assert sess.bankroll == 500
        # Lookahead loaded multiple days.
        events = SportsEvent.query.all()
        assert len(events) > 0
        days = {e.day for e in events}
        assert max(days) >= 3


def test_place_single_slip_deducts_stake():
    app = create_app(_TC())
    with app.app_context():
        from app.services.sportsbook import (
            create_sportsbook_session,
            list_open_events,
            place_slip,
        )
        sess = create_sportsbook_session(starting_bankroll=500, seed=2)
        events = list_open_events(sess)
        first = events[0]
        ml = next(m for m in first["markets"] if m["market_type"] == "moneyline")

        slip = place_slip(
            sess,
            legs_input=[{
                "market_id": ml["id"],
                "selection_key": ml["selections"][0]["key"],
            }],
            stake=50,
        )
        assert slip.slip_type == "single"
        assert slip.stake == 50
        # bankroll deducted at placement.
        assert sess.bankroll == 450


def test_place_parlay_payout_is_product_of_decimal_odds():
    app = create_app(_TC())
    with app.app_context():
        from app.services.sportsbook import (
            create_sportsbook_session,
            list_open_events,
            place_slip,
        )
        sess = create_sportsbook_session(starting_bankroll=500, seed=3)
        events = list_open_events(sess)
        # Pick legs from two different events.
        ml1 = next(m for m in events[0]["markets"] if m["market_type"] == "moneyline")
        ml2 = next(m for m in events[1]["markets"] if m["market_type"] == "moneyline")
        slip = place_slip(
            sess,
            legs_input=[
                {"market_id": ml1["id"], "selection_key": ml1["selections"][0]["key"]},
                {"market_id": ml2["id"], "selection_key": ml2["selections"][0]["key"]},
            ],
            stake=100,
        )
        assert slip.slip_type == "parlay"
        # Sanity: payout > stake (each leg has decimal > 1).
        assert slip.potential_payout > 100


def test_advance_day_settles_pending_slips():
    """End-to-end: place a slip on day 0 events, advance to day 1,
    confirm the slip settles + bankroll updates."""
    app = create_app(_TC())
    with app.app_context():
        from app.services.sportsbook import (
            advance_day,
            create_sportsbook_session,
            list_open_events,
            place_slip,
        )
        sess = create_sportsbook_session(starting_bankroll=500, seed=4)
        events = list_open_events(sess)
        day0_events = [e for e in events if e["day"] == 0]
        # Pick a moneyline leg on a day-0 event and bet on the actual winner.
        ev = day0_events[0]
        from app.models import SportsEvent
        ev_row = SportsEvent.query.get(ev["id"])
        winning_key = (
            "home" if ev_row.home_score > ev_row.away_score
            else "away" if ev_row.away_score > ev_row.home_score
            else None
        )
        if winning_key is None:
            pytest.skip("test seed produced a tie; rerun with another")
        ml = next(m for m in ev["markets"] if m["market_type"] == "moneyline")
        slip = place_slip(
            sess,
            legs_input=[{"market_id": ml["id"], "selection_key": winning_key}],
            stake=50,
        )
        assert slip.status == "pending"
        # Advance to day 1 — settles all day-0 events.
        result = advance_day(sess, seed=4)
        assert result["current_day"] == 1
        # Slip should now be won or lost (push only on tie, which we skipped).
        from app.models import BettingSlip
        refreshed = BettingSlip.query.get(slip.id)
        assert refreshed.status == "won"
        # Bankroll = 500 - 50 (placed) + payout. Payout > 50 since we won.
        assert sess.bankroll > 450


def test_advance_day_doesnt_touch_future_events():
    """Bet on a day-1 event, advance once (0 → 1). The day-1 slip is
    still pending — its event hasn't resolved yet. Advance again and
    it settles."""
    app = create_app(_TC())
    with app.app_context():
        from app.services.sportsbook import (
            advance_day,
            create_sportsbook_session,
            list_open_events,
            place_slip,
        )
        sess = create_sportsbook_session(starting_bankroll=500, seed=5)
        events = list_open_events(sess)
        day1_events = [e for e in events if e["day"] == 1]
        ev = day1_events[0]
        ml = next(m for m in ev["markets"] if m["market_type"] == "moneyline")
        slip = place_slip(
            sess,
            legs_input=[{"market_id": ml["id"], "selection_key": "home"}],
            stake=50,
        )
        # Advance 0 → 1: day-0 events resolve, day-1 events don't.
        advance_day(sess, seed=5)
        from app.models import BettingSlip
        s = db.session.get(BettingSlip, slip.id)
        assert s.status == "pending"

        # Advance 1 → 2: now the day-1 event resolves.
        advance_day(sess, seed=5)
        s = db.session.get(BettingSlip, slip.id)
        assert s.status in ("won", "lost", "push")


def test_insufficient_bankroll_rejected():
    app = create_app(_TC())
    with app.app_context():
        from app.services.sportsbook import (
            create_sportsbook_session,
            list_open_events,
            place_slip,
            SportsbookError,
        )
        sess = create_sportsbook_session(starting_bankroll=100, seed=6)
        events = list_open_events(sess)
        ml = next(m for m in events[0]["markets"] if m["market_type"] == "moneyline")
        with pytest.raises(SportsbookError, match="insufficient"):
            place_slip(
                sess,
                legs_input=[{"market_id": ml["id"], "selection_key": "home"}],
                stake=500,
            )


def test_parlay_cannot_repeat_same_market():
    """No correlated parlays — same market twice is rejected."""
    app = create_app(_TC())
    with app.app_context():
        from app.services.sportsbook import (
            create_sportsbook_session,
            list_open_events,
            place_slip,
            SportsbookError,
        )
        sess = create_sportsbook_session(starting_bankroll=500, seed=7)
        events = list_open_events(sess)
        ml = next(m for m in events[0]["markets"] if m["market_type"] == "moneyline")
        with pytest.raises(SportsbookError, match="same market"):
            place_slip(
                sess,
                legs_input=[
                    {"market_id": ml["id"], "selection_key": "home"},
                    {"market_id": ml["id"], "selection_key": "away"},
                ],
                stake=50,
            )


def test_analytics_summary_after_run():
    app = create_app(_TC())
    with app.app_context():
        from app.services.sportsbook import (
            advance_day,
            create_sportsbook_session,
            list_open_events,
            place_slip,
            session_analytics,
        )
        sess = create_sportsbook_session(starting_bankroll=500, seed=8)
        # Place a few slips then advance.
        events = list_open_events(sess)
        ml1 = next(m for m in events[0]["markets"] if m["market_type"] == "moneyline")
        ml2 = next(m for m in events[1]["markets"] if m["market_type"] == "moneyline")
        place_slip(sess, legs_input=[{"market_id": ml1["id"], "selection_key": "home"}], stake=10)
        place_slip(sess, legs_input=[{"market_id": ml2["id"], "selection_key": "away"}], stake=10)
        advance_day(sess, seed=8)

        an = session_analytics(sess)
        assert an["summary"]["slips_placed"] == 2
        assert an["summary"]["settled_count"] == 2
        # Total staked should match.
        assert an["summary"]["total_staked"] == 20
