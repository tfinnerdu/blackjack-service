"""Roulette session orchestration. Each spin settles all participants
(host + every guest) against the *same* wheel result — the casino-floor
experience where every bettor watches the same ball drop.

Endpoint flow:
  /sessions/me/bets  → caller stages their pending bets
  /sessions/me/spin  → host triggers the wheel; every participant's
                       pending bets resolve and their bankroll updates
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Optional

from ..casino import (
    apply_round_to_participant,
    create_session,
    get_caller_bankroll,
    get_caller_bets,
    participants,
    set_caller_bets,
)
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
    pass


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
        "host_bets": [],
    }
    return create_session(
        game_type="roulette",
        starting_bankroll=starting_bankroll,
        rules=rules.to_dict(),
        state=state,
    )


def stage_bets(sess: CasinoSession, token: str, bet_dicts: list[dict]) -> list[dict]:
    """Validate + persist a participant's pending bets. Replaces any
    previous staging — clients submit the full intended slate. Total
    stake must fit in the caller's bankroll right now (so two
    participants can't both 'all-in' the same dollars by accident)."""
    if sess.game_type != "roulette":
        raise RouletteError(f"session is {sess.game_type!r}, not roulette")

    rules = RouletteRules.from_dict(json.loads(sess.rules_json or "{}"))
    bets = [Bet.from_dict(d) for d in bet_dicts]
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

    bankroll = get_caller_bankroll(sess, token)
    if total_stake > bankroll:
        raise RouletteError(
            f"insufficient bankroll: stake {total_stake} > bankroll {bankroll}"
        )

    set_caller_bets(sess, token, [b.to_dict() for b in bets])
    return get_caller_bets(sess, token)


def spin(sess: CasinoSession) -> dict:
    """Spin the wheel once. Settles host + every guest's pending bets
    against the result and returns a per-participant breakdown.

    Caller is expected to be the host; route layer enforces that.
    """
    if sess.game_type != "roulette":
        raise RouletteError(f"session is {sess.game_type!r}, not roulette")

    rules = RouletteRules.from_dict(json.loads(sess.rules_json or "{}"))
    state = json.loads(sess.state_json or "{}")

    spin_index = int(state.get("spin_index", 0))
    base_seed = int(state.get("wheel_seed", 0))
    wheel = Wheel(rules.wheel_kind, seed=base_seed + spin_index)
    spin_result_obj: Spin = wheel.spin()

    per_part: list[dict] = []
    has_any_bets = False
    for token, entry, is_host in participants(sess):
        token_to_use = sess.token if (is_host and token is None) else token
        pending = entry.get("current_bets", [])
        if not pending:
            continue
        has_any_bets = True
        bets = [Bet.from_dict(b) for b in pending]
        result = settle_bets(spin_result_obj, bets)
        apply_round_to_participant(
            sess,
            None if is_host else token_to_use,
            profit=result.total_profit,
            summary={
                "label": entry.get("label", "host" if is_host else "guest"),
                "spin": spin_result_obj.to_dict(),
                "bets": [b.to_dict() for b in bets],
                "payouts": list(result.payouts),
            },
        )
        # Clear their staged bets after settling. Host clears live in
        # the local `state` dict (we'll write it back below in one go);
        # guests are stored separately in guest_tokens_json so we use
        # the helper.
        if is_host:
            state["host_bets"] = []
        else:
            set_caller_bets(sess, token_to_use, [])
        per_part.append({
            "label": entry.get("label", "host" if is_host else "guest"),
            "is_host": is_host,
            "payouts": list(result.payouts),
            "total_profit": result.total_profit,
            "bankroll_after": (
                int(sess.bankroll or 0) if is_host
                else (
                    (json.loads(sess.guest_tokens_json or "{}")
                     .get(token_to_use, {})).get("bankroll", 0)
                )
            ),
        })

    if not has_any_bets:
        raise RouletteError("no pending bets — stage some via /sessions/me/bets first")

    state["spin_index"] = spin_index + 1
    state["last_spin"] = spin_result_obj.to_dict()
    sess.state_json = json.dumps(state)
    from ..db import db
    db.session.commit()

    return {
        "spin": spin_result_obj.to_dict(),
        "participants": per_part,
    }
