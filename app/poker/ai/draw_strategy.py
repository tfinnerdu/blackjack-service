"""AI discard heuristics for draw poker.

Given a 5-card hand (or 4 for badugi) and the variant, return the
indices to discard. Simple rule-based — meant to be recognizable, not
GTO-correct.

  high (5-Card Draw):
    - keep pair/trips/quads, discard the rest
    - 4-card flush or open-ended straight: discard the off card
    - high card only: keep an ace if present, otherwise discard 4-5

  ace-to-five (lo-only games like Razz, but Razz isn't draw — only
  documentation here):
    - keep cards 8-or-below, discard the highest cards

  deuce-to-seven (2-7 Triple Draw):
    - keep low cards (2-7), discard high cards (8+) and any pair
    - never keep aces (they're high in 2-7)

  badugi (4-card lo, distinct ranks + distinct suits):
    - keep any badugi (1 card per suit, distinct ranks); discard duplicates
"""
from __future__ import annotations

from collections import Counter
from typing import Sequence

from ..cards import Card, Joker, PokerCard
from ..evaluator.high import rank_high
from ..evaluator.low import LowRule
from ..variants import HandRequirement, HiLoSplit, VariantSpec


def _ranks(cards: Sequence[PokerCard]) -> list[int]:
    return [rank_high(c.rank) for c in cards if not isinstance(c, Joker)]


def _suits(cards: Sequence[PokerCard]) -> list[str]:
    return [c.suit.value for c in cards if not isinstance(c, Joker)]


def discard_indices(
    hand: list[PokerCard],
    variant: VariantSpec,
) -> list[int]:
    """Return positions to discard from `hand`. Empty list = stand pat."""
    if not hand:
        return []

    # Lo-only variants: 2-7 or badugi rules drive different heuristics.
    if variant.hi_lo == HiLoSplit.LO_ONLY:
        if variant.lo_rule == LowRule.DEUCE_TO_SEVEN:
            return _discard_for_d27(hand)
        if variant.lo_rule == LowRule.BADUGI:
            return _discard_for_badugi(hand)
        if variant.lo_rule == LowRule.ACE_TO_FIVE:
            return _discard_for_a5(hand)

    # Default: high-only (5-Card Draw style).
    return _discard_for_high(hand)


# ---- 5-Card Draw (high) ------------------------------------------------

def _discard_for_high(hand: list[PokerCard]) -> list[int]:
    if len(hand) < 5:
        return []
    # Identify pairs / trips / quads.
    rank_counts = Counter(_ranks(hand))
    multi_ranks = {r for r, n in rank_counts.items() if n >= 2}
    if multi_ranks:
        # Keep the multi-rank cards; discard the rest.
        keep = [
            i for i, c in enumerate(hand)
            if not isinstance(c, Joker) and rank_high(c.rank) in multi_ranks
        ]
        return [i for i in range(len(hand)) if i not in keep]

    # 4-card flush?
    suit_counts = Counter(_suits(hand))
    flush_suit = next((s for s, n in suit_counts.items() if n >= 4), None)
    if flush_suit is not None:
        keep = [
            i for i, c in enumerate(hand)
            if not isinstance(c, Joker) and c.suit.value == flush_suit
        ]
        return [i for i in range(len(hand)) if i not in keep][:1]

    # Open-ended straight draw? (4 sequential ranks.)
    sorted_idx = sorted(
        range(len(hand)),
        key=lambda i: rank_high(hand[i].rank) if not isinstance(hand[i], Joker) else 0,
    )
    sorted_ranks = sorted(_ranks(hand))
    if len(sorted_ranks) >= 4:
        for start in range(len(sorted_ranks) - 3):
            window = sorted_ranks[start:start + 4]
            if window[-1] - window[0] == 3 and len(set(window)) == 4:
                # Discard the one card not in the window.
                window_set = set(window)
                discard = [
                    i for i, c in enumerate(hand)
                    if isinstance(c, Joker) or rank_high(c.rank) not in window_set
                ]
                return discard[:1]

    # Just high cards. Keep ace if any, else top card; discard the rest.
    sorted_by_rank = sorted(
        range(len(hand)),
        key=lambda i: -(rank_high(hand[i].rank) if not isinstance(hand[i], Joker) else 0),
    )
    keep = sorted_by_rank[:1]  # keep the top card
    return [i for i in range(len(hand)) if i not in keep]


# ---- 2-7 Triple Draw ---------------------------------------------------

def _discard_for_d27(hand: list[PokerCard]) -> list[int]:
    """Keep 2..7; discard 8+ and aces (A is HIGH in 2-7). Avoid pairs."""
    if not hand:
        return []
    discards: list[int] = []
    seen_ranks: set[int] = set()
    for i, c in enumerate(hand):
        if isinstance(c, Joker):
            discards.append(i)
            continue
        v = rank_high(c.rank)
        if v == 14:  # ace, high in 2-7
            discards.append(i)
            continue
        if v >= 8:
            discards.append(i)
            continue
        if v in seen_ranks:
            discards.append(i)
            continue
        seen_ranks.add(v)
    return discards[:5]   # 2-7 Triple Draw allows up to 5 replacements


# ---- Badugi -----------------------------------------------------------

def _discard_for_badugi(hand: list[PokerCard]) -> list[int]:
    """Keep one card per suit + lowest available. Discard duplicates of
    suit (keep the lowest of each), discard duplicates of rank entirely.

    Badugi uses ace-low ordering (A=1, K=13) so the iteration prefers
    aces over kings of the same suit."""
    discards: list[int] = []
    by_suit: dict[str, int] = {}     # suit -> kept-index
    seen_ranks: set[int] = set()

    def _badugi_value(c: PokerCard) -> int:
        if isinstance(c, Joker):
            return 99
        return 1 if c.rank == "A" else rank_high(c.rank)

    order = sorted(range(len(hand)), key=lambda i: _badugi_value(hand[i]))
    for i in order:
        c = hand[i]
        if isinstance(c, Joker):
            discards.append(i)
            continue
        v = _badugi_value(c)
        s = c.suit.value
        if v in seen_ranks or s in by_suit:
            discards.append(i)
        else:
            seen_ranks.add(v)
            by_suit[s] = i
    return sorted(discards)[: max(0, len(hand))]


# ---- Ace-to-five lowball ----------------------------------------------

def _discard_for_a5(hand: list[PokerCard]) -> list[int]:
    """Keep cards 8-and-below (with ace as low); discard high cards and
    pairs."""
    discards: list[int] = []
    seen_ranks: set[int] = set()
    for i, c in enumerate(hand):
        if isinstance(c, Joker):
            discards.append(i)
            continue
        v = rank_high(c.rank)
        a5_value = 1 if c.rank == "A" else v
        if a5_value > 8:
            discards.append(i)
            continue
        if a5_value in seen_ranks:
            discards.append(i)
            continue
        seen_ranks.add(a5_value)
    return discards[:5]
