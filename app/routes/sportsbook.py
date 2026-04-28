"""Sportsbook API.

POST   /api/v1/sportsbook/sessions               create session + seed slate
GET    /api/v1/sportsbook/sessions/me            session view + analytics summary
GET    /api/v1/sportsbook/sessions/me/events     events still open to bet on
GET    /api/v1/sportsbook/sessions/me/slips      caller's slips (pending + settled)
POST   /api/v1/sportsbook/sessions/me/slips      place a single or parlay slip
POST   /api/v1/sportsbook/sessions/me/advance    advance the day cursor + settle
GET    /api/v1/sportsbook/sessions/me/analytics  full analytics breakdown
DELETE /api/v1/sportsbook/sessions/me            end the session
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..db import db
from ..models import SportsbookSession
from ..services.sessions import COOKIE_NAME, get_session_token
from ..services.sportsbook import (
    SportsbookError,
    advance_day,
    create_sportsbook_session,
    list_open_events,
    list_user_slips,
    place_slip,
    session_analytics,
)

bp = Blueprint("sportsbook", __name__, url_prefix="/api/v1/sportsbook")
COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 60


def _err(msg: str, code: str, status: int = 400):
    return jsonify(error=msg, code=code), status


def _attach_cookie(response, token: str):
    response.set_cookie(
        COOKIE_NAME, token, max_age=COOKIE_MAX_AGE_SECONDS,
        httponly=True, samesite="Lax", secure=False,
    )
    return response


def _resolve_session() -> tuple[SportsbookSession | None, tuple | None]:
    token = get_session_token() or ""
    if not token:
        return None, _err("no sportsbook session", "NO_SESSION", 404)
    sess = SportsbookSession.query.filter_by(token=token).first()
    if sess is None:
        return None, _err("no sportsbook session", "NO_SESSION", 404)
    return sess, None


@bp.post("/sessions")
def create():
    body = request.get_json() or {}
    starting = int(body.get("starting_bankroll") or 1000)
    seed = body.get("seed")
    try:
        sess = create_sportsbook_session(
            starting_bankroll=starting,
            seed=int(seed) if seed is not None else None,
        )
    except SportsbookError as e:
        return _err(str(e), "BAD_REQUEST")
    response = jsonify(sess.to_dict())
    response.status_code = 201
    return _attach_cookie(response, sess.token)


@bp.get("/sessions/me")
def get_me():
    sess, err = _resolve_session()
    if err:
        return err
    payload = sess.to_dict()
    payload["analytics_summary"] = session_analytics(sess)["summary"]
    return jsonify(payload)


@bp.get("/sessions/me/events")
def list_events():
    sess, err = _resolve_session()
    if err:
        return err
    return jsonify(events=list_open_events(sess), current_day=sess.current_day)


@bp.get("/sessions/me/slips")
def list_slips():
    sess, err = _resolve_session()
    if err:
        return err
    return jsonify(slips=list_user_slips(sess))


@bp.post("/sessions/me/slips")
def place_route():
    sess, err = _resolve_session()
    if err:
        return err
    body = request.get_json() or {}
    legs = body.get("legs") or []
    stake = body.get("stake")
    if not isinstance(stake, int) or stake <= 0:
        return _err("stake must be int > 0", "BAD_REQUEST")
    if not isinstance(legs, list) or not legs:
        return _err("legs must be a non-empty list", "BAD_REQUEST")
    try:
        slip = place_slip(
            sess,
            legs_input=legs,
            stake=stake,
            slip_type=body.get("slip_type"),
        )
    except SportsbookError as e:
        return _err(str(e), "SPORTSBOOK_ERROR", 409)
    return jsonify(slip.to_dict()), 201


@bp.post("/sessions/me/advance")
def advance_route():
    sess, err = _resolve_session()
    if err:
        return err
    body = request.get_json() or {}
    seed = body.get("seed")
    try:
        result = advance_day(sess, seed=int(seed) if seed is not None else None)
    except SportsbookError as e:
        return _err(str(e), "SPORTSBOOK_ERROR", 409)
    return jsonify(result)


@bp.get("/sessions/me/analytics")
def analytics_route():
    sess, err = _resolve_session()
    if err:
        return err
    return jsonify(session_analytics(sess))


@bp.delete("/sessions/me")
def delete_route():
    sess, err = _resolve_session()
    if err:
        return err
    db.session.delete(sess)
    db.session.commit()
    response = jsonify(deleted=True)
    response.set_cookie(COOKIE_NAME, "", max_age=0)
    return response
