"""Basic strategy resolver. Public entrypoint:

    basic_strategy(hand, dealer_up, rules, capabilities) -> Action

The chart layer (charts.py) returns shorthand cells like 'Dh' (double else hit);
this module resolves those into concrete actions ('hit'/'stand'/'double'/etc.)
based on what's actually allowed for the current hand.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..engine.cards import Card, hand_total, is_ten
from ..engine.hand import Hand
from ..engine.rules import Rules
from .charts import (
    HARD_H17,
    HARD_S17,
    PAIRS_H17,
    PAIRS_S17,
    SOFT_H17,
    SOFT_S17,
    dealer_column,
)


# Concrete actions the resolver can return. Matches engine.round.Action plus
# 'insurance' for the optional insurance question.
BookAction = Literal["hit", "stand", "double", "split", "surrender"]


@dataclass
class Capabilities:
    """What's actually allowed for the active hand. The resolver collapses
    chart cells against these."""
    can_double: bool
    can_split: bool
    can_surrender: bool


def _resolve_cell(cell: str, caps: Capabilities, das_allowed: bool) -> BookAction:
    """Translate a chart cell into a final action, falling back to the 'else'
    half of compound cells when the action isn't legal here."""
    if cell == "H":
        return "hit"
    if cell == "S":
        return "stand"
    if cell == "P":
        return "split" if caps.can_split else "hit"
    if cell == "Dh":
        return "double" if caps.can_double else "hit"
    if cell == "Ds":
        return "double" if caps.can_double else "stand"
    if cell == "Ph":
        # Split if DAS allowed AND we're allowed to split here, else hit.
        return "split" if (das_allowed and caps.can_split) else "hit"
    if cell == "Rh":
        return "surrender" if caps.can_surrender else "hit"
    if cell == "Rs":
        return "surrender" if caps.can_surrender else "stand"
    if cell == "Rp":
        return "surrender" if caps.can_surrender else (
            "split" if caps.can_split else "hit"
        )
    raise ValueError(f"unknown chart cell: {cell!r}")


def basic_strategy(
    hand: Hand,
    dealer_up: Card,
    rules: Rules,
    caps: Capabilities,
) -> BookAction:
    """The book play for this hand under these rules. No counting awareness."""
    h17 = rules.dealer_hits_soft_17
    hard_chart = HARD_H17 if h17 else HARD_S17
    soft_chart = SOFT_H17 if h17 else SOFT_S17
    pair_chart = PAIRS_H17 if h17 else PAIRS_S17
    col = dealer_column(dealer_up.rank)

    # Pair lookup first (only on first two cards, both same value).
    if len(hand.cards) == 2 and caps.can_split:
        a, b = hand.cards
        if a.rank == b.rank or (is_ten(a.rank) and is_ten(b.rank)):
            # Pair charts key by rank symbol; tens collapse to "T".
            key = "T" if is_ten(a.rank) else a.rank
            cell = pair_chart[key][col]
            return _resolve_cell(cell, caps, rules.double_after_split)

    total, soft = hand_total(hand.cards)

    # Soft totals chart only covers 13..20; soft 21 just stands.
    if soft and 13 <= total <= 20:
        cell = soft_chart[total][col]
        return _resolve_cell(cell, caps, rules.double_after_split)

    # Hard totals: clamp below 5 and above 21 (bust handled upstream).
    if total < 5:
        return "hit"
    if total > 21:
        return "stand"  # bust — defensive
    cell = hard_chart[total][col]
    return _resolve_cell(cell, caps, rules.double_after_split)
