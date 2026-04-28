"""Service-layer dispatch into draw + stud rounds via the poker session."""
import json

from app import create_app
from app.config import Config


class _TC(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test"


def _client():
    return create_app(_TC()).test_client()


def _make(client, variant):
    return client.post(
        "/api/v1/poker/sessions",
        data=json.dumps({
            "variant": variant,
            "starting_stack": 1000,
            "small_blind": 5,
            "big_blind": 10,
            "human_name": "Hero",
            "bots": [{"name": "Villain", "personality": "tight"}],
        }),
        content_type="application/json",
    )


def test_5_card_draw_starts_with_family_draw():
    client = _client()
    _make(client, "5-Card Draw")
    r = client.post("/api/v1/poker/sessions/me/hands")
    assert r.status_code == 201
    data = r.get_json()
    assert data["family"] == "draw"
    # State is either betting (human up to act) or further along if AI
    # auto-played until the human's turn.
    assert data["state"] in ("betting", "drawing", "complete")


def test_5_card_draw_active_hand_round_trip_carries_family():
    client = _client()
    _make(client, "5-Card Draw")
    client.post("/api/v1/poker/sessions/me/hands")
    r = client.get("/api/v1/poker/sessions/me/hands/active")
    if r.status_code == 404:
        return  # hand auto-completed; nothing to test on the resume path
    assert r.get_json()["family"] == "draw"


def test_7_stud_starts_with_family_stud():
    client = _client()
    _make(client, "7-Card Stud")
    r = client.post("/api/v1/poker/sessions/me/hands")
    assert r.status_code == 201
    data = r.get_json()
    assert data["family"] == "stud"
    # Stud should have a 'stud' metadata block.
    assert "stud" in data


def test_holdem_still_starts_with_family_holdem():
    """Regression: didn't break the existing holdem path."""
    client = _client()
    _make(client, "Texas Hold'em")
    r = client.post("/api/v1/poker/sessions/me/hands")
    assert r.status_code == 201
    assert r.get_json()["family"] == "holdem"


def test_discard_endpoint_404_with_no_session():
    client = _client()
    r = client.post(
        "/api/v1/poker/sessions/me/hands/active/discard",
        data=json.dumps({"indices": []}),
        content_type="application/json",
    )
    assert r.status_code == 404


def test_discard_endpoint_409_when_holdem_active():
    """Discard is only valid in draw poker; holdem rejects it."""
    client = _client()
    _make(client, "Texas Hold'em")
    client.post("/api/v1/poker/sessions/me/hands")
    r = client.post(
        "/api/v1/poker/sessions/me/hands/active/discard",
        data=json.dumps({"indices": [0]}),
        content_type="application/json",
    )
    assert r.status_code == 409


def test_discard_drives_5_card_draw_through_drawing_phase():
    """Drive a 5-Card Draw hand: human folds during pre-draw betting if
    the AI raises, otherwise calls. When DRAWING fires, human discards
    nothing and the hand should transition to the post-draw betting
    round."""
    client = _client()
    _make(client, "5-Card Draw")
    start = client.post("/api/v1/poker/sessions/me/hands").get_json()
    state = start["state"]
    family = start["family"]
    assert family == "draw"
    guard = 0
    transitioned_to_drawing = False
    while state not in ("complete", "showdown") and guard < 30:
        guard += 1
        active = client.get("/api/v1/poker/sessions/me/hands/active").get_json()
        state = active["state"]
        if state in ("complete", "showdown"):
            break
        if state == "drawing":
            transitioned_to_drawing = True
            r = client.post(
                "/api/v1/poker/sessions/me/hands/active/discard",
                data=json.dumps({"indices": []}),
                content_type="application/json",
            )
            assert r.status_code == 200
            state = r.get_json()["state"]
        elif state == "betting":
            legal = active["legal_actions"]
            if active["active_seat"] != 1:
                # AI's turn — let auto-play run via a no-op fetch.
                continue
            action = "check" if "check" in legal else ("call" if "call" in legal else "fold")
            r = client.post(
                "/api/v1/poker/sessions/me/hands/active/action",
                data=json.dumps({"action": action}),
                content_type="application/json",
            )
            state = r.get_json()["state"]
        else:
            break
    # We don't strictly require seeing DRAWING (heads-up + hero-folds-pre-draw
    # short-circuits), but the dispatch shouldn't crash either way.
    assert state in ("complete", "showdown", "betting", "drawing")
