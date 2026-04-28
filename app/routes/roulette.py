"""Roulette API.

POST   /api/v1/roulette/sessions             create a new wheel
GET    /api/v1/roulette/sessions/me          fetch the caller's view
POST   /api/v1/roulette/sessions/me/bets     stage caller's pending bets
POST   /api/v1/roulette/sessions/me/spin     host triggers wheel; settles all
DELETE /api/v1/roulette/sessions/me          end the session (host only)
GET    /api/v1/roulette/sessions/by-code/<code>           lobby
POST   /api/v1/roulette/sessions/by-code/<code>/join      claim a guest token
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..casino import (
    claim_guest_seat,
    get_caller_bankroll,
    get_caller_bets,
    get_session_for_room_code,
    get_session_for_token,
    participants,
)
from ..db import db
from ..roulette import WheelKind
from ..services.roulette import (
    RouletteError,
    create_roulette_session,
    spin,
    stage_bets,
)
from ..services.sessions import COOKIE_NAME, get_session_token

bp = Blueprint("roulette", __name__, url_prefix="/api/v1/roulette")
COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 60


def _err(msg: str, code: str, status: int = 400):
    return jsonify(error=msg, code=code), status


def _attach_cookie(response, token: str):
    response.set_cookie(
        COOKIE_NAME, token, max_age=COOKIE_MAX_AGE_SECONDS,
        httponly=True, samesite="Lax", secure=False,
    )
    return response


def _resolve_caller():
    sess, is_host = get_session_for_token(get_session_token() or "")
    if sess is None:
        return None, False, None, _err("no roulette session", "NO_SESSION", 404)
    if sess.game_type != "roulette":
        return None, False, None, _err(
            f"caller's session is {sess.game_type!r}, not roulette",
            "WRONG_GAME", 409,
        )
    token = get_session_token() or ""
    return sess, is_host, token, None


def _participant_view(sess, token: str, is_host: bool) -> dict:
    """Per-caller slice of the session: their bankroll, their pending
    bets, plus the room-wide table state and a roster of participants
    so the UI can render presence."""
    payload = sess.to_dict()
    # Strip the host's primary token from anyone but the host.
    if not is_host:
        payload.pop("token", None)
    payload["caller_is_host"] = is_host
    payload["caller_bankroll"] = get_caller_bankroll(sess, token)
    payload["caller_pending_bets"] = get_caller_bets(sess, token)
    payload["participants"] = [
        {
            "label": entry.get("label"),
            "is_host": is_h,
            "bankroll": int(entry.get("bankroll", 0)),
            "rounds_played": int(entry.get("rounds_played", 0)),
            "has_pending_bets": bool(entry.get("current_bets")),
        }
        for _, entry, is_h in participants(sess)
    ]
    return payload


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
    sess, is_host, token, err = _resolve_caller()
    if err:
        return err
    return jsonify(_participant_view(sess, token, is_host))


@bp.post("/sessions/me/bets")
def stage_bets_route():
    sess, is_host, token, err = _resolve_caller()
    if err:
        return err
    body = request.get_json() or {}
    bets = body.get("bets") or []
    if not isinstance(bets, list):
        return _err("bets must be a list", "BAD_REQUEST")
    try:
        stage_bets(sess, token, bets)
    except RouletteError as e:
        return _err(str(e), "ROULETTE_ERROR", 409)
    return jsonify(_participant_view(sess, token, is_host))


@bp.post("/sessions/me/spin")
def spin_route():
    sess, is_host, _token, err = _resolve_caller()
    if err:
        return err
    if not is_host:
        return _err("only the host can spin the wheel", "FORBIDDEN", 403)
    try:
        result = spin(sess)
    except RouletteError as e:
        return _err(str(e), "ROULETTE_ERROR", 409)
    return jsonify(result)


@bp.delete("/sessions/me")
def delete_me():
    sess, is_host, _token, err = _resolve_caller()
    if err:
        return err
    if not is_host:
        return _err("only the host can end the room", "FORBIDDEN", 403)
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
    payload.pop("token", None)
    # Slim guest-token map for public consumption.
    payload["participants"] = [
        {
            "label": entry.get("label"),
            "is_host": is_h,
            "bankroll": int(entry.get("bankroll", 0)),
            "rounds_played": int(entry.get("rounds_played", 0)),
        }
        for _, entry, is_h in participants(sess)
    ]
    return jsonify(payload)


@bp.post("/sessions/by-code/<code>/join")
def join_by_code(code: str):
    sess = get_session_for_room_code(code)
    if not sess or sess.game_type != "roulette":
        return _err("no such roulette room", "NO_ROOM", 404)
    body = request.get_json() or {}
    label = body.get("label") or None
    starting = body.get("starting_bankroll")
    token = claim_guest_seat(
        sess,
        label=label,
        starting_bankroll=int(starting) if starting else None,
    )
    response = jsonify(token=token, room=sess.to_dict())
    response.status_code = 201
    return _attach_cookie(response, token)
