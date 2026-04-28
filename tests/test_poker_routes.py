"""Smoke tests for the poker API namespace."""
import json

from app import create_app
from app.config import Config


class _TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test"


def _client():
    return create_app(_TestConfig()).test_client()


def test_poker_health():
    r = _client().get("/api/v1/poker/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok", "service": "blackjack-service", "module": "poker"}


def test_deck_peek_53_card_deck():
    r = _client().post(
        "/api/v1/poker/deck/peek",
        data=json.dumps({"decks": 1, "jokers": 1, "seed": 42, "count": 5}),
        content_type="application/json",
    )
    assert r.status_code == 200
    data = r.get_json()
    assert len(data["cards"]) == 5
    assert data["deck_size"] == 53
    assert data["cards_remaining"] == 53 - 5


def test_deck_peek_validates_count():
    r = _client().post(
        "/api/v1/poker/deck/peek",
        data=json.dumps({"decks": 1, "jokers": 0, "count": 100}),
        content_type="application/json",
    )
    assert r.status_code == 400


def test_deck_peek_seed_is_deterministic():
    body = {"decks": 1, "jokers": 1, "seed": 99, "count": 10}
    a = _client().post("/api/v1/poker/deck/peek", data=json.dumps(body),
                       content_type="application/json").get_json()
    b = _client().post("/api/v1/poker/deck/peek", data=json.dumps(body),
                       content_type="application/json").get_json()
    assert a["cards"] == b["cards"]
