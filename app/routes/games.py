"""Round / play API. All routes operate on the caller's current session
(token resolved via cookie / query param / header).

  POST /api/v1/sessions/me/rounds                   start a round
  GET  /api/v1/sessions/me/rounds/active            current round view
  POST /api/v1/sessions/me/rounds/active/insurance  insurance decision
  POST /api/v1/sessions/me/rounds/active/action     hit / stand / double / split / surrender

Multi-seat note: guests with claimed seats use the same endpoints; the
caller's token is mapped to (session, seat_num) via `resolve_seat_for_token`
and the engine refuses actions for any seat other than the one currently
acting under the caller's token.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..services.games import (
    GameError,
    StartRoundRequest,
    get_active_round_view,
    start_round,
    take_action,
    take_insurance,
)
from ..services.sessions import (
    get_current_session,
    get_session_token,
    resolve_seat_for_token,
)

bp = Blueprint("games", __name__, url_prefix="/api/v1/sessions/me/rounds")


def _err(msg: str, code: str, status: int = 400):
    return jsonify(error=msg, code=code), status


def _require_session():
    sess = get_current_session()
    if not sess:
        return None, _err("no active session", "NO_SESSION", 404)
    return sess, None


def _resolve_seat():
    """Return (session, seat_num, err). The token can be the host's or
    a claimed-seat guest's. Either yields a (session, seat_num) pair."""
    sess, seat_num = resolve_seat_for_token(get_session_token() or "")
    if sess is None or seat_num is None:
        return None, None, _err("no active session", "NO_SESSION", 404)
    return sess, seat_num, None


@bp.post("")
def start():
    # Only the host can start a round. Guest claims watch + act on their
    # own seat once dealing happens; bet sizing for guest seats uses the
    # bot's base_bet by default.
    sess, err = _require_session()
    if err:
        return err
    body = request.get_json() or {}
    main_bet = body.get("main_bet")
    if not isinstance(main_bet, int) or main_bet <= 0:
        return _err("main_bet (int > 0) required", "BAD_REQUEST")
    try:
        view = start_round(
            sess,
            StartRoundRequest(main_bet=main_bet, side_bets=body.get("side_bets")),
        )
    except GameError as e:
        return _err(str(e), "GAME_ERROR", 409)
    return jsonify(view.to_dict()), 201


@bp.get("/active")
def active():
    # Either the host or a guest can view the live round.
    sess, _, err = _resolve_seat()
    if err:
        return err
    view = get_active_round_view(sess)
    if view is None:
        return _err("no round in flight", "NO_ROUND", 404)
    return jsonify(view.to_dict())


@bp.post("/active/insurance")
def insurance():
    sess, seat_num, err = _resolve_seat()
    if err:
        return err
    body = request.get_json() or {}
    accept = bool(body.get("accept", False))
    amount = body.get("amount")
    if amount is not None and not isinstance(amount, int):
        return _err("amount must be int or null", "BAD_REQUEST")
    try:
        view = take_insurance(sess, accept=accept, amount=amount, seat_num=seat_num)
    except GameError as e:
        return _err(str(e), "GAME_ERROR", 409)
    return jsonify(view.to_dict())


@bp.post("/active/action")
def action():
    sess, seat_num, err = _resolve_seat()
    if err:
        return err
    body = request.get_json() or {}
    act = body.get("action")
    if act not in ("hit", "stand", "double", "split", "surrender"):
        return _err("action must be one of hit|stand|double|split|surrender", "BAD_REQUEST")
    try:
        view = take_action(sess, act, seat_num=seat_num)
    except GameError as e:
        return _err(str(e), "GAME_ERROR", 409)
    return jsonify(view.to_dict())
