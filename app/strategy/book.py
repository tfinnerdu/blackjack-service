"""The 'book' oracle. Single function the API + AI playstyles call to ask
'what should this hand do?'. Combines basic strategy with count-based
deviations (Illustrious 18 / Fab 4) when a true count is provided.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..counting.indices import (
    IndexPlay,
    insurance_correct,
    lookup_hard,
    lookup_pair,
    lookup_surrender,
)
from ..engine.cards import Card, hand_total, is_ten
from ..engine.hand import Hand
from ..engine.rules import Rules
from . import Capabilities, BookAction, basic_strategy
from .charts import dealer_column


@dataclass
class BookCall:
    """The book's recommendation, with reasoning the UI can show."""
    action: BookAction
    source: str               # "basic" | "index" | "fallback"
    deviation: Optional[str] = None    # "16 vs 10: stand at TC>=0" if index applied
    note: Optional[str] = None         # extra context for coach panel


def book(
    hand: Hand,
    dealer_up: Card,
    rules: Rules,
    caps: Capabilities,
    true_count: Optional[float] = None,
) -> BookCall:
    """Return the optimal play. Index deviations only apply when true_count is given."""
    col = dealer_column(dealer_up.rank)
    total, soft = hand_total(hand.cards)
    is_pair = (
        len(hand.cards) == 2
        and (
            hand.cards[0].rank == hand.cards[1].rank
            or (is_ten(hand.cards[0].rank) and is_ten(hand.cards[1].rank))
        )
    )

    # Surrender index check first — surrender is a one-shot; if the count
    # says surrender, that beats everything else (provided we can).
    if true_count is not None and caps.can_surrender and not soft and not is_pair:
        idx = lookup_surrender(total, col, true_count)
        if idx:
            return BookCall(
                action="surrender", source="index", deviation=idx.label,
            )

    # Pair deviations (TT splits at high counts, etc).
    if true_count is not None and is_pair and caps.can_split:
        a = hand.cards[0]
        key = "T" if is_ten(a.rank) else a.rank
        idx = lookup_pair(key, col, true_count)
        if idx:
            return BookCall(
                action=idx.action, source="index", deviation=idx.label,
            )

    # Hard-total index deviations.
    if true_count is not None and not soft and not is_pair:
        idx = lookup_hard(total, col, true_count)
        if idx:
            # Resolve the index action against capabilities (e.g., can't double
            # if it's a 3-card hand or DAS denied) — fall through to basic if not.
            if _capable_of(idx.action, caps):
                return BookCall(
                    action=idx.action, source="index", deviation=idx.label,
                )

    # No index applied — basic strategy decides.
    return BookCall(action=basic_strategy(hand, dealer_up, rules, caps), source="basic")


def book_insurance(true_count: Optional[float]) -> BookCall:
    """Insurance is its own decision. Default is 'no' (basic strategy never
    takes insurance). Counters take it at TC >= +3.
    """
    if true_count is not None and insurance_correct(true_count):
        return BookCall(
            action="hit",  # placeholder — caller treats it as 'take insurance'
            source="index",
            deviation=f"Insurance at TC>=+3 (current TC={true_count:.2f})",
            note="take insurance",
        )
    return BookCall(action="stand", source="basic", note="decline insurance")


def _capable_of(action: BookAction, caps: Capabilities) -> bool:
    if action == "double":
        return caps.can_double
    if action == "split":
        return caps.can_split
    if action == "surrender":
        return caps.can_surrender
    return True
