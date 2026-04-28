"""Baccarat API.

POST   /api/v1/baccarat/sessions             create a new shoe
GET    /api/v1/baccarat/sessions/me          fetch the caller's view
POST   /api/v1/baccarat/sessions/me/bets     stage caller's pending bets
POST   /api/v1/baccarat/sessions/me/play     host triggers deal; settles all
DELETE /api/v1/baccarat/sessions/me          end the session (host only)
GET    /api/v1/baccarat/sessions/by-code/<code>           lobby
POST   /api/v1/baccarat/sessions/by-code/<code>/join      claim a guest token
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
from ..services.baccarat import (
    BaccaratError,
    create_baccarat_session,
    play_round,
    stage_bets,
)
from ..services.sessions import COOKIE_NAME, get_session_token

bp = Blueprint("baccarat", __name__, url_prefix="/api/v1/baccarat")
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
        return None, False, None, _err("no baccarat session", "NO_SESSION", 404)
    if sess.game_type != "baccarat":
        return None, False, None, _err(
            f"caller's session is {sess.game_type!r}, not baccarat",
            "WRONG_GAME", 409,
        )
    token = get_session_token() or ""
    return sess, is_host, token, None


def _participant_view(sess, token: str, is_host: bool) -> dict:
    payload = sess.to_dict()
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
        sess = create_baccarat_session(
            starting_bankroll=int(body.get("starting_bankroll") or 500),
            decks=int(body.get("decks") or 8),
            min_bet=int(body.get("min_bet") or 1),
            max_bet=int(body.get("max_bet") or 500),
            seed=body.get("seed"),
        )
    except (ValueError, TypeError) as e:
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
    except BaccaratError as e:
        return _err(str(e), "BACCARAT_ERROR", 409)
    return jsonify(_participant_view(sess, token, is_host))


@bp.post("/sessions/me/play")
def play_route():
    sess, is_host, _token, err = _resolve_caller()
    if err:
        return err
    if not is_host:
        return _err("only the host can deal the next round", "FORBIDDEN", 403)
    try:
        result = play_round(sess)
    except BaccaratError as e:
        return _err(str(e), "BACCARAT_ERROR", 409)
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
    if not sess or sess.game_type != "baccarat":
        return _err("no such baccarat room", "NO_ROOM", 404)
    payload = sess.to_dict()
    payload.pop("token", None)
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
    if not sess or sess.game_type != "baccarat":
        return _err("no such baccarat room", "NO_ROOM", 404)
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
