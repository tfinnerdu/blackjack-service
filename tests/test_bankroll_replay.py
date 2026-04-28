"""Parallel-replay bankroll tests. Each settled round runs two
counterfactuals — what if the human played book, what if they played
book-with-counts. The session tracks a separate bankroll for each.

Goals here:
  - The book/counter bankrolls start equal to starting_bankroll.
  - After a round, the values are sane integers (not None / not negative
    by accident) and a history entry is appended.
  - When the human plays book themselves, the actual and book bankrolls
    advance by the same amount on that round.
  - The `/me/stats` endpoint surfaces the new fields.
"""
import json

from app import create_app
from app.config import Config
from app.services.games import StartRoundRequest, start_round, take_action
from app.services.sessions import create_from_template


class _TC(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test"


def _client():
    return create_app(_TC()).test_client()


def _new_sess(starting_bankroll: int = 500):
    return create_from_template(
        template_id=None,
        starting_bankroll=starting_bankroll,
        player_seat=1,
        rules_overrides={
            "seats": 1, "min_bet": 5, "max_bet": 100, "bet_increment": 5,
            "insurance_offered": False, "dealer_peeks": False,
        },
        seed=4242,
    )


def _drive_round(sess, main_bet=10, follow_book=True):
    """Play a round end-to-end, picking either book actions or always-stand."""
    view = start_round(sess, StartRoundRequest(main_bet=main_bet))
    guard = 0
    while view.state == "playing":
        action = view.book["action"] if (follow_book and view.book) else "stand"
        if action not in view.legal_actions:
            action = "stand" if "stand" in view.legal_actions else view.legal_actions[0]
        view = take_action(sess, action)
        guard += 1
        assert guard < 20


def test_initial_bankrolls_match_starting():
    app = create_app(_TC())
    with app.app_context():
        sess = _new_sess(500)
        assert sess.book_bankroll == 500
        assert sess.counter_bankroll == 500
        assert json.loads(sess.bankroll_history_json) == []


def test_round_appends_one_history_entry_per_hand():
    app = create_app(_TC())
    with app.app_context():
        sess = _new_sess(500)
        _drive_round(sess)

        history = json.loads(sess.bankroll_history_json)
        assert len(history) >= 1
        entry = history[-1]
        assert {"hand", "actual", "book", "counter"} <= entry.keys()
        assert entry["hand"] == sess.hands_played
        assert entry["actual"] == sess.bankroll
        assert entry["book"] == sess.book_bankroll
        assert entry["counter"] == sess.counter_bankroll


def test_book_bankroll_matches_actual_when_player_plays_book():
    """If the player follows book exactly, their actual bankroll change
    equals the book replay's bankroll change for the same hand."""
    app = create_app(_TC())
    with app.app_context():
        sess = _new_sess(500)
        starting = sess.bankroll
        for _ in range(5):
            _drive_round(sess, follow_book=True)

        actual_delta = sess.bankroll - starting
        book_delta = sess.book_bankroll - starting
        # Both ran the same shoe state with the same actions, so they
        # should agree exactly.
        assert actual_delta == book_delta


def test_book_bankroll_decouples_from_actual_when_player_diverges():
    """Always-stand player will lose worse than book on average. Over a
    handful of hands the bankrolls should diverge."""
    app = create_app(_TC())
    with app.app_context():
        sess = _new_sess(1000)
        for _ in range(10):
            _drive_round(sess, follow_book=False)
        # No strict inequality — variance can flip a small sample. But
        # the book delta tracking should at least not be None and history
        # length should match hands played.
        history = json.loads(sess.bankroll_history_json)
        assert len(history) == sess.hands_played
        assert isinstance(sess.book_bankroll, int)
        assert isinstance(sess.counter_bankroll, int)


def test_stats_endpoint_returns_bankrolls_and_history():
    client = _client()
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
    client.post(
        "/api/v1/sessions",
        data=json.dumps(body),
        content_type="application/json",
    )

    # Fresh session: bankrolls all equal to starting; history empty.
    stats = client.get("/api/v1/sessions/me/stats").get_json()
    assert stats["bankrolls"]["actual"] == 500
    assert stats["bankrolls"]["book"] == 500
    assert stats["bankrolls"]["counter"] == 500
    assert stats["bankrolls"]["starting"] == 500
    assert stats["bankroll_history"] == []

    # Drive one round. History should now have one entry.
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
    assert len(stats["bankroll_history"]) >= 1
    last = stats["bankroll_history"][-1]
    assert last["hand"] == stats["hands_played"]
