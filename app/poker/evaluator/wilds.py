"""Wild-card substitution for the high evaluator.

Three substitution modes — picked per-hand by the caller (phase 3's variant
DSL decides which mode applies to which cards based on the variant's rules).

  FULLY_WILD            try every standard card; pick whichever produces
                        the strongest HandRank
  STRAIGHT_FLUSH_ONLY   the user's home-game rule: jokers only complete
                        straights, flushes, and straight flushes. If no
                        substitution yields one of those, the wild is
                        'dead' — substituted with a non-pairing, non-suited
                        filler so the rest of the hand classifies correctly.
  BUG                   classic California Bug: wild for straights and
                        flushes, otherwise plays as an Ace.

The evaluator never sees a Joker — wilds.py resolves them and forwards
concrete Cards to classify_high.
"""
from __future__ import annotations

from enum import Enum
from itertools import product
from typing import Iterable, Optional

from ..cards import Card, Joker, PokerCard, Suit
from .high import (
    HandClass,
    HandRank,
    classify_high,
    rank_high,
)

# Standard 52-card universe used as the substitution candidate set.
_RANKS = ("2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A")


def _all_cards() -> list[Card]:
    return [Card(r, s) for s in Suit for r in _RANKS]


class WildMode(str, Enum):
    FULLY_WILD = "fully_wild"
    STRAIGHT_FLUSH_ONLY = "straight_flush_only"
    BUG = "bug"


_SF_CLASSES = {HandClass.STRAIGHT, HandClass.FLUSH, HandClass.STRAIGHT_FLUSH}


def _dead_substitution(known: list[Card]) -> Card:
    """Pick a card that doesn't pair any rank in `known` and doesn't extend
    any suit in `known`. With at most 4 real cards we always have one."""
    used_ranks = {c.rank for c in known}
    used_suits = {c.suit for c in known}
    for s in Suit:
        if s in used_suits:
            continue
        for r in _RANKS:
            if r in used_ranks:
                continue
            return Card(r, s)
    # Fallback: only rank constraint. Won't happen with <=4 known cards.
    for r in _RANKS:
        if r not in used_ranks:
            return Card(r, next(iter(Suit)))
    raise RuntimeError("ran out of dead substitutions (impossible with <13 cards)")


def evaluate_with_wilds(
    cards: Iterable[PokerCard],
    *,
    wild_indices: Optional[list[int]] = None,
    mode: WildMode = WildMode.FULLY_WILD,
) -> HandRank:
    """Evaluate exactly 5 cards where the positions in wild_indices are
    treated as wild according to `mode`. If wild_indices is None, every
    Joker in `cards` is treated as wild.
    """
    cards = list(cards)
    if len(cards) != 5:
        raise ValueError(f"evaluate_with_wilds needs 5 cards, got {len(cards)}")

    if wild_indices is None:
        wild_indices = [i for i, c in enumerate(cards) if isinstance(c, Joker)]

    if not wild_indices:
        return classify_high(cards)

    fixed: list[Card] = []
    for i, c in enumerate(cards):
        if i in wild_indices:
            continue
        if isinstance(c, Joker):
            raise ValueError(f"card at index {i} is a Joker but not in wild_indices")
        fixed.append(c)

    candidates = _all_cards()
    best: Optional[HandRank] = None

    # Every (ordered) substitution tuple. Duplicates that match an already-
    # present card are still considered (some poker dialects allow paired
    # wilds — e.g. two deuces wild yielding quad aces). The evaluator just
    # picks the strongest legal hand under the mode.
    for substitution in product(candidates, repeat=len(wild_indices)):
        trial = list(cards)
        for idx, sub in zip(wild_indices, substitution):
            trial[idx] = sub
        rank = classify_high(trial)
        if mode == WildMode.STRAIGHT_FLUSH_ONLY and rank.cls not in _SF_CLASSES:
            continue
        if mode == WildMode.BUG and rank.cls not in _SF_CLASSES:
            # Bug joker plays as an Ace when no straight/flush is made.
            # Skip these substitutions in the loop and resolve below.
            continue
        if best is None or rank > best:
            best = rank

    if best is not None:
        return best

    # No straight/flush was reachable — fall back per mode.
    if mode == WildMode.STRAIGHT_FLUSH_ONLY:
        return _evaluate_with_dead_wilds(cards, wild_indices, fixed)
    if mode == WildMode.BUG:
        return _evaluate_bug_as_ace(cards, wild_indices, fixed)

    # FULLY_WILD always finds a result.
    raise RuntimeError("FULLY_WILD evaluation produced no HandRank")


def _evaluate_with_dead_wilds(
    cards: list[PokerCard],
    wild_indices: list[int],
    fixed: list[Card],
) -> HandRank:
    """Wilds couldn't make a straight/flush — treat each wild as a 'dead'
    card (no pair, no suit overlap) and classify the remainder."""
    trial = list(cards)
    known = list(fixed)
    for idx in wild_indices:
        dummy = _dead_substitution(known)
        trial[idx] = dummy
        known.append(dummy)
    return classify_high(trial)


def _evaluate_bug_as_ace(
    cards: list[PokerCard],
    wild_indices: list[int],
    fixed: list[Card],
) -> HandRank:
    """Bug joker: if no straight/flush is possible, the joker plays as an
    Ace. Pick a suit not already present so it doesn't create accidental
    flushes."""
    used_suits = {c.suit for c in fixed}
    pick_suit = next((s for s in Suit if s not in used_suits), next(iter(Suit)))
    trial = list(cards)
    for idx in wild_indices:
        trial[idx] = Card("A", pick_suit)
    return classify_high(trial)


def joker_indices(cards: Iterable[PokerCard]) -> list[int]:
    """Convenience: positions of every Joker in a 5-card hand."""
    return [i for i, c in enumerate(cards) if isinstance(c, Joker)]
