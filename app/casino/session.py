"""Lifecycle helpers for CasinoSession (the shared row used by Roulette,
Baccarat, Craps). Exposes a small surface:

- create_session(game_type, starting_bankroll, rules)
- get_session_for_token(token) → (session, is_host)
- get_session_for_room_code(code)
- claim_guest_seat(sess) → fresh guest token
- release_guest_seat(sess, token)
- record_round(sess, *, profit, summary) — bumps bankroll + appends history

All of these are deliberately game-agnostic; the engine code stays in
its game's module.
"""
from __future__ import annotations

import json
import secrets
from typing import Optional

from ..db import db
from ..models import CasinoSession


# Capped at 500 entries to keep the row size bounded for long sessions.
HISTORY_CAP = 500


def create_session(
    *,
    game_type: str,
    starting_bankroll: int,
    rules: dict,
    state: Optional[dict] = None,
) -> CasinoSession:
    if starting_bankroll <= 0:
        raise ValueError("starting_bankroll must be > 0")
    sess = CasinoSession(
        game_type=game_type,
        starting_bankroll=starting_bankroll,
        bankroll=starting_bankroll,
        rules_json=json.dumps(rules),
        state_json=json.dumps(state or {}),
        history_json="[]",
        room_code=_unique_casino_room_code(),
        guest_tokens_json="{}",
    )
    db.session.add(sess)
    db.session.commit()
    return sess


def _unique_casino_room_code(max_attempts: int = 8) -> str:
    """Mirror the blackjack helper's collision check across both tables —
    a code shared by GameSession and CasinoSession would clash in the
    URL space. Local imports keep the module dependency-cycle-free.
    """
    from ..services.sessions import _new_room_code
    from ..models import GameSession

    for _ in range(max_attempts):
        code = _new_room_code()
        if (
            CasinoSession.query.filter_by(room_code=code).first() is None
            and GameSession.query.filter_by(room_code=code).first() is None
        ):
            return code
    return _new_room_code()


def get_session_for_room_code(code: str) -> Optional[CasinoSession]:
    if not code:
        return None
    return CasinoSession.query.filter_by(room_code=code.upper()).first()


def get_session_for_token(token: str) -> tuple[Optional[CasinoSession], bool]:
    """Resolve a token to (session, is_host). Tokens may be the host's
    primary session.token, or a guest token registered in
    `guest_tokens_json`. Returns (None, False) when unknown."""
    if not token:
        return None, False
    sess = CasinoSession.query.filter_by(token=token).first()
    if sess is not None:
        return sess, True
    candidates = CasinoSession.query.filter(
        CasinoSession.guest_tokens_json.like(f"%{token}%")
    ).all()
    for cand in candidates:
        guests = json.loads(cand.guest_tokens_json or "{}")
        if token in guests.values():
            return cand, False
    return None, False


def claim_guest_seat(sess: CasinoSession, *, label: Optional[str] = None) -> str:
    """Mint a fresh guest token tied to this session. Any number of
    guests can join — they bet alongside the host's spins/rolls/deals
    using their own private bankroll tracked in their token's history."""
    guests = json.loads(sess.guest_tokens_json or "{}")
    token = secrets.token_urlsafe(32)
    guests[token] = {"label": label or "guest"}
    sess.guest_tokens_json = json.dumps(guests)
    db.session.commit()
    return token


def release_guest_seat(sess: CasinoSession, token: str) -> None:
    guests = json.loads(sess.guest_tokens_json or "{}")
    if token in guests:
        del guests[token]
        sess.guest_tokens_json = json.dumps(guests)
        db.session.commit()


def record_round(
    sess: CasinoSession,
    *,
    profit: int,
    summary: dict,
) -> None:
    """Apply a settled round: bumps the bankroll by `profit` (can be
    negative), increments rounds_played, and appends a history entry.
    `summary` is whatever the game wants to log; the Stats page will
    surface a few standard keys (bankroll, profit, label) and the rest
    can be game-specific.
    """
    sess.bankroll = (sess.bankroll or 0) + int(profit)
    sess.rounds_played = (sess.rounds_played or 0) + 1
    history = json.loads(sess.history_json or "[]")
    history.append({
        "round": sess.rounds_played,
        "bankroll": sess.bankroll,
        "profit": int(profit),
        **summary,
    })
    if len(history) > HISTORY_CAP:
        history = history[-HISTORY_CAP:]
    sess.history_json = json.dumps(history)
    db.session.commit()
