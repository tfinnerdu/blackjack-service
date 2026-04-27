"""HTTP-level tests for the round/play endpoints."""
import json

from app import create_app
from app.config import Config


class _TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test"


def _client():
    app = create_app(_TestConfig())
    return app.test_client()


def _make_session(client, **overrides):
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


def test_start_round_no_session_returns_404():
    client = _client()
    r = client.post(
        "/api/v1/sessions/me/rounds",
        data=json.dumps({"main_bet": 10}),
        content_type="application/json",
    )
    assert r.status_code == 404


def test_start_round_bad_main_bet():
    client = _client()
    _make_session(client)
    r = client.post(
        "/api/v1/sessions/me/rounds",
        data=json.dumps({"main_bet": 0}),
        content_type="application/json",
    )
    assert r.status_code == 400


def test_start_round_returns_201_and_state():
    client = _client()
    _make_session(client)
    r = client.post(
        "/api/v1/sessions/me/rounds",
        data=json.dumps({"main_bet": 10}),
        content_type="application/json",
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["state"] in ("playing", "complete", "insurance")


def test_get_active_round_404_when_none():
    client = _client()
    _make_session(client)
    r = client.get("/api/v1/sessions/me/rounds/active")
    assert r.status_code == 404


def test_action_endpoint_drives_round_to_completion():
    client = _client()
    _make_session(client)
    start = client.post(
        "/api/v1/sessions/me/rounds",
        data=json.dumps({"main_bet": 10}),
        content_type="application/json",
    ).get_json()

    state = start["state"]
    guard = 0
    while state == "playing":
        # Pick whatever's legal — stand if available, otherwise the first option.
        legal = client.get("/api/v1/sessions/me/rounds/active").get_json()["legal_actions"]
        action = "stand" if "stand" in legal else legal[0]
        r = client.post(
            "/api/v1/sessions/me/rounds/active/action",
            data=json.dumps({"action": action}),
            content_type="application/json",
        )
        assert r.status_code == 200
        state = r.get_json()["state"]
        guard += 1
        assert guard < 12

    assert state == "complete"


def test_action_endpoint_rejects_invalid_action():
    client = _client()
    _make_session(client)
    client.post(
        "/api/v1/sessions/me/rounds",
        data=json.dumps({"main_bet": 10}),
        content_type="application/json",
    )
    r = client.post(
        "/api/v1/sessions/me/rounds/active/action",
        data=json.dumps({"action": "fold"}),
        content_type="application/json",
    )
    assert r.status_code == 400


def test_double_start_rejected_with_409():
    client = _client()
    _make_session(client)
    first = client.post(
        "/api/v1/sessions/me/rounds",
        data=json.dumps({"main_bet": 10}),
        content_type="application/json",
    ).get_json()
    if first["state"] == "complete":
        return  # round auto-finished, can't test double-start
    r = client.post(
        "/api/v1/sessions/me/rounds",
        data=json.dumps({"main_bet": 10}),
        content_type="application/json",
    )
    assert r.status_code == 409
