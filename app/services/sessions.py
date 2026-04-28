"""Session lifecycle. Create-from-template, lookup-by-token, reset-shoe,
and the snapshot/restore helpers the round API will use in phase 6.

Auth is anonymous and cookie-based. The token also works as a URL query
param so a session is shareable / installable as a PWA without a login flow.
"""
from __future__ import annotations

import json
import random
from dataclasses import asdict, fields, is_dataclass
from typing import Any, Optional

from flask import Request, request

from ..config import Config
from ..db import db
from ..engine.rules import (
    DoubleRule,
    Rules,
    ShuffleMode,
    SideBets,
    SurrenderRule,
)
from ..engine.shoe import Shoe
from ..models import GameSession, SettingsTemplate

COOKIE_NAME = Config.SESSION_COOKIE_NAME
TOKEN_QUERY_PARAM = "session"


# ---- token plumbing ----------------------------------------------------

def get_session_token(req: Optional[Request] = None) -> Optional[str]:
    """Pull the anonymous session token from the cookie, then the query
    string, then a header (in priority order)."""
    req = req or request
    return (
        req.cookies.get(COOKIE_NAME)
        or req.args.get(TOKEN_QUERY_PARAM)
        or req.headers.get("X-Session-Token")
    )


def get_current_session(req: Optional[Request] = None) -> Optional[GameSession]:
    token = get_session_token(req)
    if not token:
        return None
    return GameSession.query.filter_by(token=token).first()


# ---- rule coercion (mirrors strategy route) ----------------------------

_ENUM_FIELDS = {
    "shuffle_mode": ShuffleMode,
    "double_rule": DoubleRule,
    "surrender": SurrenderRule,
}


def rules_from_dict(rules_dict: dict[str, Any]) -> Rules:
    valid = {f.name for f in fields(Rules)}
    kwargs: dict[str, Any] = {}
    for k, v in rules_dict.items():
        if k not in valid:
            continue
        if k in _ENUM_FIELDS and isinstance(v, str):
            v = _ENUM_FIELDS[k](v)
        elif k in ("blackjack_payout", "insurance_payout") and isinstance(v, list):
            v = tuple(v)
        kwargs[k] = v
    return Rules(**kwargs)


def side_bets_from_dict(sb_dict: dict[str, Any]) -> SideBets:
    """Reconstruct a SideBets from a JSON-friendly dict. Unknown keys are
    ignored so rule expansions don't break old sessions."""
    sb = SideBets()
    for f in fields(SideBets):
        sub = sb_dict.get(f.name)
        if not sub:
            continue
        target = getattr(sb, f.name)
        for k, v in sub.items():
            if hasattr(target, k):
                # Tuples of (num, den) come over the wire as lists.
                if isinstance(v, list):
                    v = tuple(v)
                setattr(target, k, v)
    return sb


# ---- session creation --------------------------------------------------

def create_from_template(
    template_id: Optional[int],
    *,
    starting_bankroll: Optional[int] = None,
    player_seat: Optional[int] = None,
    ai_seats: Optional[list[dict]] = None,
    rules_overrides: Optional[dict] = None,
    side_bets_overrides: Optional[dict] = None,
    seed: Optional[int] = None,
) -> GameSession:
    """Spin up a new GameSession.

    `template_id=None` means "use whatever fields the caller provides plus
    Rules() defaults" — useful for building a session from scratch in the UI
    without first saving a template.
    """
    if template_id is not None:
        tpl = db.session.get(SettingsTemplate, template_id)
        if not tpl:
            raise ValueError(f"template {template_id} not found")
        rules_dict = tpl.rules()
        sb_dict = tpl.side_bets()
    else:
        rules_dict = {}
        sb_dict = {}

    if rules_overrides:
        rules_dict = {**rules_dict, **rules_overrides}
    # Body-level player_seat lives outside `rules` for ergonomics, but Rules
    # validates it in __post_init__ — feed it in before construction.
    if player_seat is not None:
        rules_dict["player_seat"] = player_seat
    # If the caller shrinks seats below the default player_seat without setting
    # one explicitly, default to seat 1 so Rules() validation doesn't blow up.
    if "seats" in rules_dict and "player_seat" not in rules_dict:
        if rules_dict["seats"] < 3:
            rules_dict["player_seat"] = 1
    if side_bets_overrides:
        # Shallow merge per side-bet name.
        merged: dict[str, Any] = dict(sb_dict)
        for k, v in side_bets_overrides.items():
            merged[k] = {**(sb_dict.get(k, {})), **(v or {})}
        sb_dict = merged

    rules = rules_from_dict(rules_dict)
    side_bets = side_bets_from_dict(sb_dict)

    bankroll = starting_bankroll if starting_bankroll is not None else rules.starting_bankroll
    seat = player_seat if player_seat is not None else rules.player_seat
    if not 1 <= seat <= rules.seats:
        raise ValueError(f"player_seat {seat} not in 1..{rules.seats}")

    sess = GameSession(
        template_id=template_id,
        rules_json=json.dumps(rules.to_dict()),
        side_bets_json=json.dumps(side_bets.to_dict()),
        starting_bankroll=bankroll,
        bankroll=bankroll,
        last_results_json="[]",
        shoe_seed=seed if seed is not None else random.randint(0, 2**31 - 1),
        cards_dealt=0,
        running_count=0,
        counter_cards_seen=0,
        player_seat=seat,
        ai_seats_json=json.dumps(ai_seats or _default_ai_seats(rules, seat)),
    )
    db.session.add(sess)
    db.session.commit()
    return sess


def _default_ai_seats(rules: Rules, player_seat: int) -> list[dict]:
    """Sane default: every other seat plays book with a flat $10 bet."""
    seats = []
    for i in range(1, rules.seats + 1):
        if i == player_seat:
            continue
        seats.append({
            "seat_num": i,
            "playstyle": "book",
            "bet_pattern": "flat",
            "base_bet": rules.min_bet * 2,
            "bankroll": rules.starting_bankroll,
            "rebuy_on_bust": False,
        })
    return seats


# ---- shoe reconstruction ----------------------------------------------

def shoe_from_session(sess: GameSession) -> Shoe:
    """Rebuild the shoe at its current dealt position by re-seeding and
    burning the cards already dealt. Idempotent.
    """
    rules = rules_from_dict(json.loads(sess.rules_json))
    shoe = Shoe(
        decks=rules.decks,
        mode=rules.shuffle_mode,
        penetration=rules.penetration,
        seed=sess.shoe_seed,
    )
    if sess.cards_dealt and rules.shuffle_mode != ShuffleMode.CSM:
        # Burn forward to the recorded position. CSM doesn't accumulate dealt
        # so we'd just reshuffle in place; skip the no-op burn.
        for _ in range(sess.cards_dealt):
            shoe.next_card()
    return shoe


def reset_shoe(sess: GameSession, *, new_seed: Optional[int] = None) -> None:
    """Keep bankroll + stats; fresh shoe + counter."""
    sess.shoe_seed = new_seed if new_seed is not None else random.randint(0, 2**31 - 1)
    sess.cards_dealt = 0
    sess.running_count = 0
    sess.counter_cards_seen = 0
    sess.active_round_json = None
    db.session.commit()
