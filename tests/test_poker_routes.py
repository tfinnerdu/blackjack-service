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


def test_list_variants_returns_library():
    r = _client().get("/api/v1/poker/variants")
    assert r.status_code == 200
    data = r.get_json()
    names = [v["name"] for v in data["variants"]]
    assert "Texas Hold'em" in names
    assert "Omaha Hi/Lo (8 or better)" in names


def test_analyze_holdem_by_name():
    r = _client().post(
        "/api/v1/poker/analyze",
        data=json.dumps({
            "variant": "Texas Hold'em",
            "cards": ["AS", "KS", "QS", "JS", "TS", "2H", "3D"],
        }),
        content_type="application/json",
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["hi"]["cls_name"] == "Straight flush"


def test_analyze_omaha_with_hole_and_board():
    r = _client().post(
        "/api/v1/poker/analyze",
        data=json.dumps({
            "variant": "Omaha Hi/Lo (8 or better)",
            "hole": ["AH", "2D", "TC", "JC"],
            "board": ["3S", "4H", "8D", "KD", "QC"],
        }),
        content_type="application/json",
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["lo"] is not None
    assert data["lo"]["qualifies"] is True


def test_analyze_unknown_variant_returns_404():
    r = _client().post(
        "/api/v1/poker/analyze",
        data=json.dumps({
            "variant": "Some Nonexistent Game",
            "cards": ["AS", "KS"],
        }),
        content_type="application/json",
    )
    assert r.status_code == 404


def test_save_user_variant_then_appears_in_list():
    client = _client()
    body = {
        "name": "My Home Game",
        "description": "Custom variant",
        "family": "home",
        "deck": {"decks": 1, "jokers": 1},
        "deal": {
            "hole_cards": 5, "up_cards": 0,
            "community_streets": [], "stud_streets": [],
            "stud_face_down_final": False, "draws": [],
        },
        "wilds": [{"kind": "joker", "mode": "fully_wild"}],
        "hand": "exactly_5_hole",
        "hi_lo": "hi_only",
        "lo_rule": None,
        "lo_eight_or_better": False,
        "notes": "",
    }
    r = client.post(
        "/api/v1/poker/variants",
        data=json.dumps(body),
        content_type="application/json",
    )
    assert r.status_code == 201
    saved = r.get_json()
    assert saved["_saved_template_id"]

    # Now list — should appear after the built-ins.
    listed = client.get("/api/v1/poker/variants").get_json()["variants"]
    names = [v["name"] for v in listed]
    assert "My Home Game" in names
    assert "Texas Hold'em" in names


def test_save_variant_rejects_duplicate_name():
    client = _client()
    body = {
        "name": "Dup",
        "description": "x",
        "family": "home",
        "deck": {"decks": 1, "jokers": 0},
        "deal": {
            "hole_cards": 5, "up_cards": 0,
            "community_streets": [], "stud_streets": [],
            "stud_face_down_final": False, "draws": [],
        },
        "wilds": [],
        "hand": "exactly_5_hole",
        "hi_lo": "hi_only",
        "lo_rule": None,
        "lo_eight_or_better": False,
        "notes": "",
    }
    r1 = client.post("/api/v1/poker/variants",
                     data=json.dumps(body), content_type="application/json")
    assert r1.status_code == 201
    r2 = client.post("/api/v1/poker/variants",
                     data=json.dumps(body), content_type="application/json")
    assert r2.status_code == 400


def test_delete_user_variant_works():
    client = _client()
    body = {
        "name": "Throwaway",
        "description": "x",
        "family": "home",
        "deck": {"decks": 1, "jokers": 0},
        "deal": {
            "hole_cards": 5, "up_cards": 0,
            "community_streets": [], "stud_streets": [],
            "stud_face_down_final": False, "draws": [],
        },
        "wilds": [],
        "hand": "exactly_5_hole",
        "hi_lo": "hi_only",
        "lo_rule": None,
        "lo_eight_or_better": False,
        "notes": "",
    }
    r1 = client.post("/api/v1/poker/variants",
                     data=json.dumps(body), content_type="application/json")
    tid = r1.get_json()["_saved_template_id"]
    r2 = client.delete(f"/api/v1/poker/variants/{tid}")
    assert r2.status_code == 204


def test_cannot_delete_builtin_variant_via_poker_route():
    """Built-in variants live in `all_variants()`, not in the templates table,
    so they don't have a template_id. But if a user tries to delete a
    blackjack template via this route, it 404s (game_type filter)."""
    client = _client()
    # Find a blackjack template and try to delete via the poker route.
    blackjack = client.get("/api/v1/templates?game_type=blackjack").get_json()
    if not blackjack["templates"]:
        return
    bid = blackjack["templates"][0]["id"]
    r = client.delete(f"/api/v1/poker/variants/{bid}")
    assert r.status_code == 404


def test_analyze_with_inline_variant_dict():
    r = _client().post(
        "/api/v1/poker/analyze",
        data=json.dumps({
            "variant": {
                "name": "Custom",
                "description": "test",
                "family": "home",
                "deck": {"decks": 1, "jokers": 1},
                "deal": {
                    "hole_cards": 5, "up_cards": 0,
                    "community_streets": [], "stud_streets": [],
                    "stud_face_down_final": False, "draws": [],
                },
                "wilds": [{"kind": "joker", "mode": "fully_wild"}],
                "hand": "exactly_5_hole",
                "hi_lo": "hi_only",
                "lo_rule": None,
                "lo_eight_or_better": False,
                "notes": "",
            },
            "cards": ["AS", "AH", "AD", "AC", "JK"],
        }),
        content_type="application/json",
    )
    assert r.status_code == 200
    data = r.get_json()
    # 4 aces + joker fully wild -> 5 of a kind.
    assert data["hi"]["cls_name"] == "Five of a kind"
