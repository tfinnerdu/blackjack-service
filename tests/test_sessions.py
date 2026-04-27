"""Session lifecycle tests."""
import json

from app import create_app
from app.config import Config


class _TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test"


def _client():
    app = create_app(_TestConfig())
    return app, app.test_client()


def _builtin_id(client) -> int:
    r = client.get("/api/v1/templates")
    return next(t["id"] for t in r.get_json()["templates"] if t["is_builtin"])


def test_create_session_from_builtin_template_attaches_cookie():
    _, client = _client()
    tid = _builtin_id(client)
    r = client.post(
        "/api/v1/sessions",
        data=json.dumps({"template_id": tid}),
        content_type="application/json",
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["token"]
    assert data["bankroll"] == data["starting_bankroll"]
    assert data["template_id"] == tid
    # Cookie set so the next request needs no token in the body.
    cookie = r.headers.get("Set-Cookie", "")
    assert "bj_session=" in cookie


def test_get_me_returns_session_via_cookie():
    _, client = _client()
    tid = _builtin_id(client)
    r = client.post(
        "/api/v1/sessions",
        data=json.dumps({"template_id": tid}),
        content_type="application/json",
    )
    token = r.get_json()["token"]
    r2 = client.get("/api/v1/sessions/me")
    assert r2.status_code == 200
    assert r2.get_json()["token"] == token


def test_get_me_via_url_param_when_no_cookie():
    app = create_app(_TestConfig())
    # Use one client to create, another to fetch via URL token.
    a = app.test_client()
    tid = _builtin_id(a)
    token = a.post(
        "/api/v1/sessions",
        data=json.dumps({"template_id": tid}),
        content_type="application/json",
    ).get_json()["token"]

    b = app.test_client()
    r = b.get(f"/api/v1/sessions/me?session={token}")
    assert r.status_code == 200
    assert r.get_json()["token"] == token


def test_get_me_no_token_returns_404():
    _, client = _client()
    r = client.get("/api/v1/sessions/me")
    assert r.status_code == 404


def test_reset_keeps_bankroll_resets_shoe_and_counter():
    _, client = _client()
    tid = _builtin_id(client)
    r = client.post(
        "/api/v1/sessions",
        data=json.dumps({"template_id": tid, "seed": 1234}),
        content_type="application/json",
    )
    sess = r.get_json()
    original_seed = sess["shoe"]["seed"]
    bankroll = sess["bankroll"]

    r = client.post(
        "/api/v1/sessions/me/reset",
        data=json.dumps({"seed": 5678}),
        content_type="application/json",
    )
    assert r.status_code == 200
    after = r.get_json()
    assert after["bankroll"] == bankroll
    assert after["shoe"]["seed"] == 5678
    assert after["shoe"]["seed"] != original_seed
    assert after["shoe"]["cards_dealt"] == 0
    assert after["counter"]["running_count"] == 0


def test_create_with_overrides_takes_effect():
    _, client = _client()
    body = {
        "template_id": None,
        "starting_bankroll": 1000,
        "player_seat": 1,
        "rules": {"decks": 2, "seats": 1, "min_bet": 10, "max_bet": 100, "bet_increment": 5},
    }
    r = client.post(
        "/api/v1/sessions",
        data=json.dumps(body),
        content_type="application/json",
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["starting_bankroll"] == 1000
    assert data["bankroll"] == 1000
    assert data["rules"]["decks"] == 2
    assert data["player_seat"] == 1


def test_default_ai_seats_fill_other_seats():
    _, client = _client()
    body = {
        "template_id": None,
        "rules": {"seats": 3, "player_seat": 2},
    }
    r = client.post(
        "/api/v1/sessions",
        data=json.dumps(body),
        content_type="application/json",
    )
    data = r.get_json()
    seat_nums = [s["seat_num"] for s in data["ai_seats"]]
    assert seat_nums == [1, 3]


def test_delete_me_clears_session():
    _, client = _client()
    tid = _builtin_id(client)
    client.post(
        "/api/v1/sessions",
        data=json.dumps({"template_id": tid}),
        content_type="application/json",
    )
    r = client.delete("/api/v1/sessions/me")
    assert r.status_code == 200
    # The cookie was cleared but the in-process client may keep it locally.
    # Use a fresh app to verify the row is gone.
    r2 = client.get("/api/v1/sessions/me")
    assert r2.status_code == 404


def test_invalid_template_id_returns_400():
    _, client = _client()
    r = client.post(
        "/api/v1/sessions",
        data=json.dumps({"template_id": 99999}),
        content_type="application/json",
    )
    assert r.status_code == 400


def test_invalid_player_seat_returns_400():
    _, client = _client()
    body = {
        "template_id": None,
        "rules": {"seats": 3},
        "player_seat": 5,
    }
    r = client.post(
        "/api/v1/sessions",
        data=json.dumps(body),
        content_type="application/json",
    )
    assert r.status_code == 400
