"""Roulette session orchestration: create-session, place-bets, spin, settle.

Wheel state is rebuilt from `state_json` on each spin so we don't have
to keep a Wheel instance in memory between requests.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Optional

from ..casino import create_session, record_round
from ..models import CasinoSession
from ..roulette import (
    Bet,
    BetType,
    Spin,
    SpinResult,
    Wheel,
    WheelKind,
    settle_bets,
)


class RouletteError(Exception):
    """Caller-visible problem (bad bet, insufficient bankroll, etc.)."""


@dataclass
class RouletteRules:
    wheel_kind: WheelKind = WheelKind.AMERICAN
    min_bet: int = 1
    max_bet: int = 500

    def to_dict(self) -> dict:
        return {
            "wheel_kind": self.wheel_kind.value,
            "min_bet": self.min_bet,
            "max_bet": self.max_bet,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RouletteRules":
        return cls(
            wheel_kind=WheelKind(d.get("wheel_kind", "american")),
            min_bet=int(d.get("min_bet", 1)),
            max_bet=int(d.get("max_bet", 500)),
        )


def create_roulette_session(
    *,
    starting_bankroll: int = 500,
    wheel_kind: WheelKind = WheelKind.AMERICAN,
    min_bet: int = 1,
    max_bet: int = 500,
    seed: Optional[int] = None,
) -> CasinoSession:
    rules = RouletteRules(wheel_kind=wheel_kind, min_bet=min_bet, max_bet=max_bet)
    state = {
        "wheel_seed": seed if seed is not None else random.randint(0, 2**31 - 1),
        "spin_index": 0,
        "last_spin": None,
    }
    return create_session(
        game_type="roulette",
        starting_bankroll=starting_bankroll,
        rules=rules.to_dict(),
        state=state,
    )


def spin(sess: CasinoSession, bet_dicts: list[dict]) -> SpinResult:
    """Place bets and spin once. Bankroll is checked before the spin;
    payouts apply after. The wheel is reseeded each spin (state-derived)
    so a session can be deterministically replayed."""
    if sess.game_type != "roulette":
        raise RouletteError(f"session is {sess.game_type!r}, not roulette")

    rules = RouletteRules.from_dict(json.loads(sess.rules_json or "{}"))
    state = json.loads(sess.state_json or "{}")

    bets = [Bet.from_dict(d) for d in bet_dicts]
    if not bets:
        raise RouletteError("at least one bet is required")

    total_stake = 0
    for b in bets:
        if b.stake <= 0:
            raise RouletteError("bet stake must be > 0")
        if not (rules.min_bet <= b.stake <= rules.max_bet):
            raise RouletteError(
                f"bet {b.bet_type.value} stake {b.stake} outside "
                f"limits {rules.min_bet}..{rules.max_bet}"
            )
        total_stake += b.stake

    if total_stake > (sess.bankroll or 0):
        raise RouletteError(
            f"insufficient bankroll: stake {total_stake} > bankroll {sess.bankroll}"
        )

    # Spin-derived seed: deterministic replay with no extra DB columns.
    spin_index = int(state.get("spin_index", 0))
    base_seed = int(state.get("wheel_seed", 0))
    wheel = Wheel(rules.wheel_kind, seed=base_seed + spin_index)
    spin_result_obj: Spin = wheel.spin()

    result = settle_bets(spin_result_obj, bets)

    # Persist + bookkeep.
    state["spin_index"] = spin_index + 1
    state["last_spin"] = spin_result_obj.to_dict()
    sess.state_json = json.dumps(state)

    record_round(
        sess,
        profit=result.total_profit,
        summary={
            "label": "roulette",
            "spin": spin_result_obj.to_dict(),
            "bets": [b.to_dict() for b in bets],
            "payouts": list(result.payouts),
        },
    )
    return result
