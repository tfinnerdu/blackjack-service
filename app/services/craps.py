"""Craps session orchestration. Bets sit on the table across rolls;
each participant has their own book inside the casino session. The
host triggers each roll; every participant's book resolves
simultaneously.
"""
from __future__ import annotations

import json
import random
import secrets
from typing import Optional

from ..casino import (
    apply_round_to_participant,
    create_session,
    get_caller_bankroll,
    get_caller_bets,
    participants,
    set_caller_bets,
)
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
        "host_bets": [],     # host's book; each guest has their own
        "last_roll": None,
    }
    return create_session(
        game_type="craps",
        starting_bankroll=starting_bankroll,
        rules=rules.to_dict(),
        state=state,
    )


# ---- bet book helpers (per participant) ------------------------------

def add_bets(
    sess: CasinoSession,
    token: str,
    bet_dicts: list[dict],
) -> list[dict]:
    """Append new bets to the caller's book. Each gets an auto-id if
    missing. Total exposure (existing + new) must fit in the caller's
    bankroll."""
    if sess.game_type != "craps":
        raise CrapsError(f"session is {sess.game_type!r}, not craps")
    rules = CrapsRules.from_dict(json.loads(sess.rules_json or "{}"))

    existing = list(get_caller_bets(sess, token))
    on_table = sum(int(b.get("stake", 0)) for b in existing)
    pending = sum(int(b.get("stake", 0)) for b in bet_dicts)
    bankroll = get_caller_bankroll(sess, token)
    if pending + on_table > bankroll:
        raise CrapsError(
            f"insufficient bankroll: {pending} new + {on_table} on table "
            f"> {bankroll}"
        )

    new_book: list[dict] = list(existing)
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
        # Validate bet shape by round-tripping through the engine type.
        b = Bet.from_dict(d)
        new_book.append(b.to_dict())

    set_caller_bets(sess, token, new_book)
    return get_caller_bets(sess, token)


def cancel_bet(sess: CasinoSession, token: str, bet_id: str) -> list[dict]:
    """Remove one bet from the caller's book."""
    if sess.game_type != "craps":
        raise CrapsError(f"session is {sess.game_type!r}, not craps")
    book = list(get_caller_bets(sess, token))
    book = [b for b in book if b.get("bet_id") != bet_id]
    set_caller_bets(sess, token, book)
    return book


# ---- roll ------------------------------------------------------------

def roll(sess: CasinoSession, dice: Optional[tuple[int, int]] = None) -> dict:
    """Advance one roll. Resolves every participant's book against
    the same dice. Caller is expected to be the host."""
    if sess.game_type != "craps":
        raise CrapsError(f"session is {sess.game_type!r}, not craps")
    rules = CrapsRules.from_dict(json.loads(sess.rules_json or "{}"))
    state = json.loads(sess.state_json or "{}")

    rolls_so_far = int(state.get("rolls", 0))
    base_seed = int(state.get("rng_seed", 0))
    rng = random.Random(base_seed + rolls_so_far)
    if dice is None:
        d1, d2 = rng.randint(1, 6), rng.randint(1, 6)
    else:
        d1, d2 = dice
    roll_obj = Roll(d1, d2)

    # The table state is shared (one phase / point per room).
    table = CrapsTable.from_dict(state.get("table") or {})

    per_part: list[dict] = []
    for token, entry, is_host in participants(sess):
        token_to_use = sess.token if (is_host and token is None) else token
        book_dicts = list(entry.get("current_bets", []))
        if not book_dicts:
            continue
        bets = [Bet.from_dict(b) for b in book_dicts]
        # NB: every participant resolves against the SAME table snapshot,
        # not a per-participant clone. That's correct — the wheel/table
        # state is shared, and bets resolve identically against the
        # same roll. We pass a temporary table copy because resolve_roll
        # mutates `table` (advances phase/point); we want to advance it
        # exactly once, so use a per-participant clone for resolution
        # and the shared `table` for the final phase mutation.
        clone = CrapsTable.from_dict(table.to_dict())
        result = resolve_roll(clone, roll_obj, bets, rules)

        # Drop resolved bets from the participant's book; keep
        # surviving ones (with possibly-updated established_point on
        # COME bets). Host book lives in the local `state` dict —
        # guests in guest_tokens_json.
        resolved_ids = {o.bet_id for o in result.outcomes if o.resolved}
        surviving = [b for b in bets if b.bet_id not in resolved_ids]
        surviving_dicts = [b.to_dict() for b in surviving]
        if is_host:
            state["host_bets"] = surviving_dicts
        else:
            set_caller_bets(sess, token_to_use, surviving_dicts)

        profit = sum(o.profit for o in result.outcomes)
        apply_round_to_participant(
            sess,
            None if is_host else token_to_use,
            profit=profit,
            summary={
                "label": entry.get("label", "host" if is_host else "guest"),
                "roll": roll_obj.to_dict(),
                "outcomes": [o.to_dict() for o in result.outcomes],
            },
        )

        guests_now = json.loads(sess.guest_tokens_json or "{}")
        per_part.append({
            "label": entry.get("label", "host" if is_host else "guest"),
            "is_host": is_host,
            "outcomes": [o.to_dict() for o in result.outcomes],
            "total_profit": profit,
            "bankroll_after": (
                int(sess.bankroll or 0) if is_host
                else int(guests_now.get(token_to_use, {}).get("bankroll", 0))
            ),
        })

    # Advance the shared table state once. Re-call resolve_roll on
    # an empty book just to mutate the phase machine identically.
    resolve_roll(table, roll_obj, [], rules)

    state["rolls"] = rolls_so_far + 1
    state["table"] = table.to_dict()
    state["last_roll"] = {
        "roll": roll_obj.to_dict(),
        "phase_after": table.phase.value,
        "point_after": table.point,
    }
    sess.state_json = json.dumps(state)
    from ..db import db
    db.session.commit()

    return {
        "roll": roll_obj.to_dict(),
        "phase_after": table.phase.value,
        "point_after": table.point,
        "participants": per_part,
    }
