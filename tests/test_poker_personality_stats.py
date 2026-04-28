"""Per-personality W/L tracking + session stats endpoint."""
import json

from app import create_app
from app.config import Config


class _TC(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test"


def _make(client):
    return client.post(
        "/api/v1/poker/sessions",
        data=json.dumps({
            "variant": "Texas Hold'em",
            "starting_stack": 1000,
            "small_blind": 5,
            "big_blind": 10,
            "human_name": "Hero",
            "bots": [
                {"name": "T1", "personality": "tight"},
                {"name": "T2", "personality": "tight"},
                {"name": "Maniac", "personality": "aggressive"},
            ],
        }),
        content_type="application/json",
    )


def _drive_one_hand(client):
    """Start a hand and fold the human through completion."""
    start = client.post("/api/v1/poker/sessions/me/hands").get_json()
    state = start["state"]
    guard = 0
    while state != "complete":
        active = client.get("/api/v1/poker/sessions/me/hands/active").get_json()
        if active["state"] == "complete":
            break
        if active["active_seat"] is None:
            break
        legal = active["legal_actions"]
        action = "fold" if "fold" in legal else ("check" if "check" in legal else legal[0])
        r = client.post(
            "/api/v1/poker/sessions/me/hands/active/action",
            data=json.dumps({"action": action}),
            content_type="application/json",
        )
        state = r.get_json()["state"]
        guard += 1
        assert guard < 30


def test_personality_stats_endpoint_404_without_session():
    client = create_app(_TC()).test_client()
    r = client.get("/api/v1/poker/sessions/me/stats")
    assert r.status_code == 404


def test_seat_counters_increment_after_a_hand():
    client = create_app(_TC()).test_client()
    _make(client)
    _drive_one_hand(client)
    stats = client.get("/api/v1/poker/sessions/me/stats").get_json()
    # Three bots seated; their per-seat counters should sum to >= 1 hand.
    seat_counters = sum(s["hands_played"] for s in stats["seats"])
    assert seat_counters >= 1
    # At least one personality bucket should have hands_played > 0.
    assert any(p["hands_played"] > 0 for p in stats["personalities"])


def test_personality_aggregates_merge_same_personality():
    client = create_app(_TC()).test_client()
    _make(client)
    _drive_one_hand(client)
    stats = client.get("/api/v1/poker/sessions/me/stats").get_json()
    # Two tight bots configured -> their personality bucket has seat_count == 2.
    tight = next((p for p in stats["personalities"] if p["personality"] == "tight"), None)
    assert tight is not None
    assert tight["seat_count"] == 2


def test_human_block_tracks_separately():
    client = create_app(_TC()).test_client()
    _make(client)
    _drive_one_hand(client)
    stats = client.get("/api/v1/poker/sessions/me/stats").get_json()
    h = stats["human"]
    assert h is not None
    assert h["name"] == "Hero"
    # Human folded, so they didn't win this hand.
    assert h["hands_won"] == 0
    assert h["hands_played"] >= 1


def test_personality_aggregates_sorted_by_profit_desc():
    client = create_app(_TC()).test_client()
    _make(client)
    for _ in range(3):
        _drive_one_hand(client)
    stats = client.get("/api/v1/poker/sessions/me/stats").get_json()
    profits = [p["profit_total"] for p in stats["personalities"]]
    assert profits == sorted(profits, reverse=True)
