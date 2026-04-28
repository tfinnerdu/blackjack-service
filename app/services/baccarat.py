"""Baccarat session orchestration. Each `play_round` call:
  1. Validates bets against bankroll + rules
  2. Rebuilds the shoe at its current dealt position
  3. Deals one round
  4. Settles bets, persists state + history
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
from ..casino import create_session, record_round
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
    }
    return create_session(
        game_type="baccarat",
        starting_bankroll=starting_bankroll,
        rules=rules.to_dict(),
        state=state,
    )


def _rebuild_shoe(rules: BaccaratRules, state: dict) -> BaccaratShoe:
    """Reconstruct the shoe at its current state.

    `shuffles` tracks how many times the shoe has been re-permuted in
    this session. We have to replay that many shuffles before burning
    forward; otherwise a session that's crossed a reshuffle boundary
    would rewind to the initial permutation on every page reload.
    """
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


def play_round(sess: CasinoSession, bet_dicts: list[dict]) -> tuple[BaccaratRound, list[int]]:
    if sess.game_type != "baccarat":
        raise BaccaratError(f"session is {sess.game_type!r}, not baccarat")

    rules = BaccaratRules.from_dict(json.loads(sess.rules_json or "{}"))
    state = json.loads(sess.state_json or "{}")

    bets = [Bet.from_dict(d) for d in bet_dicts]
    if not bets:
        raise BaccaratError("at least one bet is required")
    total_stake = 0
    for b in bets:
        if b.stake <= 0:
            raise BaccaratError("bet stake must be > 0")
        if not (rules.min_bet <= b.stake <= rules.max_bet):
            raise BaccaratError(
                f"bet stake {b.stake} outside limits {rules.min_bet}..{rules.max_bet}"
            )
        total_stake += b.stake
    if total_stake > (sess.bankroll or 0):
        raise BaccaratError(
            f"insufficient bankroll: stake {total_stake} > bankroll {sess.bankroll}"
        )

    shoe = _rebuild_shoe(rules, state)
    cards_before = shoe._dealt
    rnd = deal_round(shoe)
    cards_consumed = shoe._dealt - cards_before
    payouts = settle_bets(rnd, bets, rules)
    profit = sum(payouts)

    state["cards_dealt"] = int(state.get("cards_dealt", 0)) + cards_consumed
    state["last_round"] = rnd.to_dict()
    sess.state_json = json.dumps(state)

    record_round(
        sess,
        profit=profit,
        summary={
            "label": "baccarat",
            "round": rnd.to_dict(),
            "bets": [b.to_dict() for b in bets],
            "payouts": list(payouts),
        },
    )
    return rnd, payouts
