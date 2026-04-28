"""AI playstyles. Each function picks an action for an AI seat given the
current hand state. The orchestrator calls one of these per AI hand.

All playstyles return one of: 'hit' | 'stand' | 'double' | 'split' | 'surrender'.
The chosen action is filtered against capabilities by the orchestrator —
playstyles can suggest 'double' on a 3-card hand and we'll fall through.

Common idea: players who don't follow the book make recognizable, repeatable
mistakes. Each playstyle below is tuned to feel like a real archetype rather
than just 'random play'.
"""
from __future__ import annotations

import random
from typing import Callable, Optional

from ..engine.cards import Card, hand_total, is_ten
from ..engine.hand import Hand
from ..engine.rules import Rules
from ..strategy import BookAction, Capabilities
from ..strategy.book import book


PlayFn = Callable[
    [Hand, Card, Rules, Capabilities, Optional[float], random.Random],
    BookAction,
]


# ---- by the book -------------------------------------------------------

def play_book(hand, dealer_up, rules, caps, true_count, rng) -> BookAction:
    """Perfect basic strategy. No counting awareness."""
    return book(hand, dealer_up, rules, caps, true_count=None).action


# ---- counter -----------------------------------------------------------

def play_counter(hand, dealer_up, rules, caps, true_count, rng) -> BookAction:
    """Basic strategy with Illustrious 18 + Fab 4 deviations applied."""
    return book(hand, dealer_up, rules, caps, true_count=true_count).action


# ---- tight / scared -----------------------------------------------------

def play_tight(hand, dealer_up, rules, caps, true_count, rng) -> BookAction:
    """Scared money. Never doubles. Only splits A,A and 8,8.

    Stands on hard 12+. Hits soft 17 and below; stands soft 18+. Never
    surrenders (afraid of giving up).
    """
    if len(hand.cards) == 2 and caps.can_split:
        a, b = hand.cards
        if a.rank == b.rank == "A":
            return "split"
        if a.rank == b.rank == "8":
            return "split"
    total, soft = hand_total(hand.cards)
    if soft:
        if total <= 17:
            return "hit"
        return "stand"
    if total <= 11:
        return "hit"
    return "stand"


# ---- aggressive --------------------------------------------------------

def play_aggressive(hand, dealer_up, rules, caps, true_count, rng) -> BookAction:
    """Loud and proud. Doubles 9-11, splits every pair, hits soft 18 vs
    anything dealer-strong, stands soft 19+. Surrenders never (tilt).
    """
    if len(hand.cards) == 2 and caps.can_split:
        a, b = hand.cards
        if a.rank == b.rank or (is_ten(a.rank) and is_ten(b.rank)):
            return "split"

    total, soft = hand_total(hand.cards)
    if not soft and 9 <= total <= 11 and caps.can_double:
        return "double"
    if soft and 13 <= total <= 17 and caps.can_double:
        return "double"
    if soft and total == 18:
        return "hit"
    if soft and total >= 19:
        return "stand"
    if total <= 11:
        return "hit"
    if total >= 17:
        return "stand"
    # 12-16: aggressive player still hits stiffs vs dealer 7+
    col = dealer_up.rank
    if col in ("7", "8", "9", "T", "J", "Q", "K", "A"):
        return "hit"
    return "stand"


# ---- mimic dealer ------------------------------------------------------

def play_mimic_dealer(hand, dealer_up, rules, caps, true_count, rng) -> BookAction:
    """Plays the dealer's rules. Never doubles, never splits, never surrenders."""
    total, soft = hand_total(hand.cards)
    if total < 17:
        return "hit"
    if total == 17 and soft and rules.dealer_hits_soft_17:
        return "hit"
    return "stand"


# ---- hunch -------------------------------------------------------------

def play_hunch(hand, dealer_up, rules, caps, true_count, rng) -> BookAction:
    """Looks human. Plays mostly book, but on 'feel' hands (12-16 vs 7-A)
    they sometimes stand when they should hit."""
    base = book(hand, dealer_up, rules, caps).action
    total, soft = hand_total(hand.cards)
    is_stiff = not soft and 12 <= total <= 16
    dealer_strong = dealer_up.rank in ("7", "8", "9", "T", "J", "Q", "K", "A")
    if base == "hit" and is_stiff and dealer_strong and rng.random() < 0.30:
        return "stand"
    return base


# ---- drunk -------------------------------------------------------------

def play_drunk(hand, dealer_up, rules, caps, true_count, rng, mistake_rate: float = 0.20):
    """Book play with X% chance of doing something stupid. The mistake is
    chosen so it usually still resolves (e.g., picks hit instead of stand,
    not 'split when not pairs'). Can be parameterized via the AI seat."""
    base = book(hand, dealer_up, rules, caps).action
    if rng.random() >= mistake_rate:
        return base
    # Pick a different but legal-looking action.
    pool: list[BookAction] = ["hit", "stand"]
    if caps.can_double:
        pool.append("double")
    other = [a for a in pool if a != base]
    if not other:
        return base
    return rng.choice(other)


# ---- superstitious -----------------------------------------------------

def play_superstitious(hand, dealer_up, rules, caps, true_count, rng) -> BookAction:
    """Quirky exceptions to basic strategy:

    - Never hits 16 (the 'unlucky 16').
    - Always splits 10s vs 5 or 6 ('press when the dealer's weak').
    - Refuses insurance (handled separately by the orchestrator).
    - Never surrenders (it's bad luck).
    """
    total, soft = hand_total(hand.cards)
    if not soft and total == 16:
        return "stand"

    if len(hand.cards) == 2 and caps.can_split:
        a, b = hand.cards
        if is_ten(a.rank) and is_ten(b.rank) and dealer_up.rank in ("5", "6"):
            return "split"

    base = book(hand, dealer_up, rules, caps).action
    if base == "surrender":
        # Refuses to surrender — fall back to the 'else' from the chart cell.
        # Pragmatic substitute: hit the stiff.
        return "hit" if total <= 16 else "stand"
    return base


# ---- streaky -----------------------------------------------------------
# Streaky's distinctive behavior is in bet sizing (handled by bet_patterns.py),
# not action selection. They play book for actions.

def play_streaky(hand, dealer_up, rules, caps, true_count, rng) -> BookAction:
    return book(hand, dealer_up, rules, caps).action


# ---- registry ----------------------------------------------------------

PLAYSTYLES: dict[str, PlayFn] = {
    "book": play_book,
    "counter": play_counter,
    "tight": play_tight,
    "aggressive": play_aggressive,
    "mimic_dealer": play_mimic_dealer,
    "hunch": play_hunch,
    "drunk": play_drunk,
    "superstitious": play_superstitious,
    "streaky": play_streaky,
}


def get_playstyle(name: str) -> PlayFn:
    if name not in PLAYSTYLES:
        raise KeyError(f"unknown playstyle: {name!r}; choose from {sorted(PLAYSTYLES)}")
    return PLAYSTYLES[name]


def all_playstyles() -> list[str]:
    return list(PLAYSTYLES.keys())
