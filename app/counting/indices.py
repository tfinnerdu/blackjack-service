"""Illustrious 18 + Fab 4 — the count-based deviations from basic strategy
that capture most of the dollar-EV available to a card counter.

Each entry: (player_total_or_pair, dealer_up_col, action_at_or_above_threshold,
true_count_threshold).

Index lookups are run BEFORE basic strategy. If any matching index applies,
its action wins; otherwise we fall through to the chart.

Notes:
- For 'TT' splits, we handle the pair separately since the player total is 20.
- 'A' is encoded as the dealer column key, matching strategy.charts.
- Insurance is handled by a separate helper since it's a yes/no, not an action.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


Comparator = Literal[">=", "<="]
DealerCol = int | str  # 2..10 or "A"


@dataclass(frozen=True)
class IndexPlay:
    label: str           # human-readable, shown in coach panel
    threshold: float     # true count threshold
    cmp: Comparator      # >= or <=
    action: Literal["hit", "stand", "double", "split", "surrender"]


# Hard-total index deviations: player_total -> dealer_col -> IndexPlay.
HARD_INDEXES: dict[int, dict[DealerCol, IndexPlay]] = {
    16: {
        9: IndexPlay("16 vs 9: stand at TC>=+5", 5, ">=", "stand"),
        10: IndexPlay("16 vs 10: stand at TC>=0", 0, ">=", "stand"),
    },
    15: {
        10: IndexPlay("15 vs 10: stand at TC>=+4", 4, ">=", "stand"),
    },
    13: {
        2: IndexPlay("13 vs 2: stand at TC>=-1", -1, ">=", "stand"),
        3: IndexPlay("13 vs 3: stand at TC>=-2", -2, ">=", "stand"),
    },
    12: {
        2: IndexPlay("12 vs 2: stand at TC>=+3", 3, ">=", "stand"),
        3: IndexPlay("12 vs 3: stand at TC>=+2", 2, ">=", "stand"),
        4: IndexPlay("12 vs 4: stand at TC>=0",  0, ">=", "stand"),
        5: IndexPlay("12 vs 5: stand at TC>=-2",-2, ">=", "stand"),
        6: IndexPlay("12 vs 6: stand at TC>=-1",-1, ">=", "stand"),
    },
    11: {
        "A": IndexPlay("11 vs A: double at TC>=+1", 1, ">=", "double"),
    },
    10: {
        10: IndexPlay("10 vs 10: double at TC>=+4", 4, ">=", "double"),
        "A": IndexPlay("10 vs A: double at TC>=+4", 4, ">=", "double"),
    },
    9: {
        2: IndexPlay("9 vs 2: double at TC>=+1", 1, ">=", "double"),
        7: IndexPlay("9 vs 7: double at TC>=+3", 3, ">=", "double"),
    },
}

# Pair deviations (player has TT vs small dealer up — split for an edge).
PAIR_INDEXES: dict[str, dict[DealerCol, IndexPlay]] = {
    "T": {
        5: IndexPlay("TT vs 5: split at TC>=+5", 5, ">=", "split"),
        6: IndexPlay("TT vs 6: split at TC>=+4", 4, ">=", "split"),
    },
}

# Fab 4 surrender deviations. Threshold-met -> surrender. Encoded into HARD_INDEXES
# above only where they collapse cleanly; the dedicated surrender map keeps
# the four well-known deviations explicit.
SURRENDER_INDEXES: dict[int, dict[DealerCol, IndexPlay]] = {
    14: {
        10: IndexPlay("14 vs 10: surrender at TC>=+3", 3, ">=", "surrender"),
    },
    15: {
        9: IndexPlay("15 vs 9: surrender at TC>=+2", 2, ">=", "surrender"),
        10: IndexPlay("15 vs 10: surrender at TC>=0", 0, ">=", "surrender"),
        "A": IndexPlay("15 vs A: surrender at TC>=+1 (H17)", 1, ">=", "surrender"),
    },
}


# Insurance threshold: take insurance at TC >= +3 (Hi-Lo).
INSURANCE_THRESHOLD: float = 3.0


def insurance_correct(true_count: float) -> bool:
    return true_count >= INSURANCE_THRESHOLD


def _matches(idx: IndexPlay, true_count: float) -> bool:
    if idx.cmp == ">=":
        return true_count >= idx.threshold
    return true_count <= idx.threshold


def lookup_hard(player_total: int, dealer_col: DealerCol, true_count: float) -> Optional[IndexPlay]:
    plays = HARD_INDEXES.get(player_total, {})
    idx = plays.get(dealer_col)
    if idx and _matches(idx, true_count):
        return idx
    return None


def lookup_pair(pair_rank: str, dealer_col: DealerCol, true_count: float) -> Optional[IndexPlay]:
    plays = PAIR_INDEXES.get(pair_rank, {})
    idx = plays.get(dealer_col)
    if idx and _matches(idx, true_count):
        return idx
    return None


def lookup_surrender(player_total: int, dealer_col: DealerCol, true_count: float) -> Optional[IndexPlay]:
    plays = SURRENDER_INDEXES.get(player_total, {})
    idx = plays.get(dealer_col)
    if idx and _matches(idx, true_count):
        return idx
    return None
