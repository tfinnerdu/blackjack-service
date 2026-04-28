"""Roulette API.

POST   /api/v1/roulette/sessions             create a new wheel
GET    /api/v1/roulette/sessions/me          fetch the active session
POST   /api/v1/roulette/sessions/me/spin     place bets + spin once
DELETE /api/v1/roulette/sessions/me          end the current session
GET    /api/v1/roulette/sessions/by-code/<code>           lobby
POST   /api/v1/roulette/sessions/by-code/<code>/join      claim a guest token
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..casino import (
    claim_guest_seat,
    get_session_for_room_code,
    get_session_for_token,
)
from ..db import db
from ..roulette import WheelKind
from ..services.roulette import (
    RouletteError,
    create_roulette_session,
    spin,
)
from ..services.sessions import COOKIE_NAME, get_session_token

bp = Blueprint("roulette", __name__, url_prefix="/api/v1/roulette")
COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 60


def _err(msg: str, code: str, status: int = 400):
    return jsonify(error=msg, code=code), status


def _attach_cookie(response, token: str):
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        samesite="Lax",
        secure=False,
    )
    return response


def _resolve_caller():
    sess, is_host = get_session_for_token(get_session_token() or "")
    if sess is None:
        return None, False, _err("no roulette session", "NO_SESSION", 404)
    if sess.game_type != "roulette":
        return None, False, _err(
            f"caller's session is {sess.game_type!r}, not roulette",
            "WRONG_GAME", 409,
        )
    return sess, is_host, None


@bp.post("/sessions")
def create():
    body = request.get_json() or {}
    try:
        kind = WheelKind(body.get("wheel_kind", "american"))
    except ValueError:
        return _err("wheel_kind must be 'american' or 'european'", "BAD_REQUEST")
    starting = int(body.get("starting_bankroll") or 500)
    min_bet = int(body.get("min_bet") or 1)
    max_bet = int(body.get("max_bet") or 500)
    seed = body.get("seed")
    try:
        sess = create_roulette_session(
            starting_bankroll=starting,
            wheel_kind=kind,
            min_bet=min_bet,
            max_bet=max_bet,
            seed=seed,
        )
    except ValueError as e:
        return _err(str(e), "BAD_REQUEST")
    response = jsonify(sess.to_dict())
    response.status_code = 201
    return _attach_cookie(response, sess.token)


@bp.get("/sessions/me")
def get_me():
    sess, is_host, err = _resolve_caller()
    if err:
        return err
    payload = sess.to_dict()
    payload["caller_is_host"] = is_host
    return jsonify(payload)


@bp.post("/sessions/me/spin")
def spin_route():
    sess, _is_host, err = _resolve_caller()
    if err:
        return err
    body = request.get_json() or {}
    bets = body.get("bets") or []
    if not isinstance(bets, list):
        return _err("bets must be a list", "BAD_REQUEST")
    try:
        result = spin(sess, bets)
    except RouletteError as e:
        return _err(str(e), "ROULETTE_ERROR", 409)
    return jsonify(result.to_dict())


@bp.delete("/sessions/me")
def delete_me():
    sess, _is_host, err = _resolve_caller()
    if err:
        return err
    db.session.delete(sess)
    db.session.commit()
    response = jsonify(deleted=True)
    response.set_cookie(COOKIE_NAME, "", max_age=0)
    return response


@bp.get("/sessions/by-code/<code>")
def get_by_code(code: str):
    sess = get_session_for_room_code(code)
    if not sess or sess.game_type != "roulette":
        return _err("no such roulette room", "NO_ROOM", 404)
    payload = sess.to_dict()
    # Don't leak the host's primary token in the public lobby view.
    payload.pop("token", None)
    return jsonify(payload)


@bp.post("/sessions/by-code/<code>/join")
def join_by_code(code: str):
    sess = get_session_for_room_code(code)
    if not sess or sess.game_type != "roulette":
        return _err("no such roulette room", "NO_ROOM", 404)
    body = request.get_json() or {}
    label = body.get("label") or None
    token = claim_guest_seat(sess, label=label)
    response = jsonify(token=token, room=sess.to_dict())
    response.status_code = 201
    return _attach_cookie(response, token)
