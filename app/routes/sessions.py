"""Session API.

POST   /api/v1/sessions             create a session (token in body + cookie)
GET    /api/v1/sessions/me          fetch the session bound to caller's token
GET    /api/v1/sessions/me/stats    derived stats: win rate, mistake rate,
                                    EV-lost-to-mistakes
POST   /api/v1/sessions/me/reset    keep bankroll + stats, reshuffle shoe
DELETE /api/v1/sessions/me          end the current session
GET    /api/v1/sessions/by-code/<code>                       lobby info
POST   /api/v1/sessions/by-code/<code>/seats/<n>/claim       claim a bot seat
POST   /api/v1/sessions/by-code/<code>/seats/<n>/release     drop a guest claim
"""
from __future__ import annotations

import json

from flask import Blueprint, jsonify, request

from ..db import db
from ..services.sessions import (
    COOKIE_NAME,
    claim_seat,
    create_from_template,
    get_current_session,
    get_session_by_room_code,
    get_session_token,
    release_seat,
    reset_shoe,
    resolve_seat_for_token,
)

bp = Blueprint("sessions", __name__, url_prefix="/api/v1/sessions")

# Anonymous tokens last 60 days unless the user clears their cookies.
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
        secure=False,  # flip to True behind HTTPS-only deployments (Render is HTTPS)
    )
    return response


@bp.post("")
def create():
    body = request.get_json() or {}
    try:
        sess = create_from_template(
            template_id=body.get("template_id"),
            starting_bankroll=body.get("starting_bankroll"),
            player_seat=body.get("player_seat"),
            ai_seats=body.get("ai_seats"),
            rules_overrides=body.get("rules"),
            side_bets_overrides=body.get("side_bets"),
            seed=body.get("seed"),
        )
    except ValueError as e:
        return _err(str(e), "BAD_REQUEST")

    response = jsonify(sess.to_dict())
    response.status_code = 201
    return _attach_cookie(response, sess.token)


@bp.get("/me")
def get_me():
    # Either the host's token or a guest's seat token resolves here. We
    # tag the response with `caller_seat` so the UI can render the
    # right seat-specific affordances.
    sess, seat_num = resolve_seat_for_token(get_session_token() or "")
    if not sess:
        return _err("no active session", "NO_SESSION", 404)
    payload = sess.to_dict()
    payload["caller_seat"] = seat_num
    payload["caller_is_host"] = (seat_num == sess.player_seat)
    return jsonify(payload)


@bp.get("/me/stats")
def stats_me():
    """Derived blackjack stats. Computes ratios + EV-lost-as-dollars on
    top of the raw counters in the session row so the UI can render them
    directly."""
    sess = get_current_session()
    if not sess:
        return _err("no active session", "NO_SESSION", 404)
    hp = sess.hands_played or 0
    win_rate = round(sess.wins / hp * 100, 1) if hp else 0.0
    mistake_rate = round(sess.book_mistakes / hp * 100, 1) if hp else 0.0
    bj_rate = round(sess.player_blackjacks / hp * 100, 1) if hp else 0.0
    bust_rate = round(sess.busts / hp * 100, 1) if hp else 0.0
    return jsonify(
        hands_played=hp,
        starting_bankroll=sess.starting_bankroll,
        bankroll=sess.bankroll,
        net_profit=sess.bankroll - sess.starting_bankroll,
        wins=sess.wins,
        losses=sess.losses,
        pushes=sess.pushes,
        player_blackjacks=sess.player_blackjacks,
        busts=sess.busts,
        surrenders=sess.surrenders,
        book_mistakes=sess.book_mistakes,
        ev_lost_dollars=round(sess.ev_lost_cents / 100, 2),
        ev_lost_estimate_note="Heuristic estimate, not a true Monte Carlo EV.",
        rates={
            "win_pct": win_rate,
            "loss_pct": round(sess.losses / hp * 100, 1) if hp else 0.0,
            "push_pct": round(sess.pushes / hp * 100, 1) if hp else 0.0,
            "mistake_pct": mistake_rate,
            "blackjack_pct": bj_rate,
            "bust_pct": bust_rate,
        },
        counter={
            "running_count": sess.running_count,
            "cards_seen": sess.counter_cards_seen,
        },
        bankrolls={
            "actual": sess.bankroll,
            "book": sess.book_bankroll,
            "counter": sess.counter_bankroll,
            "starting": sess.starting_bankroll,
        },
        bankroll_history=json.loads(sess.bankroll_history_json or "[]"),
    )


