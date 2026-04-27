"""Hi-Lo card counting + true-count math.

Hi-Lo values:
  2,3,4,5,6        = +1
  7,8,9            =  0
  T,J,Q,K,A        = -1

True count = running count / decks remaining (rounded down to nearest 0.5
for index-play comparisons; we keep the exact float and let consumers round).
"""
from __future__ import annotations

from ..engine.cards import Card


HI_LO_VALUES: dict[str, int] = {
    "2": 1, "3": 1, "4": 1, "5": 1, "6": 1,
    "7": 0, "8": 0, "9": 0,
    "T": -1, "J": -1, "Q": -1, "K": -1, "A": -1,
}


def hi_lo_value(rank: str) -> int:
    return HI_LO_VALUES[rank]


class Counter:
    """Tracks running count + cards seen so true count can be computed.

    Pass `decks` (the size of the shoe) at construction so we can derive
    'decks remaining' from cards seen.
    """

    def __init__(self, decks: int):
        if decks < 1:
            raise ValueError("decks must be >= 1")
        self.decks = decks
        self.running_count: int = 0
        self.cards_seen: int = 0

    def see(self, card: Card) -> None:
        self.running_count += hi_lo_value(card.rank)
        self.cards_seen += 1

    def see_many(self, cards) -> None:
        for c in cards:
            self.see(c)

    @property
    def cards_remaining(self) -> int:
        return max(0, self.decks * 52 - self.cards_seen)

    @property
    def decks_remaining(self) -> float:
        # Standard practice: round to nearest half-deck for true-count math.
        # We return the precise float; deviations apply >= thresholds so
        # rounding direction doesn't matter for them.
        return self.cards_remaining / 52.0

    @property
    def true_count(self) -> float:
        decks_left = self.decks_remaining
        if decks_left <= 0:
            return 0.0
        return self.running_count / decks_left

    def reset(self) -> None:
        self.running_count = 0
        self.cards_seen = 0

    def to_dict(self) -> dict:
        return {
            "running_count": self.running_count,
            "true_count": round(self.true_count, 2),
            "decks_remaining": round(self.decks_remaining, 2),
            "cards_seen": self.cards_seen,
        }
