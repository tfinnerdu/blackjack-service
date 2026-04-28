"""End-to-end games-service tests covering the round lifecycle.

We pin a deterministic seed and decks/penetration so the deal is
reproducible. When a test depends on specific cards (e.g. testing the
insurance branch), we drive a 1-seat session at that seed and assert
behavior that's true for every legal sequence (state transitions,
bankroll math).
"""
import json

from app import create_app
from app.config import Config
from app.services.games import (
    GameError,
    StartRoundRequest,
    get_active_round_view,
    start_round,
    take_action,
    take_insurance,
)
from app.services.sessions import create_from_template


class _TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test"


def _ctx():
    return create_app(_TestConfig())


def _new_session(app, **overrides):
    """Default to 1 seat at seat 1, no insurance/peek (so we don't deal with
    the insurance-state branch unless a test wants it), deterministic seed."""
    rules = {
        "seats": 1,
        "min_bet": 5,
        "max_bet": 100,
        "bet_increment": 5,
        "insurance_offered": False,
        "dealer_peeks": False,
    }
    rules.update(overrides.pop("rules_overrides", {}))
    with app.app_context():
        sess = create_from_template(
            template_id=None,
            starting_bankroll=overrides.get("bankroll", 500),
            player_seat=1,
            rules_overrides=rules,
            seed=overrides.get("seed", 4242),
        )
        return sess.id  # return id to be re-fetched per request


def _get(app, sid):
    from app.models import GameSession
    return app.extensions["sqlalchemy"].session.get(GameSession, sid)


def test_full_round_to_settlement_updates_bankroll_and_stats():
    app = _ctx()
    sid = _new_session(app)
    with app.app_context():
        sess = _get(app, sid)
        starting = sess.bankroll
        view = start_round(sess, StartRoundRequest(main_bet=10))

        # Drive the round to completion via stand actions. Most deterministic
        # paths terminate within a handful of stands; loop with a guard.
        guard = 0
        while view.state == "playing":
            action = "stand" if "stand" in view.legal_actions else view.legal_actions[0]
            view = take_action(sess, action)
            guard += 1
            assert guard < 12

        assert view.state == "complete"
        assert view.result is not None
        assert sess.active_round_json is None
        # Bankroll moved by exactly the round profit.
        outcomes_profit = sum(o["profit"] for o in view.result["outcomes"])
        assert sess.bankroll - starting == outcomes_profit
        assert sess.hands_played >= 1
        assert sess.cards_dealt > 0


def test_book_mistake_counted_when_action_diverges():
    app = _ctx()
    sid = _new_session(app)
    with app.app_context():
        sess = _get(app, sid)
        view = start_round(sess, StartRoundRequest(main_bet=10))
        if view.state != "playing":
            return  # natural BJ, can't test mistake
        before = sess.book_mistakes
        # Pick whichever legal action is NOT the book recommendation. If
        # the only legal action is the book one, skip.
        recommended = view.book["action"] if view.book else None
        candidates = [a for a in view.legal_actions if a != recommended]
        if not candidates:
            return
        # Take the divergent action; a mistake should be recorded.
        take_action(sess, candidates[0])
        assert sess.book_mistakes == before + 1


def test_no_round_in_flight_means_take_action_errors():
    app = _ctx()
    sid = _new_session(app)
    with app.app_context():
        sess = _get(app, sid)
        import pytest
        with pytest.raises(GameError):
            take_action(sess, "stand")


def test_get_active_round_view_returns_none_when_no_round():
    app = _ctx()
    sid = _new_session(app)
    with app.app_context():
        sess = _get(app, sid)
        assert get_active_round_view(sess) is None


def test_get_active_round_view_returns_view_after_start():
    app = _ctx()
    sid = _new_session(app)
    with app.app_context():
        sess = _get(app, sid)
        view = start_round(sess, StartRoundRequest(main_bet=10))
        if view.state == "complete":
            assert get_active_round_view(sess) is None
            return
        # Re-load via the read-only view helper; should match state.
        v2 = get_active_round_view(sess)
        assert v2 is not None
        assert v2.state == view.state
        assert v2.active_seat_num == view.active_seat_num


def test_round_persists_across_session_reload():
    """Snapshot survives a completely fresh session lookup."""
    app = _ctx()
    sid = _new_session(app)
    with app.app_context():
        sess = _get(app, sid)
        view = start_round(sess, StartRoundRequest(main_bet=10))
        if view.state == "complete":
            return

    # New context simulates a process restart.
    with app.app_context():
        sess2 = _get(app, sid)
        v2 = get_active_round_view(sess2)
        assert v2 is not None
        assert v2.state == view.state


def test_insurance_flow_pays_or_loses():
    """Drive seeds until we land on a dealer A-up. With seats=1 and dealer_peeks=True,
    a few seeds should produce the insurance state."""
    app = _ctx()
    found = False
    with app.app_context():
        for seed in range(1, 60):
            sess = create_from_template(
                template_id=None,
                starting_bankroll=500,
                player_seat=1,
                rules_overrides={
                    "seats": 1,
                    "min_bet": 5, "max_bet": 100, "bet_increment": 5,
                    "insurance_offered": True,
                    "dealer_peeks": True,
                },
                seed=seed,
            )
            view = start_round(sess, StartRoundRequest(main_bet=10))
            if view.state == "insurance":
                found = True
                # Take insurance for $5; round either ends (dealer BJ -> 2:1)
                # or transitions to playing (dealer no BJ -> insurance loses).
                view2 = take_insurance(sess, accept=True, amount=5)
                # Drive any remaining play to completion.
                guard = 0
                while view2.state == "playing":
                    action = "stand" if "stand" in view2.legal_actions else view2.legal_actions[0]
                    view2 = take_action(sess, action)
                    guard += 1
                    assert guard < 12
                assert view2.state == "complete"
                # Insurance result was recorded against the player seat.
                ins = view2.result["insurance_outcomes"]
                assert "1" in ins or 1 in ins
                break
        assert found, "no insurance scenario hit across 60 seeds; check rules"
