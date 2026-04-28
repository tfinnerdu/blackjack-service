"""Multi-player tests for the three casino games.

A casino room (Roulette / Baccarat / Craps) lets a host plus any
number of guests bet against the same wheel / shoe / dice. Each
participant has their own bankroll inside the session — the host's
on the row, every guest's inside guest_tokens_json.

What we want to prove:
  - Joining via a room code mints a guest token + a seeded bankroll
  - Each participant's stage_bets endpoint validates against THEIR
    bankroll, not the host's
  - When the host triggers spin / play / roll, all participants'
    pending bets resolve against the same outcome and bankrolls
    update independently
  - Only the host can trigger the resolution endpoint
"""
from __future__ import annotations

import json

import pytest

from app import create_app
from app.config import Config


class _TC(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test"


def _client():
    return create_app(_TC()).test_client()


# ---- Roulette --------------------------------------------------------

def test_roulette_join_seeds_guest_bankroll():
    host = _client()
    r = host.post("/api/v1/roulette/sessions",
                  data=json.dumps({"starting_bankroll": 200}),
                  content_type="application/json")
    code = r.get_json()["room_code"]

    guest = host.application.test_client()
    r = guest.post(f"/api/v1/roulette/sessions/by-code/{code}/join",
                   data=json.dumps({"label": "Alice"}),
                   content_type="application/json")
    assert r.status_code == 201
    me = guest.get("/api/v1/roulette/sessions/me").get_json()
    assert me["caller_is_host"] is False
    assert me["caller_bankroll"] == 200    # default = host's starting
    # Two participants visible: host + Alice.
    labels = sorted(p["label"] for p in me["participants"])
    assert labels == sorted(["host", "Alice"])


def test_roulette_guest_bet_rejected_when_over_bankroll():
    host = _client()
    r = host.post("/api/v1/roulette/sessions",
                  data=json.dumps({"starting_bankroll": 100}),
                  content_type="application/json")
    code = r.get_json()["room_code"]

    guest = host.application.test_client()
    guest.post(f"/api/v1/roulette/sessions/by-code/{code}/join",
               data=json.dumps({"starting_bankroll": 50}),
               content_type="application/json")

    # 75 > 50: rejected.
    r = guest.post("/api/v1/roulette/sessions/me/bets",
                   data=json.dumps({"bets": [{"bet_type": "red", "stake": 75}]}),
                   content_type="application/json")
    assert r.status_code == 409
    assert "insufficient" in r.get_json()["error"].lower()


def test_roulette_spin_settles_host_and_guest_independently():
    host = _client()
    r = host.post("/api/v1/roulette/sessions",
                  data=json.dumps({"starting_bankroll": 200, "seed": 42}),
                  content_type="application/json")
    code = r.get_json()["room_code"]

    guest = host.application.test_client()
    guest.post(f"/api/v1/roulette/sessions/by-code/{code}/join",
               data=json.dumps({"starting_bankroll": 200}),
               content_type="application/json")

    # Host bets red, guest bets black — opposite sides, same spin.
    host.post("/api/v1/roulette/sessions/me/bets",
              data=json.dumps({"bets": [{"bet_type": "red", "stake": 10}]}),
              content_type="application/json")
    guest.post("/api/v1/roulette/sessions/me/bets",
               data=json.dumps({"bets": [{"bet_type": "black", "stake": 10}]}),
               content_type="application/json")

    r = host.post("/api/v1/roulette/sessions/me/spin")
    assert r.status_code == 200
    body = r.get_json()
    assert "spin" in body
    parts = body["participants"]
    assert len(parts) == 2
    profits = [p["total_profit"] for p in parts]
    # One won, one lost — opposite outcomes guaranteed unless 0/00 lands
    # in which case both lose. Either way they shouldn't both win.
    assert not (profits[0] > 0 and profits[1] > 0)


def test_roulette_only_host_can_spin():
    host = _client()
    r = host.post("/api/v1/roulette/sessions",
                  data=json.dumps({"starting_bankroll": 100}),
                  content_type="application/json")
    code = r.get_json()["room_code"]

    guest = host.application.test_client()
    guest.post(f"/api/v1/roulette/sessions/by-code/{code}/join", data=json.dumps({}), content_type="application/json")
    guest.post("/api/v1/roulette/sessions/me/bets",
               data=json.dumps({"bets": [{"bet_type": "red", "stake": 5}]}),
               content_type="application/json")

    r = guest.post("/api/v1/roulette/sessions/me/spin")
    assert r.status_code == 403


def test_roulette_spin_clears_pending_bets():
    host = _client()
    r = host.post("/api/v1/roulette/sessions",
                  data=json.dumps({"starting_bankroll": 200, "seed": 1}),
                  content_type="application/json")
    host.post("/api/v1/roulette/sessions/me/bets",
             data=json.dumps({"bets": [{"bet_type": "red", "stake": 10}]}),
             content_type="application/json")
    host.post("/api/v1/roulette/sessions/me/spin")
    me = host.get("/api/v1/roulette/sessions/me").get_json()
    assert me["caller_pending_bets"] == []


# ---- Baccarat --------------------------------------------------------

def test_baccarat_play_settles_all_participants():
    host = _client()
    r = host.post("/api/v1/baccarat/sessions",
                  data=json.dumps({"starting_bankroll": 200, "seed": 7}),
                  content_type="application/json")
    code = r.get_json()["room_code"]

    guest = host.application.test_client()
    guest.post(f"/api/v1/baccarat/sessions/by-code/{code}/join", data=json.dumps({}), content_type="application/json")

    host.post("/api/v1/baccarat/sessions/me/bets",
             data=json.dumps({"bets": [{"bet_type": "player", "stake": 10}]}),
             content_type="application/json")
    guest.post("/api/v1/baccarat/sessions/me/bets",
               data=json.dumps({"bets": [{"bet_type": "banker", "stake": 10}]}),
               content_type="application/json")

    r = host.post("/api/v1/baccarat/sessions/me/play")
    assert r.status_code == 200
    body = r.get_json()
    assert "round" in body
    assert len(body["participants"]) == 2

    # After the round, each participant's bankroll should be ≠ 200
    # OR equal (tie pushes Player+Banker). Either way, both have a
    # bankroll_after field and pending bets are cleared.
    for p in body["participants"]:
        assert "bankroll_after" in p


def test_baccarat_guest_only_cannot_play():
    host = _client()
    r = host.post("/api/v1/baccarat/sessions", data=json.dumps({}), content_type="application/json")
    code = r.get_json()["room_code"]
    guest = host.application.test_client()
    guest.post(f"/api/v1/baccarat/sessions/by-code/{code}/join", data=json.dumps({}), content_type="application/json")
    guest.post("/api/v1/baccarat/sessions/me/bets",
               data=json.dumps({"bets": [{"bet_type": "player", "stake": 5}]}),
               content_type="application/json")
    r = guest.post("/api/v1/baccarat/sessions/me/play")
    assert r.status_code == 403


# ---- Craps -----------------------------------------------------------

def test_craps_book_persists_per_participant():
    """Two participants each with their own book. After a non-resolving
    roll their books survive. After a 7 with a point on, both lose
    their pass-line bets independently."""
    host = _client()
    r = host.post("/api/v1/craps/sessions",
                  data=json.dumps({"starting_bankroll": 200, "seed": 5}),
                  content_type="application/json")
    code = r.get_json()["room_code"]

    guest = host.application.test_client()
    guest.post(f"/api/v1/craps/sessions/by-code/{code}/join", data=json.dumps({}), content_type="application/json")

    host.post("/api/v1/craps/sessions/me/bets",
             data=json.dumps({"bets": [{"bet_type": "pass_line", "stake": 10}]}),
             content_type="application/json")
    guest.post("/api/v1/craps/sessions/me/bets",
               data=json.dumps({"bets": [{"bet_type": "pass_line", "stake": 10}]}),
               content_type="application/json")

    # Force a 6 so the point is set (no resolution yet).
    r = host.post("/api/v1/craps/sessions/me/roll",
                  data=json.dumps({"dice": [3, 3]}),
                  content_type="application/json")
    assert r.status_code == 200
    assert r.get_json()["phase_after"] == "point_on"

    # Each book should still have one bet.
    me = host.get("/api/v1/craps/sessions/me").get_json()
    you = guest.get("/api/v1/craps/sessions/me").get_json()
    assert len(me["caller_book"]) == 1
    assert len(you["caller_book"]) == 1

    # Force a 7 — both bets lose and books empty.
    r = host.post("/api/v1/craps/sessions/me/roll",
                  data=json.dumps({"dice": [3, 4]}),
                  content_type="application/json")
    assert r.get_json()["phase_after"] == "come_out"

    me = host.get("/api/v1/craps/sessions/me").get_json()
    you = guest.get("/api/v1/craps/sessions/me").get_json()
    assert me["caller_book"] == []
    assert you["caller_book"] == []
    # Both participants lost their $10.
    assert me["caller_bankroll"] == 190
    assert you["caller_bankroll"] == 190


def test_craps_only_host_can_roll():
    host = _client()
    r = host.post("/api/v1/craps/sessions", data=json.dumps({}), content_type="application/json")
    code = r.get_json()["room_code"]
    guest = host.application.test_client()
    guest.post(f"/api/v1/craps/sessions/by-code/{code}/join", data=json.dumps({}), content_type="application/json")
    r = guest.post("/api/v1/craps/sessions/me/roll")
    assert r.status_code == 403


def test_craps_guest_can_cancel_their_own_bet():
    host = _client()
    r = host.post("/api/v1/craps/sessions", data=json.dumps({}), content_type="application/json")
    code = r.get_json()["room_code"]
    guest = host.application.test_client()
    guest.post(f"/api/v1/craps/sessions/by-code/{code}/join", data=json.dumps({}), content_type="application/json")
    r = guest.post("/api/v1/craps/sessions/me/bets",
                   data=json.dumps({"bets": [{"bet_type": "field", "stake": 5}]}),
                   content_type="application/json")
    book = r.get_json()["caller_book"]
    bet_id = book[0]["bet_id"]
    r = guest.delete(f"/api/v1/craps/sessions/me/bets/{bet_id}")
    assert r.status_code == 200
    assert r.get_json()["caller_book"] == []
