"""Smoke tests for games.start_round. Full-flow tests (action, insurance,
settle) land in test_games_flow.py once those service paths exist.
"""
import json

from app import create_app
from app.config import Config
from app.models import GameSession
from app.services.games import StartRoundRequest, start_round
from app.services.sessions import create_from_template


class _TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test"


def _ctx():
    app = create_app(_TestConfig())
    return app


def test_start_round_deals_to_human_and_returns_legal_actions():
    app = _ctx()
    with app.app_context():
        sess = create_from_template(
            template_id=None,
            starting_bankroll=500,
            player_seat=1,
            rules_overrides={"seats": 1, "min_bet": 5, "max_bet": 100, "bet_increment": 5,
                             "insurance_offered": False, "dealer_peeks": False},
            seed=1234,
        )
        view = start_round(sess, StartRoundRequest(main_bet=10))
        # Either the human is to act (most likely) or the round completed
        # because of a natural BJ. Both are OK; just assert internal consistency.
        assert view.state in ("playing", "complete")
        if view.state == "playing":
            assert view.active_seat_num == 1
            assert view.legal_actions  # something to do
            assert view.book is not None
            assert view.book["action"] in ("hit", "stand", "double", "split", "surrender")
        # A round-in-flight row should be persisted unless we settled.
        assert (sess.active_round_json is None) == (view.state == "complete")


def test_start_round_rejects_bet_above_bankroll():
    app = _ctx()
    with app.app_context():
        sess = create_from_template(
            template_id=None,
            starting_bankroll=20,
            player_seat=1,
            rules_overrides={"seats": 1, "min_bet": 5, "max_bet": 100, "bet_increment": 5},
        )
        import pytest
        from app.services.games import GameError
        with pytest.raises(GameError):
            start_round(sess, StartRoundRequest(main_bet=50))


def test_start_round_rejects_double_start():
    app = _ctx()
    with app.app_context():
        sess = create_from_template(
            template_id=None, starting_bankroll=500, player_seat=1,
            rules_overrides={"seats": 1, "min_bet": 5, "max_bet": 100, "bet_increment": 5,
                             "insurance_offered": False, "dealer_peeks": False},
            seed=1,
        )
        view = start_round(sess, StartRoundRequest(main_bet=10))
        if view.state == "complete":
            return  # round auto-finished, can't test double-start cleanly
        import pytest
        from app.services.games import GameError
        with pytest.raises(GameError):
            start_round(sess, StartRoundRequest(main_bet=10))
