"""End-to-end tests for the poker simulator API."""
import json

from app import create_app
from app.config import Config


class _TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test"


def _client():
    return create_app(_TestConfig()).test_client()


def _create(client, **overrides):
    body = {
        "variant": "Texas Hold'em",
        "starting_stack": 1000,
        "small_blind": 5,
        "big_blind": 10,
        "bots": [
            {"name": "Tight Tom", "personality": "tight"},
            {"name": "Maniac Mike", "personality": "aggressive"},
        ],
        "human_name": "Hero",
    }
    body.update(overrides)
    return client.post(
        "/api/v1/poker/sessions",
        data=json.dumps(body),
        content_type="application/json",
    )


def test_personalities_endpoint_lists_nine():
    r = _client().get("/api/v1/poker/personalities")
    data = r.get_json()
    assert "book" in data["personalities"]
    assert len(data["personalities"]) == 9


def test_create_session_attaches_cookie_and_seats():
    client = _client()
    r = _create(client)
    assert r.status_code == 201
    data = r.get_json()
    assert data["token"]
    seat_count = len(data["seats"])
    assert seat_count == 3   # 1 human + 2 bots
    assert any(s["is_human"] for s in data["seats"])
    cookie = r.headers.get("Set-Cookie", "")
    assert "bj_poker_session=" in cookie


def test_get_session_via_cookie():
    client = _client()
    _create(client)
    r = client.get("/api/v1/poker/sessions/me")
    assert r.status_code == 200


def test_create_session_rejects_unknown_personality():
    client = _client()
    r = _create(client, bots=[{"name": "Bad Bot", "personality": "psychic"}])
    assert r.status_code == 400


def test_create_session_rejects_unknown_variant():
    client = _client()
    r = _create(client, variant="Some Game That Doesn't Exist")
    assert r.status_code == 400


def test_start_hand_deals_and_returns_state():
    client = _client()
    _create(client)
    r = client.post("/api/v1/poker/sessions/me/hands")
    assert r.status_code == 201
    data = r.get_json()
    # Either the human is up to act or the hand has already settled.
    assert data["state"] in ("pre_flop", "flop", "turn", "river", "showdown", "complete")
    assert len(data["human_hole"]) == 2  # Hold'em hole cards
    if data["state"] != "complete":
        assert data["pot_total"] >= 15  # at least SB + BB


def test_active_hand_returns_state_after_start():
    client = _client()
    _create(client)
    start = client.post("/api/v1/poker/sessions/me/hands").get_json()
    if start["state"] == "complete":
        return
    r = client.get("/api/v1/poker/sessions/me/hands/active")
    assert r.status_code == 200


def test_take_action_drives_hand_to_completion():
    """Drive a hand to completion via human FOLDs (heads-up if two seats
    are bots, fold-through ends fast)."""
    client = _client()
    _create(client)
    start = client.post("/api/v1/poker/sessions/me/hands").get_json()
    state = start["state"]
    guard = 0
    while state not in ("complete",):
        # If it's not the human's turn, the AI auto-played in the start_hand
        # call already; we should be at COMPLETE or waiting on the human.
        active = client.get("/api/v1/poker/sessions/me/hands/active").get_json()
        if active["state"] == "complete":
            state = "complete"
            break
        if active["active_seat"] is None:
            break
        legal = active["legal_actions"]
        # Pick fold if available, else check, else first.
        if "fold" in legal:
            action = "fold"
        elif "check" in legal:
            action = "check"
        elif "call" in legal:
            action = "call"
        else:
            action = legal[0]
        r = client.post(
            "/api/v1/poker/sessions/me/hands/active/action",
            data=json.dumps({"action": action}),
            content_type="application/json",
        )
        assert r.status_code == 200
        state = r.get_json()["state"]
        guard += 1
        assert guard < 30
    # After completion the hand row should be cleared.
    r = client.get("/api/v1/poker/sessions/me/hands/active")
    assert r.status_code == 404


def test_double_start_returns_409():
    client = _client()
    _create(client)
    first = client.post("/api/v1/poker/sessions/me/hands").get_json()
    if first["state"] == "complete":
        return
    r = client.post("/api/v1/poker/sessions/me/hands")
    assert r.status_code == 409


def test_action_without_session_returns_404():
    client = _client()
    r = client.post(
        "/api/v1/poker/sessions/me/hands/active/action",
        data=json.dumps({"action": "fold"}),
        content_type="application/json",
    )
    assert r.status_code == 404


def test_invalid_action_returns_400():
    client = _client()
    _create(client)
    client.post("/api/v1/poker/sessions/me/hands")
    r = client.post(
        "/api/v1/poker/sessions/me/hands/active/action",
        data=json.dumps({"action": "moonwalk"}),
        content_type="application/json",
    )
    assert r.status_code == 400


def test_delete_session_clears_cookie():
    client = _client()
    _create(client)
    r = client.delete("/api/v1/poker/sessions/me")
    assert r.status_code == 200
    r2 = client.get("/api/v1/poker/sessions/me")
    assert r2.status_code == 404
