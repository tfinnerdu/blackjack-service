"""Craps API.

POST   /api/v1/craps/sessions                   create a table
GET    /api/v1/craps/sessions/me                fetch the caller's view
POST   /api/v1/craps/sessions/me/bets           append bets to caller's book
DELETE /api/v1/craps/sessions/me/bets/<id>      cancel a bet from caller's book
POST   /api/v1/craps/sessions/me/roll           host triggers roll; settles all
DELETE /api/v1/craps/sessions/me                end the session (host only)
GET    /api/v1/craps/sessions/by-code/<code>           lobby
POST   /api/v1/craps/sessions/by-code/<code>/join      claim a guest token
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
from ..services.craps import (
    CrapsError,
    add_bets,
    cancel_bet,
    create_craps_session,
    roll as roll_service,
)
from ..services.sessions import COOKIE_NAME, get_session_token

bp = Blueprint("craps", __name__, url_prefix="/api/v1/craps")
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
        return None, False, None, _err("no craps session", "NO_SESSION", 404)
    if sess.game_type != "craps":
        return None, False, None, _err(
            f"caller's session is {sess.game_type!r}, not craps",
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
    payload["caller_book"] = get_caller_bets(sess, token)
    payload["participants"] = [
        {
            "label": entry.get("label"),
            "is_host": is_h,
            "bankroll": int(entry.get("bankroll", 0)),
            "rounds_played": int(entry.get("rounds_played", 0)),
            "open_bets": len(entry.get("current_bets", [])),
        }
        for _, entry, is_h in participants(sess)
    ]
    return payload


@bp.post("/sessions")
def create():
    body = request.get_json() or {}
    try:
        sess = create_craps_session(
            starting_bankroll=int(body.get("starting_bankroll") or 500),
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
def add_bets_route():
    sess, is_host, token, err = _resolve_caller()
    if err:
        return err
    body = request.get_json() or {}
    bets = body.get("bets") or []
    if not isinstance(bets, list):
        return _err("bets must be a list", "BAD_REQUEST")
    try:
        add_bets(sess, token, bets)
    except CrapsError as e:
        return _err(str(e), "CRAPS_ERROR", 409)
    return jsonify(_participant_view(sess, token, is_host))


@bp.delete("/sessions/me/bets/<bet_id>")
def cancel_route(bet_id: str):
    sess, is_host, token, err = _resolve_caller()
    if err:
        return err
    try:
        cancel_bet(sess, token, bet_id)
    except CrapsError as e:
        return _err(str(e), "CRAPS_ERROR", 409)
    return jsonify(_participant_view(sess, token, is_host))


@bp.post("/sessions/me/roll")
def roll_route():
    sess, is_host, _token, err = _resolve_caller()
    if err:
        return err
    if not is_host:
        return _err("only the host can roll the dice", "FORBIDDEN", 403)
    body = request.get_json() or {}
    dice = body.get("dice")
    parsed_dice = None
    if dice:
        if not (isinstance(dice, list) and len(dice) == 2):
            return _err("dice must be [d1, d2]", "BAD_REQUEST")
        parsed_dice = (int(dice[0]), int(dice[1]))
    try:
        result = roll_service(sess, dice=parsed_dice)
    except CrapsError as e:
        return _err(str(e), "CRAPS_ERROR", 409)
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
    if not sess or sess.game_type != "craps":
        return _err("no such craps room", "NO_ROOM", 404)
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
    if not sess or sess.game_type != "craps":
        return _err("no such craps room", "NO_ROOM", 404)
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
