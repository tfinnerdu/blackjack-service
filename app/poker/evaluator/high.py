"""Standard high-hand evaluator.

We sort hands first by class (straight flush > quads > full house > ...) and
within a class by tie-breaker ranks. The HandRank result encodes both, so
sorting a list of HandRank objects gives the canonical poker order with
the strongest hand last.

Aces play both high (default) and low (in A-2-3-4-5 wheel straights and
in A-2-3-4-5-of-suit straight-flushes / steel wheels). Both treatments
are checked.

Wild cards are NOT handled here — wilds.py picks the optimal substitution
and feeds 5 concrete cards into classify_high. A joker that arrives here
unsubstituted is rejected (callers must resolve wilds first).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Iterable, Optional

from itertools import combinations

from ..cards import Card, Joker, PokerCard


class HandClass(IntEnum):
    HIGH_CARD = 0
    PAIR = 1
    TWO_PAIR = 2
    THREE_OF_A_KIND = 3
    STRAIGHT = 4
    FLUSH = 5
    FULL_HOUSE = 6
    FOUR_OF_A_KIND = 7
    STRAIGHT_FLUSH = 8
    FIVE_OF_A_KIND = 9   # only reachable with wilds


HAND_CLASS_NAMES: dict[int, str] = {
    HandClass.HIGH_CARD: "High card",
    HandClass.PAIR: "Pair",
    HandClass.TWO_PAIR: "Two pair",
    HandClass.THREE_OF_A_KIND: "Three of a kind",
    HandClass.STRAIGHT: "Straight",
    HandClass.FLUSH: "Flush",
    HandClass.FULL_HOUSE: "Full house",
    HandClass.FOUR_OF_A_KIND: "Four of a kind",
    HandClass.STRAIGHT_FLUSH: "Straight flush",
    HandClass.FIVE_OF_A_KIND: "Five of a kind",
}


# Rank-to-value: A high = 14, K = 13, ... 2 = 2. Lookup-only — Card stores
# 'A'/'2'/'T'/'J'/'Q'/'K' as strings.
_RANK_HIGH: dict[str, int] = {
    "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
    "T": 10, "J": 11, "Q": 12, "K": 13, "A": 14,
}


def rank_high(rank: str) -> int:
    return _RANK_HIGH[rank]


@dataclass(frozen=True)
class HandRank:
    """Comparable hand strength. The tuple ordering mimics standard poker
    comparison: class first, then class-specific tie-breakers.

    `cards` is descriptive only — two seats holding the same strength
    via different physical cards (e.g. both playing the board straight)
    must compare equal so split pots resolve correctly. We mark cards
    compare=False so dataclass equality + ordering ignore it.
    """
    cls: HandClass
    tiebreakers: tuple[int, ...]
    cards: tuple[Card, ...] = field(default=(), compare=False)

    def __lt__(self, other: "HandRank") -> bool:
        return (self.cls, self.tiebreakers) < (other.cls, other.tiebreakers)

    def __le__(self, other: "HandRank") -> bool:
        return (self.cls, self.tiebreakers) <= (other.cls, other.tiebreakers)

    def __gt__(self, other: "HandRank") -> bool:
        return (self.cls, self.tiebreakers) > (other.cls, other.tiebreakers)

    def name(self) -> str:
        return HAND_CLASS_NAMES[int(self.cls)]


def _check_wilds_resolved(cards: Iterable[PokerCard]) -> list[Card]:
    """Reject jokers — wild substitution is wilds.py's job. Returns the
    list as concrete Cards so callers can drop the type-narrowing dance."""
    resolved: list[Card] = []
    for c in cards:
        if isinstance(c, Joker):
            raise ValueError("classify_high requires wilds to be resolved first")
        resolved.append(c)
    return resolved


def _is_straight(rank_values: list[int]) -> Optional[int]:
    """Returns the high card of the straight, or None if not a straight.
    Handles the A-2-3-4-5 wheel by promoting the ace to 1 and re-checking."""
    s = sorted(set(rank_values))
    if len(s) != 5:
        return None
    if s == [2, 3, 4, 5, 14]:
        # Wheel: ace plays low, high card is the 5.
        return 5
    if s[-1] - s[0] == 4:
        return s[-1]
    return None


def classify_high(cards: Iterable[PokerCard]) -> HandRank:
    """Classify exactly 5 cards. Wilds must be pre-substituted."""
    resolved = _check_wilds_resolved(cards)
    if len(resolved) != 5:
        raise ValueError(f"classify_high needs 5 cards, got {len(resolved)}")

    rank_values = sorted([rank_high(c.rank) for c in resolved], reverse=True)
    rank_counts = Counter(rank_values)
    suit_counts = Counter(c.suit for c in resolved)

    is_flush = max(suit_counts.values()) == 5
    straight_high = _is_straight(rank_values)

    # Order tiebreakers descending so direct tuple comparison works.
    grouped = sorted(rank_counts.items(), key=lambda kv: (-kv[1], -kv[0]))
    counts_descending = [count for _, count in grouped]
    ranks_by_count = [rank for rank, _ in grouped]

    # 5 of a kind (only reachable with wilds → here only as a sanity check
    # since wilds.py would have already substituted).
    if rank_counts and max(rank_counts.values()) == 5:
        five_rank = ranks_by_count[0]
        return HandRank(HandClass.FIVE_OF_A_KIND, (five_rank,), tuple(resolved))

    if is_flush and straight_high is not None:
        # Wheel straight flushes count as steel wheels — high card is 5.
        return HandRank(HandClass.STRAIGHT_FLUSH, (straight_high,), tuple(resolved))

    if counts_descending[:2] == [4, 1]:
        quad, kicker = ranks_by_count[0], ranks_by_count[1]
        return HandRank(HandClass.FOUR_OF_A_KIND, (quad, kicker), tuple(resolved))

    if counts_descending[:2] == [3, 2]:
        trip, pair = ranks_by_count[0], ranks_by_count[1]
        return HandRank(HandClass.FULL_HOUSE, (trip, pair), tuple(resolved))

    if is_flush:
        return HandRank(HandClass.FLUSH, tuple(rank_values), tuple(resolved))

    if straight_high is not None:
        return HandRank(HandClass.STRAIGHT, (straight_high,), tuple(resolved))

    if counts_descending[:1] == [3]:
        trip = ranks_by_count[0]
        kickers = sorted(
            [r for r in rank_values if r != trip], reverse=True
        )
        return HandRank(HandClass.THREE_OF_A_KIND, (trip, *kickers), tuple(resolved))

    if counts_descending[:2] == [2, 2]:
        high_pair = max(ranks_by_count[0], ranks_by_count[1])
        low_pair = min(ranks_by_count[0], ranks_by_count[1])
        kicker = ranks_by_count[2]
        return HandRank(HandClass.TWO_PAIR, (high_pair, low_pair, kicker), tuple(resolved))

    if counts_descending[:1] == [2]:
        pair = ranks_by_count[0]
        kickers = sorted([r for r in rank_values if r != pair], reverse=True)
        return HandRank(HandClass.PAIR, (pair, *kickers), tuple(resolved))

    return HandRank(HandClass.HIGH_CARD, tuple(rank_values), tuple(resolved))


def best_high(
    cards: Iterable[PokerCard],
    *,
    must_use: int = 0,
    hole: Optional[Iterable[PokerCard]] = None,
    board: Optional[Iterable[PokerCard]] = None,
) -> HandRank:
    """Best 5-card high hand.

    Two modes:
    - Default: pick the best 5 from `cards` (e.g. 7-card stud, draw, hold'em
      board+hole pile).
    - 'Use exactly K from hole + (5-K) from board' (Omaha): set must_use=K and
      pass hole + board separately.
    """
    if must_use > 0:
        if hole is None or board is None:
            raise ValueError("must_use mode requires hole + board")
        hole = list(hole)
        board = list(board)
        if must_use > len(hole):
            raise ValueError("must_use > hole size")
        if (5 - must_use) > len(board):
            raise ValueError("not enough board cards for that requirement")
        best: Optional[HandRank] = None
        for h_combo in combinations(hole, must_use):
            for b_combo in combinations(board, 5 - must_use):
                rank = classify_high(list(h_combo) + list(b_combo))
                if best is None or rank > best:
                    best = rank
        assert best is not None
        return best

    cards = list(cards)
    if len(cards) < 5:
        raise ValueError(f"need at least 5 cards, got {len(cards)}")
    if len(cards) == 5:
        return classify_high(cards)

    best = None
    for combo in combinations(cards, 5):
        rank = classify_high(combo)
        if best is None or rank > best:
            best = rank
    assert best is not None
    return best
