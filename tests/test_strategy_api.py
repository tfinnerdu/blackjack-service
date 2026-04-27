"""End-to-end test for /api/v1/strategy/ask."""
import json

from app import create_app
from app.config import Config


class _TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test"


def _client():
    app = create_app(_TestConfig())
    return app.test_client()


def _ask(client, **body):
    return client.post(
        "/api/v1/strategy/ask",
        data=json.dumps(body),
        content_type="application/json",
    )


def test_basic_query():
    client = _client()
    r = _ask(
        client,
        hand=["TS", "6H"],
        dealer_up="7C",
        rules={"dealer_hits_soft_17": True},
        can_double=True,
        can_split=False,
        can_surrender=False,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["action"] == "hit"
    assert data["source"] == "basic"


def test_count_deviation_via_api():
    client = _client()
    r = _ask(
        client,
        hand=["TS", "6H"],
        dealer_up="TC",
        rules={"dealer_hits_soft_17": True},
        can_double=False,
        can_split=False,
        can_surrender=False,
        true_count=0.0,
    )
    data = r.get_json()
    assert data["action"] == "stand"
    assert data["source"] == "index"


def test_invalid_hand_returns_400():
    client = _client()
    r = _ask(client, hand=["TS"], dealer_up="7C")
    assert r.status_code == 400


def test_rules_enum_strings_accepted():
    client = _client()
    r = _ask(
        client,
        hand=["AS", "7H"],
        dealer_up="2C",
        rules={"dealer_hits_soft_17": True, "double_rule": "any2"},
        can_double=True,
        can_split=False,
        can_surrender=False,
    )
    assert r.status_code == 200
    # H17 A,7 vs 2 = double.
    assert r.get_json()["action"] == "double"
