"""AI seat config + driver. Bundles a playstyle + bet pattern + bankroll
state and exposes the two methods the round orchestrator needs:
`pick_bet(...)` (round start) and `pick_action(...)` (each player turn).

A bust-out seat returns 0 from pick_bet and the orchestrator drops them.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

from ..engine.cards import Card
from ..engine.hand import Hand
from ..engine.rules import Rules
from ..strategy import BookAction, Capabilities
from .bet_patterns import get_bet_pattern
from .playstyles import get_playstyle


@dataclass
class AISeat:
    seat_num: int
    playstyle: str = "book"
    bet_pattern: str = "flat"
    base_bet: int = 10
    bankroll: int = 200
    rebuy_on_bust: bool = False
    rebuy_amount: int = 200
    drunk_mistake_rate: float = 0.20
    seed: Optional[int] = None

    last_results: list[int] = field(default_factory=list)
    rng: random.Random = field(default=None, repr=False)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.rng is None:
            self.rng = random.Random(self.seed)

    @property
    def is_bust(self) -> bool:
        return self.bankroll < 1

    def pick_bet(self, rules: Rules, true_count: Optional[float] = None) -> int:
        """Decide a stake for the next round. 0 means 'sit out / left the table'."""
        if self.is_bust:
            if self.rebuy_on_bust:
                self.bankroll = self.rebuy_amount
            else:
                return 0
        if self.bankroll < rules.min_bet:
            return 0
        fn = get_bet_pattern(self.bet_pattern)
        return fn(self.bankroll, self.base_bet, self.last_results, rules, true_count, self.rng)

    def pick_action(
        self,
        hand: Hand,
        dealer_up: Card,
        rules: Rules,
        caps: Capabilities,
        true_count: Optional[float] = None,
    ) -> BookAction:
        """Pick a single action for the active hand. Filtered against caps
        by the orchestrator if needed."""
        fn = get_playstyle(self.playstyle)
        # Drunk takes its own param; everything else uses the same signature.
        if self.playstyle == "drunk":
            return fn(hand, dealer_up, rules, caps, true_count, self.rng,
                      self.drunk_mistake_rate)  # type: ignore[call-arg]
        return fn(hand, dealer_up, rules, caps, true_count, self.rng)

    def record_result(self, profit: int) -> None:
        self.bankroll += profit
        self.last_results.append(profit)
        # Cap history length so streak-aware patterns don't carry ancient data.
        if len(self.last_results) > 50:
            self.last_results = self.last_results[-50:]

    def to_dict(self) -> dict:
        return {
            "seat_num": self.seat_num,
            "playstyle": self.playstyle,
            "bet_pattern": self.bet_pattern,
            "base_bet": self.base_bet,
            "bankroll": self.bankroll,
            "rebuy_on_bust": self.rebuy_on_bust,
            "rebuy_amount": self.rebuy_amount,
            "drunk_mistake_rate": self.drunk_mistake_rate,
            "seed": self.seed,
            "is_bust": self.is_bust,
        }
