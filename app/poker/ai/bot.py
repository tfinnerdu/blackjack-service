"""AIBot binds a name + personality + last-results history into one object
the round driver can call to get the next action."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

from ..cards import Card
from ..pot import BetAction
from .personalities import Decision, Move, get_personality


@dataclass
class AIBot:
    seat_num: int
    name: str
    personality: str = "book"
    drunk_mistake_rate: float = 0.30
    seed: Optional[int] = None

    last_results: list[int] = field(default_factory=list)
    rng: random.Random = field(default=None, repr=False)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.rng is None:
            self.rng = random.Random(self.seed)

    def decide(
        self,
        *,
        hole: list[Card],
        community: list[Card],
        pot_size: int,
        to_call: int,
        min_raise_to: int,
        big_blind: int,
        stack: int,
        legal_actions: list[BetAction],
        is_pre_flop: bool,
    ) -> Move:
        d = Decision(
            hole=hole, community=community, pot_size=pot_size, to_call=to_call,
            min_raise_to=min_raise_to, big_blind=big_blind, stack=stack,
            legal_actions=legal_actions, is_pre_flop=is_pre_flop,
            last_results=list(self.last_results), rng=self.rng,
        )
        fn = get_personality(self.personality)
        if self.personality == "drunk":
            return fn(d, self.drunk_mistake_rate)  # type: ignore[call-arg]
        return fn(d)

    def record_result(self, profit: int) -> None:
        self.last_results.append(profit)
        if len(self.last_results) > 20:
            self.last_results = self.last_results[-20:]

    def to_dict(self) -> dict:
        return {
            "seat_num": self.seat_num,
            "name": self.name,
            "personality": self.personality,
            "drunk_mistake_rate": self.drunk_mistake_rate,
            "seed": self.seed,
            "last_results": list(self.last_results),
        }
