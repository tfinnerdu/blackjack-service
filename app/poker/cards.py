"""Poker card primitives. Re-uses the standard 52-card Card/Suit from the
shared engine module, adds Joker as a sibling type, and exposes a
PokerCard alias that's the union the rest of the poker code uses.

Joker is intentionally NOT a Card — it has no inherent rank or suit. Some
games treat it as fully wild; others (like the user's home game) only let
it complete straights or flushes, in which case the evaluator picks a
substitution that makes it useful, subject to the variant's wild rules.

Tokens:
  - 52 standard cards round-trip via card_from_token/card_to_token
  - Big joker: 'JK'
  - Little joker: 'jk'
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Union

from ..engine.cards import Card, Suit, card_from_token, card_to_token


@dataclass(frozen=True, slots=True)
class Joker:
    """A joker. `big=True` is the standard joker; `big=False` is the little
    joker used in some 54-card decks."""
    big: bool = True

    def __str__(self) -> str:
        return "JK" if self.big else "jk"


PokerCard = Union[Card, Joker]


def is_joker(card: PokerCard) -> bool:
    return isinstance(card, Joker)


def is_natural(card: PokerCard) -> bool:
    """A 'natural' card is a non-joker — used by some variants ('the next
    natural Q is wild')."""
    return not is_joker(card)


def poker_card_from_token(token: str) -> PokerCard:
    """Parse standard card tokens ('AS', '7H', 'TC'), plus 'JK' / 'jk' for
    jokers. Case-insensitive on standard cards; case-sensitive on jokers
    so the big/little distinction survives the round-trip."""
    if token == "JK":
        return Joker(big=True)
    if token == "jk":
        return Joker(big=False)
    return card_from_token(token)


def poker_card_to_token(card: PokerCard) -> str:
    if isinstance(card, Joker):
        return "JK" if card.big else "jk"
    return card_to_token(card)


def parse_cards(tokens: Iterable[str]) -> list[PokerCard]:
    return [poker_card_from_token(t) for t in tokens]


def stringify_cards(cards: Iterable[PokerCard]) -> list[str]:
    return [poker_card_to_token(c) for c in cards]


__all__ = [
    "Card",
    "Joker",
    "PokerCard",
    "Suit",
    "is_joker",
    "is_natural",
    "poker_card_from_token",
    "poker_card_to_token",
    "parse_cards",
    "stringify_cards",
]
