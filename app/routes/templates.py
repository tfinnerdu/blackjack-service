"""Settings templates API. Read-only for builtins, full CRUD for user-created.

Phase 2 surface:
  GET    /api/v1/templates           list
  GET    /api/v1/templates/<id>      detail
  POST   /api/v1/templates           create (user template)
  PATCH  /api/v1/templates/<id>      update (user template only)
  DELETE /api/v1/templates/<id>      delete (user template only)
"""
from __future__ import annotations

import json

from flask import Blueprint, jsonify, request

from ..db import db
from ..models import SettingsTemplate

bp = Blueprint("templates", __name__, url_prefix="/api/v1/templates")


def _err(message: str, code: str, status: int = 400):
    return jsonify(error=message, code=code), status


@bp.get("")
def list_templates():
    game_type = request.args.get("game_type")
    q = SettingsTemplate.query
    if game_type:
        q = q.filter_by(game_type=game_type)
    templates = q.order_by(
        SettingsTemplate.is_builtin.desc(),
        SettingsTemplate.name.asc(),
    ).all()
    return jsonify(templates=[t.to_dict() for t in templates])


@bp.get("/<int:template_id>")
def get_template(template_id: int):
    t = db.session.get(SettingsTemplate, template_id)
    if not t:
        return _err("template not found", "NOT_FOUND", 404)
    return jsonify(t.to_dict())


@bp.post("")
def create_template():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip()
    game_type = (data.get("game_type") or "blackjack").strip()
    rules = data.get("rules")
    side_bets = data.get("side_bets")
    if not name or rules is None or side_bets is None:
        return _err("name, rules, side_bets required", "BAD_REQUEST")
    if SettingsTemplate.query.filter_by(name=name).first():
        return _err("template name already exists", "DUPLICATE")
    t = SettingsTemplate(
        game_type=game_type,
        name=name,
        description=description,
        rules_json=json.dumps(rules),
        side_bets_json=json.dumps(side_bets),
        is_builtin=False,
    )
    db.session.add(t)
    db.session.commit()
    return jsonify(t.to_dict()), 201


@bp.patch("/<int:template_id>")
def update_template(template_id: int):
    t = db.session.get(SettingsTemplate, template_id)
    if not t:
        return _err("template not found", "NOT_FOUND", 404)
    if t.is_builtin:
        return _err("cannot edit a built-in template; clone it first", "BUILTIN_READ_ONLY", 403)
    data = request.get_json() or {}
    if "name" in data:
        t.name = data["name"].strip()
    if "description" in data:
        t.description = data["description"].strip()
    if "rules" in data:
        t.rules_json = json.dumps(data["rules"])
    if "side_bets" in data:
        t.side_bets_json = json.dumps(data["side_bets"])
    db.session.commit()
    return jsonify(t.to_dict())


@bp.delete("/<int:template_id>")
def delete_template(template_id: int):
    t = db.session.get(SettingsTemplate, template_id)
    if not t:
        return _err("template not found", "NOT_FOUND", 404)
    if t.is_builtin:
        return _err("cannot delete a built-in template", "BUILTIN_READ_ONLY", 403)
    db.session.delete(t)
    db.session.commit()
    return ("", 204)
