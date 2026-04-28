"""Poker hand evaluator.

  high.py        5-card high-hand classifier + best-5-from-N
  low.py         A-5 / 2-7 / badugi low-hand evaluators (phase 2.5)
  wilds.py       wild substitution (phase 2.3-2.4)

The high evaluator returns a HandRank that's directly comparable: a higher
value beats a lower one. Within a rank class (e.g. two pair) the kickers
are encoded into the value so a queen-high two pair beats a jack-high.
"""
from .high import (
    HAND_CLASS_NAMES,
    HandClass,
    HandRank,
    best_high,
    classify_high,
)
from .low import LowRank, LowRule, best_low, low_ranks_compare
from .wilds import WildMode, evaluate_with_wilds, joker_indices

__all__ = [
    "HAND_CLASS_NAMES",
    "HandClass",
    "HandRank",
    "LowRank",
    "LowRule",
    "WildMode",
    "best_high",
    "best_low",
    "classify_high",
    "evaluate_with_wilds",
    "joker_indices",
    "low_ranks_compare",
]
