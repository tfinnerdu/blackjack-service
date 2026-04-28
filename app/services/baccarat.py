"""Baccarat session orchestration. Punto Banco — every participant
bets on the same deal, all settle together. The shoe state is shared
across the table; per-participant bankrolls + bets live in the
`CasinoSession` guest book.
"""
from __future__ import annotations

import json
import random
from typing import Optional

from ..baccarat import (
    BaccaratRound,
    BaccaratRules,
    BaccaratShoe,
    Bet,
    BetType,
    deal_round,
    settle_bets,
)
from ..casino import (
    apply_round_to_participant,
    create_session,
    get_caller_bankroll,
    get_caller_bets,
    participants,
    set_caller_bets,
)
from ..models import CasinoSession


class BaccaratError(Exception):
    pass


def create_baccarat_session(
    *,
    starting_bankroll: int = 500,
    decks: int = 8,
    min_bet: int = 1,
    max_bet: int = 500,
    seed: Optional[int] = None,
) -> CasinoSession:
    rules = BaccaratRules(decks=decks, min_bet=min_bet, max_bet=max_bet)
    state = {
        "shoe_seed": seed if seed is not None else random.randint(0, 2**31 - 1),
        "cards_dealt": 0,
        "shuffles": 1,
        "last_round": None,
        "host_bets": [],
    }
    return create_session(
        game_type="baccarat",
        starting_bankroll=starting_bankroll,
        rules=rules.to_dict(),
        state=state,
    )


def _rebuild_shoe(rules: BaccaratRules, state: dict) -> BaccaratShoe:
    """Reconstruct the shoe at its current state. The `shuffles`
    counter ensures we land on the right permutation after a mid-shoe
    reshuffle (same fix as blackjack's shoe-replay bug)."""
    shoe = BaccaratShoe(
        decks=rules.decks,
        penetration=rules.penetration,
        seed=int(state.get("shoe_seed", 0)),
    )
    needed_shuffles = max(1, int(state.get("shuffles", 1)))
    for _ in range(needed_shuffles - 1):
        shoe.shuffle()
    burn = int(state.get("cards_dealt", 0))
    if shoe.needs_reshuffle:
        shoe.shuffle()
        state["shuffles"] = needed_shuffles + 1
        state["cards_dealt"] = 0
        return shoe
    for _ in range(burn):
        shoe.next_card()
    return shoe


def stage_bets(sess: CasinoSession, token: str, bet_dicts: list[dict]) -> list[dict]:
    if sess.game_type != "baccarat":
        raise BaccaratError(f"session is {sess.game_type!r}, not baccarat")
    rules = BaccaratRules.from_dict(json.loads(sess.rules_json or "{}"))
    bets = [Bet.from_dict(d) for d in bet_dicts]
    total = 0
    for b in bets:
        if b.stake <= 0:
            raise BaccaratError("bet stake must be > 0")
        if not (rules.min_bet <= b.stake <= rules.max_bet):
            raise BaccaratError(
                f"bet stake {b.stake} outside limits {rules.min_bet}..{rules.max_bet}"
            )
        total += b.stake
    bankroll = get_caller_bankroll(sess, token)
    if total > bankroll:
        raise BaccaratError(
            f"insufficient bankroll: stake {total} > bankroll {bankroll}"
        )
    set_caller_bets(sess, token, [b.to_dict() for b in bets])
    return get_caller_bets(sess, token)


def play_round(sess: CasinoSession) -> dict:
    """Deal one round and settle every participant's pending bets
    against the result. Host triggers; route layer enforces that."""
    if sess.game_type != "baccarat":
        raise BaccaratError(f"session is {sess.game_type!r}, not baccarat")
    rules = BaccaratRules.from_dict(json.loads(sess.rules_json or "{}"))
    state = json.loads(sess.state_json or "{}")

    shoe = _rebuild_shoe(rules, state)
    cards_before = shoe._dealt
    rnd = deal_round(shoe)
    cards_consumed = shoe._dealt - cards_before

    per_part: list[dict] = []
    has_any_bets = False
    for token, entry, is_host in participants(sess):
        token_to_use = sess.token if (is_host and token is None) else token
        pending = entry.get("current_bets", [])
        if not pending:
            continue
        has_any_bets = True
        bets = [Bet.from_dict(b) for b in pending]
        payouts = settle_bets(rnd, bets, rules)
        profit = sum(payouts)
        apply_round_to_participant(
            sess,
            None if is_host else token_to_use,
            profit=profit,
            summary={
                "label": entry.get("label", "host" if is_host else "guest"),
                "round": rnd.to_dict(),
                "bets": [b.to_dict() for b in bets],
                "payouts": list(payouts),
            },
        )
        # Clear their staged bets. Host's bets live in the local
        # `state` dict (written back below); guests live in
        # guest_tokens_json so use the helper.
        if is_host:
            state["host_bets"] = []
        else:
            set_caller_bets(sess, token_to_use, [])
        guests_now = json.loads(sess.guest_tokens_json or "{}")
        per_part.append({
            "label": entry.get("label", "host" if is_host else "guest"),
            "is_host": is_host,
            "payouts": list(payouts),
            "total_profit": profit,
            "bankroll_after": (
                int(sess.bankroll or 0) if is_host
                else int(guests_now.get(token_to_use, {}).get("bankroll", 0))
            ),
        })

    if not has_any_bets:
        raise BaccaratError(
            "no pending bets — stage some via /sessions/me/bets first"
        )

    state["cards_dealt"] = int(state.get("cards_dealt", 0)) + cards_consumed
    state["last_round"] = rnd.to_dict()
    sess.state_json = json.dumps(state)
    from ..db import db
    db.session.commit()

    return {"round": rnd.to_dict(), "participants": per_part}
