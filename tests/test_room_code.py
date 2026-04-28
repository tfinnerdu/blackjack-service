"""Room code + seat-claim multi-human path.

Each session ships with a 6-char `room_code`; guests can claim an AI seat
by hitting /sessions/by-code/{code}/seats/{seat_num}/claim. Their token
authorizes actions on that seat (and only that seat). The host's
existing token continues to authorize actions on player_seat.
"""
import json

from app import create_app
from app.config import Config


class _TC(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test"


def _client():
    return create_app(_TC()).test_client()


def _new_session(client, **overrides):
    body = {
        "template_id": None,
        "starting_bankroll": 500,
        "player_seat": 1,
        "rules": {
            "seats": 3, "min_bet": 5, "max_bet": 100, "bet_increment": 5,
            "insurance_offered": False, "dealer_peeks": False,
        },
        "ai_seats": [
            {
                "seat_num": 2, "playstyle": "book", "bet_pattern": "flat",
                "base_bet": 10, "bankroll": 200,
            },
            {
                "seat_num": 3, "playstyle": "book", "bet_pattern": "flat",
                "base_bet": 10, "bankroll": 200,
            },
        ],
        "seed": 4242,
    }
    body.update(overrides)
    return client.post(
        "/api/v1/sessions", data=json.dumps(body), content_type="application/json"
    )


def test_session_has_room_code_and_empty_seat_map():
    client = _client()
    r = _new_session(client)
    sess = r.get_json()
    assert sess["room_code"] and len(sess["room_code"]) == 6
    assert sess["seat_tokens"] == {}


def test_lobby_lists_seats_with_claimability():
    client = _client()
    r = _new_session(client)
    code = r.get_json()["room_code"]

    r2 = client.get(f"/api/v1/sessions/by-code/{code}")
    assert r2.status_code == 200
    lobby = r2.get_json()
    assert lobby["room_code"] == code
    seat_kinds = {s["seat_num"]: s["kind"] for s in lobby["seats"]}
    assert seat_kinds == {1: "host", 2: "ai", 3: "ai"}
    assert all(s["claimable"] for s in lobby["seats"] if s["seat_num"] != 1)


def test_lobby_404s_for_unknown_code():
    r = _client().get("/api/v1/sessions/by-code/NOSUCH")
    assert r.status_code == 404


def test_claim_returns_token_and_marks_seat_claimed():
    client = _client()
    code = _new_session(client).get_json()["room_code"]
    # Use a separate client (no host cookie) for the guest claim flow.
    guest = _client().__class__(client.application, response_wrapper=client.application.response_class)
    # Simpler: just use a fresh test client.

    guest = client.application.test_client()
    r = guest.post(f"/api/v1/sessions/by-code/{code}/seats/2/claim")
    assert r.status_code == 201
    body = r.get_json()
    assert body["seat_num"] == 2
    assert isinstance(body["token"], str) and len(body["token"]) > 16
    # Lobby reflects the claim.
    seat_kinds = {s["seat_num"]: s["kind"] for s in body["room"]["seats"]}
    assert seat_kinds[2] == "guest"
    assert seat_kinds[3] == "ai"


def test_cannot_claim_host_seat():
    client = _client()
    code = _new_session(client).get_json()["room_code"]
    guest = client.application.test_client()
    r = guest.post(f"/api/v1/sessions/by-code/{code}/seats/1/claim")
    assert r.status_code == 400
    assert "host" in r.get_json()["error"].lower()


def test_cannot_claim_invalid_seat():
    client = _client()
    code = _new_session(client).get_json()["room_code"]
    guest = client.application.test_client()
    r = guest.post(f"/api/v1/sessions/by-code/{code}/seats/9/claim")
    assert r.status_code == 400


def test_release_drops_the_claim():
    client = _client()
    code = _new_session(client).get_json()["room_code"]
    guest = client.application.test_client()
    guest.post(f"/api/v1/sessions/by-code/{code}/seats/2/claim")
    r = guest.post(f"/api/v1/sessions/by-code/{code}/seats/2/release")
    assert r.status_code == 200
    seat_kinds = {s["seat_num"]: s["kind"] for s in r.get_json()["seats"]}
    assert seat_kinds[2] == "ai"


def test_only_owner_or_host_can_release():
    """A third party with no claim should not be able to release another
    seat."""
    client = _client()
    code = _new_session(client).get_json()["room_code"]
    # Guest 1 claims seat 2.
    guest1 = client.application.test_client()
    guest1.post(f"/api/v1/sessions/by-code/{code}/seats/2/claim")
    # Random visitor (no token) tries to release it.
    bystander = client.application.test_client()
    r = bystander.post(f"/api/v1/sessions/by-code/{code}/seats/2/release")
    assert r.status_code == 403


def test_guest_token_can_act_on_their_seat_only():
    """End-to-end: host starts a round; the guest seat (seat 2) is the
    first to act because seat 1 is human (host). After the host acts,
    auto-play runs the rest. This test verifies that the guest's token
    cannot act when it's not their seat's turn."""
    host = _client()
    code = _new_session(host).get_json()["room_code"]

    guest = host.application.test_client()
    guest.post(f"/api/v1/sessions/by-code/{code}/seats/2/claim")

    # Host starts the round.
    r = host.post(
        "/api/v1/sessions/me/rounds",
        data=json.dumps({"main_bet": 10}),
        content_type="application/json",
    )
    assert r.status_code == 201
    state = r.get_json()
    if state["state"] != "playing":
        return  # natural BJ — round complete; skip the action checks

    # Determine whose turn it is. If it's seat 2 (guest), the guest can
    # act and the host cannot. If seat 1 (host), the inverse.
    active = state["active_seat_num"]
    other_acting = host if active == 1 else guest
    not_my_turn = guest if active == 1 else host

    # The non-active seat's token should be rejected when trying to act.
    r_bad = not_my_turn.post(
        "/api/v1/sessions/me/rounds/active/action",
        data=json.dumps({"action": "stand"}),
        content_type="application/json",
    )
    assert r_bad.status_code == 409
    assert "not your turn" in r_bad.get_json()["error"]

    # The active seat's token can act.
    r_ok = other_acting.post(
        "/api/v1/sessions/me/rounds/active/action",
        data=json.dumps({"action": "stand"}),
        content_type="application/json",
    )
    assert r_ok.status_code == 200


def test_guest_can_set_their_seat_bet():
    """A guest claims seat 2, then sets a custom bet for the next round.
    The host's session view (via get_seat_claim_bet) should reflect it."""
    from app.services.sessions import get_seat_claim_bet

    host = _client()
    code = _new_session(host).get_json()["room_code"]
    guest = host.application.test_client()
    guest.post(f"/api/v1/sessions/by-code/{code}/seats/2/claim")

    r = guest.post(
        "/api/v1/sessions/me/seat/bet",
        data=json.dumps({"bet": 25}),
        content_type="application/json",
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["seat_num"] == 2 and body["bet"] == 25

    # Caller's view exposes the chosen bet.
    me = guest.get("/api/v1/sessions/me").get_json()
    assert me["caller_seat"] == 2
    assert me["caller_seat_bet"] == 25

    # Lobby surfaces it for everyone.
    lobby = host.get(f"/api/v1/sessions/by-code/{code}").get_json()
    seat2 = next(s for s in lobby["seats"] if s["seat_num"] == 2)
    assert seat2["guest_bet"] == 25

    # Server-side helper agrees.
    with host.application.app_context():
        from app.models import GameSession
        sess = GameSession.query.filter_by(room_code=code).first()
        assert get_seat_claim_bet(sess, 2) == 25


def test_host_cannot_set_their_own_seat_bet_via_endpoint():
    """The host bets via /rounds (per-round); their seat-bet endpoint
    is only meaningful for guests."""
    host = _client()
    _new_session(host)
    r = host.post(
        "/api/v1/sessions/me/seat/bet",
        data=json.dumps({"bet": 25}),
        content_type="application/json",
    )
    assert r.status_code == 403


def test_guest_seat_bet_must_be_within_table_limits():
    host = _client()
    code = _new_session(host).get_json()["room_code"]
    guest = host.application.test_client()
    guest.post(f"/api/v1/sessions/by-code/{code}/seats/2/claim")

    # Below min_bet ($5).
    r = guest.post(
        "/api/v1/sessions/me/seat/bet",
        data=json.dumps({"bet": 2}),
        content_type="application/json",
    )
    assert r.status_code == 400


def test_guest_can_view_active_round():
    """Read-only round view should work for any seat owner via cookie."""
    host = _client()
    code = _new_session(host).get_json()["room_code"]
    guest = host.application.test_client()
    guest.post(f"/api/v1/sessions/by-code/{code}/seats/2/claim")

    host.post(
        "/api/v1/sessions/me/rounds",
        data=json.dumps({"main_bet": 10}),
        content_type="application/json",
    )
    r = guest.get("/api/v1/sessions/me/rounds/active")
    # Either 200 (round in flight) or 404 (host got a natural and round
    # finished); both are valid outcomes here.
    assert r.status_code in (200, 404)
