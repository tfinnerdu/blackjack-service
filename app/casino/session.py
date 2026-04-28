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
    primary session.token, or a guest token registered as a KEY in
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
        if token in guests:
            return cand, False
    return None, False


def claim_guest_seat(
    sess: CasinoSession,
    *,
    label: Optional[str] = None,
    starting_bankroll: Optional[int] = None,
) -> str:
    """Mint a fresh guest token tied to this session. Each guest gets
    their own private bankroll + bet history; the host's row-level
    bankroll is theirs alone. `starting_bankroll` defaults to the
    host's starting bankroll so guests come in even with the host."""
    starting = int(starting_bankroll if starting_bankroll is not None else sess.starting_bankroll)
    guests = json.loads(sess.guest_tokens_json or "{}")
    token = secrets.token_urlsafe(32)
    guests[token] = {
        "label": label or "guest",
        "bankroll": starting,
        "starting_bankroll": starting,
        "rounds_played": 0,
        "history": [],
        "current_bets": [],
    }
    sess.guest_tokens_json = json.dumps(guests)
    db.session.commit()
    return token


def release_guest_seat(sess: CasinoSession, token: str) -> None:
    guests = json.loads(sess.guest_tokens_json or "{}")
    if token in guests:
        del guests[token]
        sess.guest_tokens_json = json.dumps(guests)
        db.session.commit()


def _normalize_guest_entry(entry) -> dict:
    """Older sessions stored guest entries as `{label}` only — coerce
    them into the full shape with bankroll fields."""
    if isinstance(entry, str):
        return {"label": entry, "bankroll": 0, "starting_bankroll": 0,
                "rounds_played": 0, "history": [], "current_bets": []}
    if not isinstance(entry, dict):
        return {"label": "guest", "bankroll": 0, "starting_bankroll": 0,
                "rounds_played": 0, "history": [], "current_bets": []}
    return {
        "label": entry.get("label", "guest"),
        "bankroll": int(entry.get("bankroll", 0) or 0),
        "starting_bankroll": int(entry.get("starting_bankroll", 0) or 0),
        "rounds_played": int(entry.get("rounds_played", 0) or 0),
        "history": list(entry.get("history", [])),
        "current_bets": list(entry.get("current_bets", [])),
    }


def get_guest_entry(sess: CasinoSession, token: str) -> Optional[dict]:
    guests = json.loads(sess.guest_tokens_json or "{}")
    if token not in guests:
        return None
    return _normalize_guest_entry(guests[token])


def participants(sess: CasinoSession) -> list[tuple[Optional[str], dict, bool]]:
    """List of (token, entry, is_host) — host first, then each guest.
    The host's `token` slot is None to flag 'use sess directly'.
    """
    state = json.loads(sess.state_json or "{}")
    host_entry = {
        "label": "host",
        "bankroll": int(sess.bankroll or 0),
        "starting_bankroll": int(sess.starting_bankroll or 0),
        "rounds_played": int(sess.rounds_played or 0),
        "history": json.loads(sess.history_json or "[]"),
        "current_bets": list(state.get("host_bets", [])),
    }
    out: list[tuple[Optional[str], dict, bool]] = [(None, host_entry, True)]
    guests = json.loads(sess.guest_tokens_json or "{}")
    for token, entry in guests.items():
        out.append((token, _normalize_guest_entry(entry), False))
    return out


def get_caller_bankroll(sess: CasinoSession, token: str) -> int:
    if token == sess.token:
        return int(sess.bankroll or 0)
    entry = get_guest_entry(sess, token)
    return int(entry.get("bankroll", 0)) if entry else 0


def get_caller_bets(sess: CasinoSession, token: str) -> list[dict]:
    if token == sess.token:
        state = json.loads(sess.state_json or "{}")
        return list(state.get("host_bets", []))
    entry = get_guest_entry(sess, token)
    return list(entry.get("current_bets", [])) if entry else []


def set_caller_bets(sess: CasinoSession, token: str, bets: list[dict]) -> None:
    """Replace the caller's pending bets. Called by `/sessions/me/bets`
    on each game's blueprint; the per-game routes apply game-specific
    validation before calling here."""
    if token == sess.token:
        state = json.loads(sess.state_json or "{}")
        state["host_bets"] = list(bets)
        sess.state_json = json.dumps(state)
    else:
        guests = json.loads(sess.guest_tokens_json or "{}")
        if token not in guests:
            return
        entry = _normalize_guest_entry(guests[token])
        entry["current_bets"] = list(bets)
        guests[token] = entry
        sess.guest_tokens_json = json.dumps(guests)
    db.session.commit()


def clear_caller_bets(sess: CasinoSession, token: str) -> None:
    set_caller_bets(sess, token, [])


def apply_round_to_participant(
    sess: CasinoSession,
    token: Optional[str],
    *,
    profit: int,
    summary: dict,
) -> None:
    """Apply a single participant's settlement. `token=None` means the
    host (mutates session row); a guest token mutates that entry."""
    if token is None or token == sess.token:
        record_round(sess, profit=profit, summary=summary)
        return
    guests = json.loads(sess.guest_tokens_json or "{}")
    if token not in guests:
        return
    entry = _normalize_guest_entry(guests[token])
    entry["bankroll"] += int(profit)
    entry["rounds_played"] += 1
    history = entry["history"]
    history.append({
        "round": entry["rounds_played"],
        "bankroll": entry["bankroll"],
        "profit": int(profit),
        **summary,
    })
    if len(history) > HISTORY_CAP:
        history = history[-HISTORY_CAP:]
    entry["history"] = history
    guests[token] = entry
    sess.guest_tokens_json = json.dumps(guests)
    db.session.commit()


def record_round(
    sess: CasinoSession,
    *,
    profit: int,
    summary: dict,
) -> None:
    """Host-only path used by single-player flows. For multi-participant
    settlement use `apply_round_to_participant`."""
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
