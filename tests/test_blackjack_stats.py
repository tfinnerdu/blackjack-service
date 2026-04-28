"""Blackjack /api/v1/sessions/me/stats endpoint + EV-lost tracking."""
import json

from app import create_app
from app.config import Config
from app.models import GameSession
from app.services.games import StartRoundRequest, start_round, take_action
from app.services.sessions import create_from_template


class _TC(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test"


def _client():
    return create_app(_TC()).test_client()


def _build_session(client, **overrides):
    body = {
        "template_id": None,
        "starting_bankroll": 500,
        "player_seat": 1,
        "rules": {
            "seats": 1, "min_bet": 5, "max_bet": 100, "bet_increment": 5,
            "insurance_offered": False, "dealer_peeks": False,
        },
        "seed": 4242,
    }
    body.update(overrides)
    return client.post(
        "/api/v1/sessions",
        data=json.dumps(body),
        content_type="application/json",
    )


def test_stats_endpoint_returns_404_without_session():
    r = _client().get("/api/v1/sessions/me/stats")
    assert r.status_code == 404


def test_stats_endpoint_initial_session_zeroes():
    client = _client()
    _build_session(client)
    r = client.get("/api/v1/sessions/me/stats")
    assert r.status_code == 200
    data = r.get_json()
    assert data["hands_played"] == 0
    assert data["wins"] == 0
    assert data["ev_lost_dollars"] == 0.0
    assert data["rates"]["win_pct"] == 0.0
    assert "Heuristic estimate" in data["ev_lost_estimate_note"]


def test_stats_endpoint_includes_counter_state():
    client = _client()
    _build_session(client)
    r = client.get("/api/v1/sessions/me/stats")
    data = r.get_json()
    assert "counter" in data
    assert data["counter"]["running_count"] == 0
    assert data["counter"]["cards_seen"] == 0


def test_ev_lost_increments_when_player_diverges_from_book():
    """Drive a hand where the player makes a non-book action; ev_lost
    should move."""
    app = create_app(_TC())
    with app.app_context():
        sess = create_from_template(
            template_id=None,
            starting_bankroll=500,
            player_seat=1,
            rules_overrides={
                "seats": 1, "min_bet": 5, "max_bet": 100, "bet_increment": 5,
                "insurance_offered": False, "dealer_peeks": False,
            },
            seed=4242,
        )
        before = sess.ev_lost_cents
        view = start_round(sess, StartRoundRequest(main_bet=10))
        if view.state != "playing":
            return  # natural BJ, skip
        recommended = view.book["action"] if view.book else None
        candidates = [a for a in view.legal_actions if a != recommended]
        if not candidates:
            return  # only one legal action, can't diverge
        take_action(sess, candidates[0])
        # ev_lost_cents should now be > 0 since we deviated.
        assert sess.ev_lost_cents > before


def test_ev_lost_does_not_increment_when_book_action_taken():
    """Same starting hand: take exactly the book action. ev_lost stays zero."""
    app = create_app(_TC())
    with app.app_context():
        sess = create_from_template(
            template_id=None,
            starting_bankroll=500,
            player_seat=1,
            rules_overrides={
                "seats": 1, "min_bet": 5, "max_bet": 100, "bet_increment": 5,
                "insurance_offered": False, "dealer_peeks": False,
            },
            seed=4242,
        )
        view = start_round(sess, StartRoundRequest(main_bet=10))
        if view.state != "playing":
            return
        take_action(sess, view.book["action"])
        # The action might have ended the hand (e.g. surrender) — ev_lost
        # should remain zero either way since we matched book.
        assert sess.ev_lost_cents == 0


def test_rates_all_present_when_hands_played():
    """Drive a few hands, confirm rate fields exist."""
    client = _client()
    _build_session(client)
    # Start + drive one hand to completion.
    r = client.post(
        "/api/v1/sessions/me/rounds",
        data=json.dumps({"main_bet": 10}),
        content_type="application/json",
    )
    state = r.get_json()["state"]
    guard = 0
    while state == "playing":
        active = client.get("/api/v1/sessions/me/rounds/active").get_json()
        legal = active["legal_actions"]
        action = "stand" if "stand" in legal else legal[0]
        r = client.post(
            "/api/v1/sessions/me/rounds/active/action",
            data=json.dumps({"action": action}),
            content_type="application/json",
        )
        state = r.get_json()["state"]
        guard += 1
        assert guard < 12

    stats = client.get("/api/v1/sessions/me/stats").get_json()
    assert stats["hands_played"] >= 1
    rates = stats["rates"]
    for key in ("win_pct", "loss_pct", "push_pct", "mistake_pct",
                "blackjack_pct", "bust_pct"):
        assert key in rates
        assert isinstance(rates[key], (int, float))
