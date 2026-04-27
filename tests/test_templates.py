"""Smoke tests for the SettingsTemplate model + presets seeding + API."""
import json

from app import create_app
from app.config import Config
from app.db import db


class _TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test"


def _client():
    app = create_app(_TestConfig())
    return app, app.test_client()


def test_presets_seeded_on_boot():
    app, client = _client()
    with app.app_context():
        from app.models import SettingsTemplate
        names = {t.name for t in SettingsTemplate.query.all()}
    assert "Vegas Strip 6:5 H17" in names
    assert "Vegas Downtown 3:2 H17" in names
    assert "Single-Deck 3:2 H17" in names
    assert "European No-Hole 3:2 S17" in names


def test_list_templates_endpoint():
    _, client = _client()
    r = client.get("/api/v1/templates")
    assert r.status_code == 200
    data = r.get_json()
    assert "templates" in data
    assert any(t["is_builtin"] for t in data["templates"])


def test_create_user_template_then_delete():
    _, client = _client()
    body = {
        "name": "My Custom Game",
        "description": "Test",
        "rules": {"decks": 4, "min_bet": 5},
        "side_bets": {},
    }
    r = client.post(
        "/api/v1/templates",
        data=json.dumps(body),
        content_type="application/json",
    )
    assert r.status_code == 201
    tid = r.get_json()["id"]

    r = client.delete(f"/api/v1/templates/{tid}")
    assert r.status_code == 204


def test_cannot_edit_builtin():
    _, client = _client()
    r = client.get("/api/v1/templates")
    builtin = next(t for t in r.get_json()["templates"] if t["is_builtin"])
    r2 = client.patch(
        f"/api/v1/templates/{builtin['id']}",
        data=json.dumps({"name": "renamed"}),
        content_type="application/json",
    )
    assert r2.status_code == 403


def test_cannot_delete_builtin():
    _, client = _client()
    r = client.get("/api/v1/templates")
    builtin = next(t for t in r.get_json()["templates"] if t["is_builtin"])
    r2 = client.delete(f"/api/v1/templates/{builtin['id']}")
    assert r2.status_code == 403
