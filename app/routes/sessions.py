"""Session API.

POST   /api/v1/sessions             create a session (token in body + cookie)
GET    /api/v1/sessions/me          fetch the session bound to caller's token
GET    /api/v1/sessions/me/stats    derived stats: win rate, mistake rate,
                                    EV-lost-to-mistakes
POST   /api/v1/sessions/me/reset    keep bankroll + stats, reshuffle shoe
DELETE /api/v1/sessions/me          end the current session
"""
from __future__ import annotations

import json

from flask import Blueprint, jsonify, request

from ..db import db
from ..services.sessions import (
    COOKIE_NAME,
    create_from_template,
    get_current_session,
    get_session_token,
    reset_shoe,
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
    sess = get_current_session()
    if not sess:
        return _err("no active session", "NO_SESSION", 404)
    return jsonify(sess.to_dict())


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
