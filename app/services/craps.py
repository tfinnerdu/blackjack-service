"""Craps session orchestration. Bets sit on the table across rolls;
the service tracks the bet book, the table phase, and the dice rng.

A round in craps is a sequence of rolls until enough resolve. We let
the caller drive roll-by-roll: client posts a roll, server resolves,
returns updated state. Add/remove bets between rolls is allowed
when the table allows it (we don't block — clients should follow the
casino conventions on that).
"""
from __future__ import annotations

import json
import random
import secrets
from typing import Optional

from ..casino import create_session, record_round
from ..craps import (
    Bet,
    BetType,
    CrapsRules,
    CrapsTable,
    Phase,
    Roll,
    RollResult,
    resolve_roll,
)
from ..models import CasinoSession


class CrapsError(Exception):
    pass


def create_craps_session(
    *,
    starting_bankroll: int = 500,
    min_bet: int = 1,
    max_bet: int = 500,
    seed: Optional[int] = None,
) -> CasinoSession:
    rules = CrapsRules(min_bet=min_bet, max_bet=max_bet)
    state = {
        "rng_seed": seed if seed is not None else random.randint(0, 2**31 - 1),
        "rolls": 0,
        "table": CrapsTable().to_dict(),
        "bets": [],          # list of Bet.to_dict()
        "last_roll": None,
    }
    return create_session(
        game_type="craps",
        starting_bankroll=starting_bankroll,
        rules=rules.to_dict(),
        state=state,
    )


def _state(sess: CasinoSession) -> dict:
    return json.loads(sess.state_json or "{}")


def _save_state(sess: CasinoSession, st: dict) -> None:
    sess.state_json = json.dumps(st)


def _bets_from_state(st: dict) -> list[Bet]:
    return [Bet.from_dict(b) for b in st.get("bets", [])]


def _table_from_state(st: dict) -> CrapsTable:
    return CrapsTable.from_dict(st.get("table") or {})


def add_bets(sess: CasinoSession, bet_dicts: list[dict]) -> dict:
    """Append new bets to the book (with auto-generated ids if absent).
    Stake is deducted lazily — only at resolution does bankroll move,
    so a bet sitting on the table doesn't lock funds in the same way
    the blackjack engine does. This matches casino feel.
    """
    if sess.game_type != "craps":
        raise CrapsError(f"session is {sess.game_type!r}, not craps")
    rules = CrapsRules.from_dict(json.loads(sess.rules_json or "{}"))
    st = _state(sess)
    bets = st.get("bets", [])

    pending_total = sum(int(b.get("stake", 0)) for b in bet_dicts)
    on_table = sum(int(b.get("stake", 0)) for b in bets)
    if pending_total + on_table > (sess.bankroll or 0):
        raise CrapsError(
            f"insufficient bankroll: {pending_total} new + {on_table} on table "
            f"> {sess.bankroll}"
        )

    for d in bet_dicts:
        stake = int(d.get("stake", 0))
        if stake <= 0:
            raise CrapsError("stake must be > 0")
        if not (rules.min_bet <= stake <= rules.max_bet):
            raise CrapsError(
                f"stake {stake} outside limits {rules.min_bet}..{rules.max_bet}"
            )
        if "bet_id" not in d:
            d = {**d, "bet_id": secrets.token_hex(4)}
        # Validate bet shape by round-tripping.
        b = Bet.from_dict(d)
        bets.append(b.to_dict())

    st["bets"] = bets
    _save_state(sess, st)
    return st


def cancel_bet(sess: CasinoSession, bet_id: str) -> dict:
    """Remove a bet that hasn't resolved yet. Casino rules vary on
    which bets are 'contract' (can't be removed once a point is on);
    we don't enforce that here — callers should know what they're
    doing."""
    if sess.game_type != "craps":
        raise CrapsError(f"session is {sess.game_type!r}, not craps")
    st = _state(sess)
    st["bets"] = [b for b in st.get("bets", []) if b.get("bet_id") != bet_id]
    _save_state(sess, st)
    return st


def roll(sess: CasinoSession, dice: Optional[tuple[int, int]] = None) -> RollResult:
    """Advance one roll. If `dice` is provided (e.g. for a
    deterministic test), uses it; otherwise rolls fresh dice from
    the session's seeded RNG."""
    if sess.game_type != "craps":
        raise CrapsError(f"session is {sess.game_type!r}, not craps")
    rules = CrapsRules.from_dict(json.loads(sess.rules_json or "{}"))
    st = _state(sess)

    rolls_so_far = int(st.get("rolls", 0))
    base_seed = int(st.get("rng_seed", 0))
    rng = random.Random(base_seed + rolls_so_far)
    if dice is None:
        d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
    else:
        d1, d2 = dice
    roll_obj = Roll(d1, d2)

    table = _table_from_state(st)
    bets = _bets_from_state(st)
    result = resolve_roll(table, roll_obj, bets, rules)

    # Drop resolved bets from the book; keep the rest (with possibly
    # updated established_point on COME bets).
    resolved_ids = {o.bet_id for o in result.outcomes if o.resolved}
    surviving = [b for b in bets if b.bet_id not in resolved_ids]

    profit = sum(o.profit for o in result.outcomes)
    st["rolls"] = rolls_so_far + 1
    st["bets"] = [b.to_dict() for b in surviving]
    st["table"] = table.to_dict()
    st["last_roll"] = result.to_dict()
    _save_state(sess, st)

    record_round(
        sess,
        profit=profit,
        summary={
            "label": "craps",
            "roll": roll_obj.to_dict(),
            "phase_after": table.phase.value,
            "point_after": table.point,
            "outcomes": [o.to_dict() for o in result.outcomes],
        },
    )
    return result