@bp.post("/me/reset")
def reset_me():
    sess = get_current_session()
    if not sess:
        return _err("no active session", "NO_SESSION", 404)
    body = request.get_json() or {}
    reset_shoe(sess, new_seed=body.get("seed"))
    return jsonify(sess.to_dict())


# ---- room code / seat-claim ------------------------------------------

def _room_view(sess) -> dict:
    """Public lobby view of a room — no host token, no shoe internals.
    Anyone with the room code can fetch this to decide which seat to grab."""
    rules = json.loads(sess.rules_json)
    ai_rows = json.loads(sess.ai_seats_json)
    claimed = json.loads(sess.seat_tokens_json or "{}")
    seats = []
    for n in range(1, int(rules.get("seats", 1)) + 1):
        if n == sess.player_seat:
            seats.append({"seat_num": n, "kind": "host", "claimable": False})
            continue
        ai = next((r for r in ai_rows if int(r["seat_num"]) == n), None)
        is_claimed = str(n) in claimed
        seats.append({
            "seat_num": n,
            "kind": "guest" if is_claimed else "ai",
            "claimable": ai is not None and not is_claimed,
            "playstyle": ai.get("playstyle") if ai else None,
            "bet_pattern": ai.get("bet_pattern") if ai else None,
            "base_bet": ai.get("base_bet") if ai else None,
            "bankroll": ai.get("bankroll") if ai else None,
        })
    return {
        "room_code": sess.room_code,
        "template_name": sess.template.name if sess.template else None,
        "rules": rules,
        "seats": seats,
        "player_seat": sess.player_seat,
        "hands_played": sess.hands_played,
    }


@bp.get("/by-code/<code>")
def get_by_code(code: str):
    sess = get_session_by_room_code(code)
    if not sess:
        return _err("no such room", "NO_ROOM", 404)
    return jsonify(_room_view(sess))


@bp.post("/by-code/<code>/seats/<int:seat_num>/claim")
def claim_seat_route(code: str, seat_num: int):
    sess = get_session_by_room_code(code)
    if not sess:
        return _err("no such room", "NO_ROOM", 404)
    try:
        token = claim_seat(sess, seat_num)
    except ValueError as e:
        return _err(str(e), "BAD_REQUEST", 400)
    response = jsonify(token=token, seat_num=seat_num, room=_room_view(sess))
    response.status_code = 201
    return _attach_cookie(response, token)


@bp.post("/by-code/<code>/seats/<int:seat_num>/release")
def release_seat_route(code: str, seat_num: int):
    sess = get_session_by_room_code(code)
    if not sess:
        return _err("no such room", "NO_ROOM", 404)
    # Only the seat owner (or host) can release.
    caller = get_session_token() or ""
    seats = json.loads(sess.seat_tokens_json or "{}")
    is_owner = seats.get(str(seat_num)) == caller
    is_host = caller == sess.token
    if not (is_owner or is_host):
        return _err("not authorized to release this seat", "FORBIDDEN", 403)
    release_seat(sess, seat_num)
    return jsonify(_room_view(sess))


@bp.delete("/me")
def delete_me():
    sess = get_current_session()
    if not sess:
        return _err("no active session", "NO_SESSION", 404)
    db.session.delete(sess)
    db.session.commit()
    response = jsonify(deleted=True)
    response.set_cookie(COOKIE_NAME, "", max_age=0)
    return response
