"""Low-hand evaluators.

Three independent low rules, each with its own scoring + qualifier:

- ACE_TO_FIVE: aces are low, straights/flushes don't count, pairs disqualify.
  Used by Omaha Hi/Lo (with 8-or-better qualifier), Stud Hi/Lo, Razz.
  Best low = wheel (A-2-3-4-5).
- DEUCE_TO_SEVEN: aces are HIGH, straights AND flushes count against you.
  Used by 2-7 Triple Draw, Lowball.
  Best low = 7-5-4-3-2 unsuited.
- BADUGI: 4-card hand. Pick the best 4-of-different-rank-and-suit. Pairs
  disqualify; matching suits 'kill' the higher one. Best = A-2-3-4 of
  four suits.

LowRank.qualifies is False when no qualifying low exists (8-or-better
qualifier missed; pair-blocked A-5; less-than-4-card badugi).

Comparison convention: lower ranks tuple = better low. Use
`best_low(...).ranks` directly — no overloaded operators, sort ascending.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from itertools import combinations
from typing import Iterable, Optional

from ..cards import Card, Joker, PokerCard, Suit
from .high import classify_high, HandClass, HandRank, rank_high


class LowRule(str, Enum):
    ACE_TO_FIVE = "ace_to_five"
    DEUCE_TO_SEVEN = "deuce_to_seven"
    BADUGI = "badugi"


@dataclass(frozen=True)
class LowRank:
    rule: LowRule
    qualifies: bool
    ranks: tuple[int, ...]              # descending; smaller = better low
    cards: tuple[Card, ...] = ()
    name: str = ""                       # human-readable, e.g. '7-5-4-3-2 (wheel)'


# Ace-to-five rank values: A is 1 (best/lowest); 2..K = 2..13.
def _a5_rank(rank: str) -> int:
    return 1 if rank == "A" else rank_high(rank)


# Deuce-to-seven rank values: A is 14 (worst). Same as standard high.
def _d27_rank(rank: str) -> int:
    return rank_high(rank)


def _check_no_jokers(cards: Iterable[PokerCard]) -> list[Card]:
    out: list[Card] = []
    for c in cards:
        if isinstance(c, Joker):
            raise ValueError("low evaluators require resolved cards (no jokers)")
        out.append(c)
    return out


# ---- Ace-to-five -------------------------------------------------------

def _best_a5(cards: list[Card], *, eight_or_better: bool) -> LowRank:
    """Pick the best 5-card low. Pairs are skipped; we want 5 distinct ranks.

    Returns qualifies=False when fewer than 5 distinct ranks exist or, for
    eight_or_better, when those ranks aren't all 8 or under.
    """
    # Group by A-5 rank value, lowest first; for each rank pick a sample
    # card so the resulting low is reportable as 5 concrete cards.
    by_value: dict[int, Card] = {}
    for c in cards:
        v = _a5_rank(c.rank)
        if v not in by_value:
            by_value[v] = c
    # Pick the 5 smallest distinct values.
    vals = sorted(by_value.keys())[:5]
    if len(vals) < 5:
        return LowRank(LowRule.ACE_TO_FIVE, False, ())
    if eight_or_better and max(vals) > 8:
        return LowRank(LowRule.ACE_TO_FIVE, False, ())
    chosen = [by_value[v] for v in vals]
    ranks_desc = tuple(sorted(vals, reverse=True))
    return LowRank(
        LowRule.ACE_TO_FIVE, True, ranks_desc,
        tuple(chosen),
        name=_a5_name(ranks_desc),
    )


def _a5_name(ranks_desc: tuple[int, ...]) -> str:
    """e.g. (5,4,3,2,1) -> '5-4-3-2-A (wheel)'."""
    label = "-".join("A" if v == 1 else str(v) if v < 10 else "TJQK"[v - 10]
                     for v in ranks_desc)
    if ranks_desc == (5, 4, 3, 2, 1):
        return f"{label} (wheel)"
    return label


# ---- Deuce-to-seven ----------------------------------------------------

def _d27_compare_score(rank: HandRank) -> tuple:
    """For 2-7 lowball, the 'best' hand is the worst high-classification.
    A high-card hand with low kickers wins; a pair loses to high card etc.
    We score by (class_index, ranks_descending) and a *smaller* score
    means a better low.
    """
    return (int(rank.cls), rank.tiebreakers)


def _best_d27(cards: list[Card]) -> LowRank:
    """Best 5-card 2-7 low. Aces are HIGH, straights and flushes count
    against you. Always qualifies (no qualifier in 2-7 lowball)."""
    if len(cards) < 5:
        return LowRank(LowRule.DEUCE_TO_SEVEN, False, ())
    best_rank: Optional[HandRank] = None
    best_combo: Optional[tuple[Card, ...]] = None
    for combo in combinations(cards, 5):
        rank = classify_high(list(combo))
        if best_rank is None or _d27_compare_score(rank) < _d27_compare_score(best_rank):
            best_rank = rank
            best_combo = combo
    assert best_rank is not None and best_combo is not None
    # Encode as descending ranks (with A=14 since it's the worst card here).
    ranks = tuple(sorted([_d27_rank(c.rank) for c in best_combo], reverse=True))
    return LowRank(
        LowRule.DEUCE_TO_SEVEN,
        True,
        # Prepend the high-class index so a pair-2-7 doesn't beat a
        # high-card-Q-7 in comparison: smaller class wins.
        (int(best_rank.cls),) + ranks,
        best_combo,
        name=_d27_name(best_rank, ranks),
    )


def _d27_name(rank: HandRank, ranks_desc: tuple[int, ...]) -> str:
    if rank.cls == HandClass.HIGH_CARD:
        label = "-".join(_short_rank(v) for v in ranks_desc)
        return label
    return rank.name()


def _short_rank(v: int) -> str:
    return "A" if v == 14 else str(v) if v < 10 else "TJQK"[v - 10]


# ---- Badugi ------------------------------------------------------------

def _best_badugi(cards: list[Card]) -> LowRank:
    """Best 4-card badugi. Pick the largest set of cards with all distinct
    ranks AND all distinct suits, then break ties by lowest highest-card.

    'Best' is usually the 4-card badugi (4 distinct ranks + 4 suits). When
    no 4-card badugi exists we still report the best 3-card badugi etc.
    qualifies=True when at least a 4-card badugi exists.
    """
    if not cards:
        return LowRank(LowRule.BADUGI, False, ())
    # Convert to (a5_value, suit, original_card) tuples; lower a5_value
    # is preferred.
    triples = [(_a5_rank(c.rank), c.suit, c) for c in cards]
    # Try every subset of size 4 first; fall back to 3, 2, 1.
    for size in (4, 3, 2, 1):
        best: Optional[tuple[tuple[int, ...], list[Card]]] = None
        for combo in combinations(triples, size):
            ranks = [t[0] for t in combo]
            suits = [t[1] for t in combo]
            if len(set(ranks)) != size or len(set(suits)) != size:
                continue
            ranks_desc = tuple(sorted(ranks, reverse=True))
            if best is None or ranks_desc < best[0]:
                best = (ranks_desc, [t[2] for t in combo])
        if best is not None:
            qualifies = size == 4
            return LowRank(
                LowRule.BADUGI,
                qualifies,
                # Prefix size so a 4-card badugi beats any 3-card etc.
                # Smaller (size, ranks) = better; we invert size so 4 < 3 < ...
                (-len(best[0]),) + best[0],
                tuple(best[1]),
                name=_badugi_name(size, best[0]),
            )
    return LowRank(LowRule.BADUGI, False, ())


def _badugi_name(size: int, ranks_desc: tuple[int, ...]) -> str:
    label = "-".join(_a5_short(v) for v in ranks_desc)
    return f"{size}-card {label}"


def _a5_short(v: int) -> str:
    return "A" if v == 1 else str(v) if v < 10 else "TJQK"[v - 10]


# ---- public API --------------------------------------------------------

def best_low(
    cards: Iterable[PokerCard],
    rule: LowRule,
    *,
    eight_or_better: bool = False,
) -> LowRank:
    """Best low from an arbitrary card pile.

    - ACE_TO_FIVE: 5 distinct ranks; eight_or_better gates qualification.
    - DEUCE_TO_SEVEN: best 5-of-N where smallest high-classification wins.
    - BADUGI: best ranked-and-suited 1..4 card subset.
    """
    resolved = _check_no_jokers(cards)
    if rule == LowRule.ACE_TO_FIVE:
        return _best_a5(resolved, eight_or_better=eight_or_better)
    if rule == LowRule.DEUCE_TO_SEVEN:
        return _best_d27(resolved)
    if rule == LowRule.BADUGI:
        return _best_badugi(resolved)
    raise ValueError(f"unknown low rule: {rule}")


def low_ranks_compare(a: LowRank, b: LowRank) -> int:
    """Return -1 if a is better than b, 1 if worse, 0 if equal.

    Non-qualifying lows are always 'worse' than qualifying lows. Among
    qualifying lows, smaller ranks tuple wins.
    """
    if a.qualifies and not b.qualifies:
        return -1
    if b.qualifies and not a.qualifies:
        return 1
    if not a.qualifies and not b.qualifies:
        return 0
    if a.ranks < b.ranks:
        return -1
    if a.ranks > b.ranks:
        return 1
    return 0
