"""Hand-strength heuristics. NOT a Monte Carlo equity calculator — just a
0..1 score that captures 'how good is this hand right now'. Personality
bots translate this score into actions; faking equity vs Monte Carlo
sims keeps the simulator fast on a Render free tier.

  pre_flop_strength: from 2 hole cards alone. Loosely tracks the Sklansky
                     groups but mapped to 0..1.
  post_flop_strength: from hole + community cards using the high evaluator.
                      0..1 mapped from the made hand class plus a 'draw
                      hint' bump for live straight/flush draws.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..cards import Card, Joker, PokerCard
from ..evaluator import HandClass, classify_high
from ..evaluator.high import best_high, rank_high


@dataclass
class HandStrength:
    score: float       # 0..1; >=0.7 = strong, 0.4..0.7 = decent, <0.3 = weak
    label: str         # human-readable summary
    made_class: int    # HandClass int value (0..9), or -1 if pre-flop
    is_pair_or_better: bool


# ---- pre-flop ---------------------------------------------------------

def pre_flop_strength(hole: list[Card]) -> HandStrength:
    """Score 2 hole cards. Premium pairs near 1.0, rags near 0.05.

    We use a simple version of the Chen formula (high card points + pair
    bonus + suited bonus + connectors bonus) then squash to 0..1.
    """
    if len(hole) != 2:
        return HandStrength(0.0, "—", -1, False)
    a, b = hole
    if isinstance(a, Joker) or isinstance(b, Joker):
        # Joker pre-flop is treated as a generic 'good' card by personalities
        # that aren't aware of partial-wild rules. Phase 7 can refine.
        return HandStrength(0.7, "joker hand", -1, False)
    h = max(rank_high(a.rank), rank_high(b.rank))
    l = min(rank_high(a.rank), rank_high(b.rank))

    # Chen-style high-card points.
    points = {14: 10, 13: 8, 12: 7, 11: 6}.get(h, h / 2.0)

    # Pair bonus: pair value = max(5, 2 * card-value), so AA=20, KK=16, ..., 22=5
    if a.rank == b.rank:
        points = max(5, points * 2)
        label = f"pair of {a.rank}s"
    else:
        suited = a.suit == b.suit
        if suited:
            points += 2
        gap = h - l - 1
        if gap == 0:
            points += 1   # connector
        elif gap == 1:
            points += 0   # one-gap
        elif gap == 2:
            points -= 2
        elif gap == 3:
            points -= 4
        else:
            points -= 5
        if h < 12 and gap > 0:
            points -= 1
        label = f"{a.rank}{a.suit.value}{b.rank}{b.suit.value} {'suited' if suited else 'offsuit'}"

    # Squash to 0..1. Premium AA ~ 20 -> 1.0; rags hit floor.
    score = max(0.0, min(1.0, (points + 5) / 25.0))
    is_pair = a.rank == b.rank
    return HandStrength(score=score, label=label, made_class=-1, is_pair_or_better=is_pair)


# ---- post-flop --------------------------------------------------------

# Class-to-score baseline (no draw bumps yet).
_CLASS_SCORE: dict[int, float] = {
    HandClass.HIGH_CARD: 0.20,
    HandClass.PAIR: 0.40,
    HandClass.TWO_PAIR: 0.65,
    HandClass.THREE_OF_A_KIND: 0.80,
    HandClass.STRAIGHT: 0.85,
    HandClass.FLUSH: 0.90,
    HandClass.FULL_HOUSE: 0.95,
    HandClass.FOUR_OF_A_KIND: 0.98,
    HandClass.STRAIGHT_FLUSH: 1.00,
    HandClass.FIVE_OF_A_KIND: 1.00,
}


def post_flop_strength(
    hole: list[Card], community: list[Card],
) -> HandStrength:
    """Score the player's best made hand on the flop / turn / river.

    Adds a small bump for active draws so 'good draw, weak made' bots
    don't fold every flush draw.
    """
    if not community:
        return pre_flop_strength(hole)
    cards: list[PokerCard] = list(hole) + list(community)
    # Treat any joker as fully wild for strength purposes; substitution
    # specifics matter for showdown but here we just want a feel for power.
    if any(isinstance(c, Joker) for c in cards):
        # Replace each joker with an Ace of a fresh-feeling suit; rough.
        cards = [Card("A", _suit_for_joker(i)) if isinstance(c, Joker) else c
                 for i, c in enumerate(cards)]
    rank = best_high(cards)
    base = _CLASS_SCORE[int(rank.cls)]

    # Draw bump: count flush + straight outs cheaply.
    bump = _draw_bump(cards) if rank.cls in (HandClass.HIGH_CARD, HandClass.PAIR) else 0.0
    score = min(1.0, base + bump)

    label = HandClass(rank.cls).name.lower().replace("_", " ")
    return HandStrength(
        score=score,
        label=label,
        made_class=int(rank.cls),
        is_pair_or_better=int(rank.cls) >= int(HandClass.PAIR),
    )


def _draw_bump(cards: list[Card]) -> float:
    """Cheap heuristic: 4-flush -> +0.10; OESD (open-ended straight) -> +0.10."""
    bump = 0.0

    # 4 to a flush?
    suit_counts: dict = {}
    for c in cards:
        suit_counts[c.suit] = suit_counts.get(c.suit, 0) + 1
    if max(suit_counts.values(), default=0) >= 4:
        bump += 0.10

    # Open-ended straight: 4 in a row.
    vals = sorted({rank_high(c.rank) for c in cards})
    # Add ace-low alias so wheel draws are detected.
    if 14 in vals:
        vals = sorted(set(vals) | {1})
    run = 1
    longest = 1
    for i in range(1, len(vals)):
        if vals[i] - vals[i - 1] == 1:
            run += 1
            longest = max(longest, run)
        else:
            run = 1
    if longest >= 4:
        bump += 0.10
    return bump


# Cycle through suits when treating wilds as ace; not consequential since
# this is just for strength feel.
def _suit_for_joker(seed_idx: int):
    from ..cards import Suit
    suits = list(Suit)
    return suits[seed_idx % len(suits)]
