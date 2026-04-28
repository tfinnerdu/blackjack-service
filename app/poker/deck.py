"""Poker deck construction + shuffling.

Supports:
  - Standard 52-card decks (1 or more)
  - 53-card deck (52 + 1 big joker) — the user's home-game default
  - 54-card deck (52 + big + little joker)
  - Any combination via DeckSpec
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

from ..engine.cards import RANKS, Suit
from .cards import Card, Joker, PokerCard


@dataclass
class DeckSpec:
    """Composition of a poker deck.

    decks=1 + jokers=0 -> standard 52
    decks=1 + jokers=1 -> 53 (one big joker; the home-game default)
    decks=1 + jokers=2 -> 54 (big + little)
    """
    decks: int = 1
    jokers: int = 0  # 0, 1 (big), or 2 (big + little)
    little_joker: bool = True  # only consulted when jokers >= 2

    def __post_init__(self) -> None:
        if self.decks < 1:
            raise ValueError("decks must be >= 1")
        if self.jokers not in (0, 1, 2):
            raise ValueError("jokers must be 0, 1, or 2")

    @property
    def total_cards(self) -> int:
        return self.decks * 52 + self.jokers


def build_deck(spec: DeckSpec) -> list[PokerCard]:
    cards: list[PokerCard] = []
    for _ in range(spec.decks):
        for suit in Suit:
            for rank in RANKS:
                cards.append(Card(rank, suit))
    if spec.jokers >= 1:
        cards.append(Joker(big=True))
    if spec.jokers >= 2:
        cards.append(Joker(big=False))
    return cards


class PokerShoe:
    """Deal source for a poker session. Unlike the blackjack shoe, poker
    typically reshuffles every hand — we still expose a seed so analysis
    of a specific deal can be reproduced.
    """

    def __init__(self, spec: DeckSpec, seed: Optional[int] = None):
        self.spec = spec
        self._rng = random.Random(seed)
        self._cards: list[PokerCard] = []
        self._dealt: int = 0
        self.shuffles: int = 0
        self.shuffle()

    @property
    def cards_remaining(self) -> int:
        return len(self._cards)

    @property
    def cards_dealt(self) -> int:
        return self._dealt

    def shuffle(self) -> None:
        self._cards = build_deck(self.spec)
        self._rng.shuffle(self._cards)
        self._dealt = 0
        self.shuffles += 1

    def next_card(self) -> PokerCard:
        if not self._cards:
            self.shuffle()
        card = self._cards.pop(0)
        self._dealt += 1
        return card

    def deal(self, n: int) -> list[PokerCard]:
        return [self.next_card() for _ in range(n)]


__all__ = ["DeckSpec", "PokerShoe", "build_deck"]
