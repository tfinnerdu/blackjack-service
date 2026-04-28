"""Pot + betting model.

A poker table tracks per-player committed-this-round chips, a running pot,
and any side pots created when someone is all-in for less than others have
committed. The Pot class owns enough state that the round/state-machine
layer can ask 'who's still to act?' and 'what does it cost to call?' without
re-derivation.

We model chips as integers. No fractional chips, no separate small-blind /
big-blind tables — those are config inputs to the round, not pot state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class BetAction(str, Enum):
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"
    RAISE = "raise"
    ALL_IN = "all_in"


@dataclass
class Player:
    """A seat at the simulator table. Stack is the live chip count.

    `committed_this_round` is reset between betting streets; `committed_total`
    is what's already gone to the pot across the whole hand (used when
    building side pots at showdown).
    """
    seat_num: int
    name: str
    stack: int
    is_human: bool = False
    folded: bool = False
    all_in: bool = False
    committed_this_round: int = 0
    committed_total: int = 0
    has_acted_this_round: bool = False

    @property
    def in_hand(self) -> bool:
        return not self.folded

    def reset_for_new_round(self) -> None:
        self.committed_this_round = 0
        self.has_acted_this_round = False

    def reset_for_new_hand(self) -> None:
        self.folded = False
        self.all_in = False
        self.committed_this_round = 0
        self.committed_total = 0
        self.has_acted_this_round = False


@dataclass
class SidePot:
    """One layer of the pot at showdown. amount = chips locked in this layer;
    eligible_seats = seats that can win it."""
    amount: int
    eligible_seats: list[int] = field(default_factory=list)


class Pot:
    """Running pot for the current hand. Updated as each street's bets close.

    At showdown, `build_side_pots()` returns a layered list ordered from
    smallest-buy-in to largest, so the showdown logic can settle each layer
    among its eligible players.
    """

    def __init__(self):
        self.committed: dict[int, int] = {}   # seat_num -> total committed across the hand
        self.current_street_total: int = 0    # informational: chips in this street
        self.total: int = 0                    # informational: chips already swept in

    def commit(self, player: Player, amount: int) -> None:
        if amount < 0:
            raise ValueError("commit amount must be >= 0")
        if amount > player.stack:
            raise ValueError("can't commit more than stack")
        player.stack -= amount
        player.committed_this_round += amount
        player.committed_total += amount
        if player.stack == 0:
            player.all_in = True
        self.committed[player.seat_num] = player.committed_total
        self.current_street_total += amount
        self.total += amount

    def close_street(self) -> None:
        self.current_street_total = 0

    def amount_to_call(self, player: Player, current_bet: int) -> int:
        """Cost for `player` to match the current_bet for the street."""
        return max(0, current_bet - player.committed_this_round)

    def build_side_pots(self, players: list[Player]) -> list[SidePot]:
        """Slice the running pot into layers. Each layer's amount is
        contributions up to that layer's cap; eligible seats are the ones
        who put in at least that cap."""
        active = [p for p in players if p.committed_total > 0]
        contributions = sorted({p.committed_total for p in active})
        layers: list[SidePot] = []
        prev_cap = 0
        for cap in contributions:
            layer_amount = 0
            eligible: list[int] = []
            for p in active:
                if p.committed_total >= cap:
                    layer_amount += cap - prev_cap
                    if not p.folded:
                        eligible.append(p.seat_num)
            if layer_amount > 0:
                layers.append(SidePot(amount=layer_amount, eligible_seats=eligible))
            prev_cap = cap
        return layers


# ---- pure validators / helpers ----------------------------------------

def legal_actions(
    player: Player,
    current_bet: int,
    last_raise: int,
    min_bet: int,
) -> list[BetAction]:
    """What actions `player` can take given the street's current_bet and
    last_raise size. last_raise governs minimum raise sizing.
    """
    if player.folded or player.all_in:
        return []
    actions: list[BetAction] = [BetAction.FOLD]
    needs_to_call = max(0, current_bet - player.committed_this_round)
    if needs_to_call == 0:
        actions.append(BetAction.CHECK)
        if player.stack > 0:
            actions.append(BetAction.BET)
    else:
        # Call or raise (if they can afford a min-raise).
        if player.stack > 0:
            actions.append(BetAction.CALL)
        if player.stack > needs_to_call:
            actions.append(BetAction.RAISE)
    if player.stack > 0:
        actions.append(BetAction.ALL_IN)
    return actions


def min_raise_to(current_bet: int, last_raise: int, min_bet: int) -> int:
    """Smallest legal total bet for a raise. last_raise is the size of the
    most recent raise; the next raise must be at least that much again."""
    return max(current_bet + last_raise, current_bet + min_bet)


__all__ = [
    "BetAction",
    "Player",
    "SidePot",
    "Pot",
    "legal_actions",
    "min_raise_to",
]
