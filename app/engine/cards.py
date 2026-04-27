"""Card primitives. Kept tiny and immutable so the rest of the engine can
treat them as plain values.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class Suit(str, Enum):
    SPADES = "S"
    HEARTS = "H"
    DIAMONDS = "D"
    CLUBS = "C"


class Color(str, Enum):
    RED = "red"
    BLACK = "black"


SUIT_COLOR = {
    Suit.HEARTS: Color.RED,
    Suit.DIAMONDS: Color.RED,
    Suit.SPADES: Color.BLACK,
    Suit.CLUBS: Color.BLACK,
}


# Rank symbols. "T" for ten keeps tokens single-character which simplifies
# strategy lookups; UI renders "10".
RANKS: tuple[str, ...] = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K")
RANK_INDEX: dict[str, int] = {r: i for i, r in enumerate(RANKS)}


def rank_value(rank: str) -> int:
    """Hard value of a rank. Aces return 1; soft handling is computed on the hand."""
    if rank == "A":
        return 1
    if rank in ("T", "J", "Q", "K"):
        return 10
    return int(rank)


def is_ten(rank: str) -> bool:
    return rank in ("T", "J", "Q", "K")


@dataclass(frozen=True, slots=True)
class Card:
    rank: str
    suit: Suit

    def __post_init__(self) -> None:
        if self.rank not in RANK_INDEX:
            raise ValueError(f"invalid rank: {self.rank!r}")

    @property
    def value(self) -> int:
        return rank_value(self.rank)

    @property
    def color(self) -> Color:
        return SUIT_COLOR[self.suit]

    def __str__(self) -> str:
        return f"{self.rank}{self.suit.value}"

    def to_dict(self) -> dict:
        return {"rank": self.rank, "suit": self.suit.value}


def hand_total(cards: Iterable[Card]) -> tuple[int, bool]:
    """Return (best total, is_soft).

    Soft means at least one ace is currently counted as 11. We start with
    every ace as 11 and demote one at a time until we're at or under 21.
    """
    cards = list(cards)
    total = sum(c.value for c in cards)
    aces = sum(1 for c in cards if c.rank == "A")
    # Each ace originally counted as 1; promote one to 11 (+10) while it fits.
    soft_aces = 0
    while aces > 0 and total + 10 <= 21:
        total += 10
        aces -= 1
        soft_aces += 1
    return total, soft_aces > 0


def is_blackjack(cards: Iterable[Card]) -> bool:
    """A natural 21 on the initial deal: exactly 2 cards totaling 21."""
    cards = list(cards)
    if len(cards) != 2:
        return False
    total, _ = hand_total(cards)
    return total == 21
