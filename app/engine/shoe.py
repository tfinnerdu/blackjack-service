"""Shoe of cards. Supports casino cut-card, CSM, and hand-shuffle modes.

A seed makes shuffles deterministic so a session can be exact-resumed
(re-run the same seed + the same number of dealt cards = identical shoe state).
"""
from __future__ import annotations

import random
from typing import Optional

from .cards import Card, RANKS, Suit
from .rules import ShuffleMode


def _fresh_deck() -> list[Card]:
    return [Card(r, s) for s in Suit for r in RANKS]


def _build_packet(decks: int) -> list[Card]:
    cards: list[Card] = []
    for _ in range(decks):
        cards.extend(_fresh_deck())
    return cards


def _hand_shuffle(cards: list[Card], rng: random.Random) -> list[Card]:
    """Approximate a real human shuffle: a few imperfect riffles + a strip cut.

    A casino dealer typically does ~4 riffles + a strip + a final riffle,
    which is far less random than a Fisher-Yates. We emulate that imperfection
    so 'hand shuffle' meaningfully differs from 'casino shuffle' (which uses
    the proper Fisher-Yates via random.shuffle).
    """
    deck = list(cards)

    def riffle(d: list[Card]) -> list[Card]:
        mid = len(d) // 2 + rng.randint(-3, 3)
        left, right = d[:mid], d[mid:]
        out: list[Card] = []
        while left or right:
            # Imperfect interleave: drop a small clump from each side.
            for _ in range(rng.randint(1, 3)):
                if left:
                    out.append(left.pop(0))
            for _ in range(rng.randint(1, 3)):
                if right:
                    out.append(right.pop(0))
        return out

    def strip(d: list[Card]) -> list[Card]:
        out: list[Card] = []
        i = 0
        while i < len(d):
            chunk = rng.randint(8, 20)
            out = d[i : i + chunk] + out
            i += chunk
        return out

    for _ in range(rng.randint(3, 4)):
        deck = riffle(deck)
    deck = strip(deck)
    deck = riffle(deck)
    return deck


class Shoe:
    """Deal source for a single table.

    `next_card()` returns the top card. `needs_reshuffle` flips True once the
    cut card is reached (casino mode) or never flips (CSM, since used cards
    are returned immediately).
    """

    def __init__(
        self,
        decks: int,
        mode: ShuffleMode = ShuffleMode.CASINO,
        penetration: float = 0.75,
        seed: Optional[int] = None,
    ):
        if not 1 <= decks <= 8:
            raise ValueError("decks must be 1..8")
        self.decks = decks
        self.mode = mode
        self.penetration = penetration
        self._rng = random.Random(seed)
        self._seed = seed
        self._cards: list[Card] = []
        self._dealt: int = 0
        self._cut_card_index: int = 0
        self.shuffles: int = 0
        self.shuffle()

    @property
    def total_cards(self) -> int:
        return self.decks * 52

    @property
    def cards_remaining(self) -> int:
        return len(self._cards)

    @property
    def cards_dealt(self) -> int:
        return self._dealt

    @property
    def needs_reshuffle(self) -> bool:
        if self.mode == ShuffleMode.CSM:
            return False
        return self._dealt >= self._cut_card_index

    @property
    def cards_to_cut(self) -> int:
        """How many more cards can be dealt before the cut-card mark is
        reached. Useful for the play UI: 'X cards before reshuffle'."""
        if self.mode == ShuffleMode.CSM:
            return self.total_cards
        return max(0, self._cut_card_index - self._dealt)

    # Cut-card jitter band, expressed as a fraction of total cards.
    # Real dealers cut at slightly different positions each shuffle;
    # we emulate that with a uniform offset in [-band, +band] around
    # the configured `penetration` ratio. Set to 0.0 to disable.
    CUT_CARD_JITTER = 0.04

    def shuffle(self) -> None:
        """(Re)build the shoe from fresh decks. Each shuffle re-rolls
        the cut-card position within a small band so successive shoes
        feel different — players reported the cut landing in the same
        spot every shoe before this jitter existed."""
        cards = _build_packet(self.decks)
        if self.mode == ShuffleMode.HAND:
            self._cards = _hand_shuffle(cards, self._rng)
        else:
            # CSM and casino both start from a perfect Fisher-Yates shuffle.
            self._rng.shuffle(cards)
            self._cards = cards
        self._dealt = 0
        # Randomize cut around `penetration` within a clamped band.
        if self.mode == ShuffleMode.CASINO and self.CUT_CARD_JITTER > 0:
            jitter = self._rng.uniform(-self.CUT_CARD_JITTER, self.CUT_CARD_JITTER)
            target = max(0.30, min(0.95, self.penetration + jitter))
        else:
            target = self.penetration
        self._cut_card_index = int(self.total_cards * target)
        self.shuffles += 1

    def next_card(self) -> Card:
        if not self._cards:
            # CSM should never run dry, but reshuffle defensively.
            self.shuffle()
        card = self._cards.pop(0)
        self._dealt += 1
        if self.mode == ShuffleMode.CSM:
            # CSM: card returns to the shoe and shoe is conceptually reshuffled.
            # In practice this means each next_card draws from a fresh permutation.
            self._cards.append(card)
            self._rng.shuffle(self._cards)
            # CSM doesn't accumulate "dealt" toward a cut card.
            self._dealt = 0
        return card

    def deal(self, n: int) -> list[Card]:
        return [self.next_card() for _ in range(n)]
