"""Basic strategy charts. Multi-deck (4-8) charts for H17 and S17, with DAS
toggled separately. Single-deck has small variations we treat as a deviation
layer (TODO phase 3.1).

Encoding (chart cell values):
  H   = hit
  S   = stand
  Dh  = double if allowed, else hit
  Ds  = double if allowed, else stand
  P   = split
  Ph  = split if DAS allowed, else hit
  Rh  = surrender if allowed, else hit
  Rs  = surrender if allowed, else stand
  Rp  = surrender if allowed, else split

The dealer up-card columns are keyed by integer 2..10 plus 'A'. Tens (T/J/Q/K)
all map to column 10.
"""
from __future__ import annotations

from typing import Literal


ChartCell = Literal["H", "S", "Dh", "Ds", "P", "Ph", "Rh", "Rs", "Rp"]
DealerCol = int | str  # 2..10 or "A"

DEALER_COLS: tuple[DealerCol, ...] = (2, 3, 4, 5, 6, 7, 8, 9, 10, "A")


def _row(*cells: ChartCell) -> dict[DealerCol, ChartCell]:
    if len(cells) != len(DEALER_COLS):
        raise ValueError(f"chart row has {len(cells)} cells, expected {len(DEALER_COLS)}")
    return dict(zip(DEALER_COLS, cells))


# ----------------------------------------------------------------------
# H17 (dealer hits soft 17)
# ----------------------------------------------------------------------

HARD_H17: dict[int, dict[DealerCol, ChartCell]] = {
    #          2    3    4    5    6    7    8    9    10   A
    5:  _row("H", "H", "H", "H", "H", "H", "H", "H", "H", "H"),
    6:  _row("H", "H", "H", "H", "H", "H", "H", "H", "H", "H"),
    7:  _row("H", "H", "H", "H", "H", "H", "H", "H", "H", "H"),
    8:  _row("H", "H", "H", "H", "H", "H", "H", "H", "H", "H"),
    9:  _row("H", "Dh","Dh","Dh","Dh","H", "H", "H", "H", "H"),
    10: _row("Dh","Dh","Dh","Dh","Dh","Dh","Dh","Dh","H", "H"),
    11: _row("Dh","Dh","Dh","Dh","Dh","Dh","Dh","Dh","Dh","Dh"),  # H17: double 11 vs A
    12: _row("H", "H", "S", "S", "S", "H", "H", "H", "H", "H"),
    13: _row("S", "S", "S", "S", "S", "H", "H", "H", "H", "H"),
    14: _row("S", "S", "S", "S", "S", "H", "H", "H", "H", "H"),
    15: _row("S", "S", "S", "S", "S", "H", "H", "H", "Rh","Rh"), # H17: 15 vs A surrender
    16: _row("S", "S", "S", "S", "S", "H", "H", "Rh","Rh","Rh"),
    17: _row("S", "S", "S", "S", "S", "S", "S", "S", "S", "Rs"), # H17: 17 vs A surrender
    18: _row("S", "S", "S", "S", "S", "S", "S", "S", "S", "S"),
    19: _row("S", "S", "S", "S", "S", "S", "S", "S", "S", "S"),
    20: _row("S", "S", "S", "S", "S", "S", "S", "S", "S", "S"),
    21: _row("S", "S", "S", "S", "S", "S", "S", "S", "S", "S"),
}

# Soft totals keyed by total (13 = A2, 14 = A3, ... 20 = A9). Soft 21 = blackjack
# never reaches the resolver since it's flagged finished at deal time.
SOFT_H17: dict[int, dict[DealerCol, ChartCell]] = {
    13: _row("H", "H", "H", "Dh","Dh","H", "H", "H", "H", "H"),  # A,2
    14: _row("H", "H", "H", "Dh","Dh","H", "H", "H", "H", "H"),  # A,3
    15: _row("H", "H", "Dh","Dh","Dh","H", "H", "H", "H", "H"),  # A,4
    16: _row("H", "H", "Dh","Dh","Dh","H", "H", "H", "H", "H"),  # A,5
    17: _row("H", "Dh","Dh","Dh","Dh","H", "H", "H", "H", "H"),  # A,6
    18: _row("Ds","Ds","Ds","Ds","Ds","S", "S", "H", "H", "H"),  # A,7 — H17 doubles vs 2
    19: _row("S", "S", "S", "S", "Ds","S", "S", "S", "S", "S"),  # A,8 — H17 doubles vs 6
    20: _row("S", "S", "S", "S", "S", "S", "S", "S", "S", "S"),  # A,9
}

PAIRS_H17: dict[str, dict[DealerCol, ChartCell]] = {
    "2": _row("Ph","Ph","P", "P", "P", "P", "H", "H", "H", "H"),
    "3": _row("Ph","Ph","P", "P", "P", "P", "H", "H", "H", "H"),
    "4": _row("H", "H", "H", "Ph","Ph","H", "H", "H", "H", "H"),
    "5": _row("Dh","Dh","Dh","Dh","Dh","Dh","Dh","Dh","H", "H"),  # treated as 10
    "6": _row("Ph","P", "P", "P", "P", "H", "H", "H", "H", "H"),
    "7": _row("P", "P", "P", "P", "P", "P", "H", "H", "H", "H"),
    "8": _row("P", "P", "P", "P", "P", "P", "P", "P", "P", "Rp"),  # H17: 8,8 vs A surrender else split
    "9": _row("P", "P", "P", "P", "P", "S", "P", "P", "S", "S"),
    "T": _row("S", "S", "S", "S", "S", "S", "S", "S", "S", "S"),
    "A": _row("P", "P", "P", "P", "P", "P", "P", "P", "P", "P"),
}


# ----------------------------------------------------------------------
# S17 (dealer stands soft 17)
# ----------------------------------------------------------------------

HARD_S17: dict[int, dict[DealerCol, ChartCell]] = {
    5:  _row("H", "H", "H", "H", "H", "H", "H", "H", "H", "H"),
    6:  _row("H", "H", "H", "H", "H", "H", "H", "H", "H", "H"),
    7:  _row("H", "H", "H", "H", "H", "H", "H", "H", "H", "H"),
    8:  _row("H", "H", "H", "H", "H", "H", "H", "H", "H", "H"),
    9:  _row("H", "Dh","Dh","Dh","Dh","H", "H", "H", "H", "H"),
    10: _row("Dh","Dh","Dh","Dh","Dh","Dh","Dh","Dh","H", "H"),
    11: _row("Dh","Dh","Dh","Dh","Dh","Dh","Dh","Dh","Dh","H"),  # S17: 11 vs A is hit
    12: _row("H", "H", "S", "S", "S", "H", "H", "H", "H", "H"),
    13: _row("S", "S", "S", "S", "S", "H", "H", "H", "H", "H"),
    14: _row("S", "S", "S", "S", "S", "H", "H", "H", "H", "H"),
    15: _row("S", "S", "S", "S", "S", "H", "H", "H", "Rh","H"),  # S17: 15 vs A is hit
    16: _row("S", "S", "S", "S", "S", "H", "H", "Rh","Rh","Rh"),
    17: _row("S", "S", "S", "S", "S", "S", "S", "S", "S", "S"),  # S17: 17 vs A is stand
    18: _row("S", "S", "S", "S", "S", "S", "S", "S", "S", "S"),
    19: _row("S", "S", "S", "S", "S", "S", "S", "S", "S", "S"),
    20: _row("S", "S", "S", "S", "S", "S", "S", "S", "S", "S"),
    21: _row("S", "S", "S", "S", "S", "S", "S", "S", "S", "S"),
}

SOFT_S17: dict[int, dict[DealerCol, ChartCell]] = {
    13: _row("H", "H", "H", "Dh","Dh","H", "H", "H", "H", "H"),
    14: _row("H", "H", "H", "Dh","Dh","H", "H", "H", "H", "H"),
    15: _row("H", "H", "Dh","Dh","Dh","H", "H", "H", "H", "H"),
    16: _row("H", "H", "Dh","Dh","Dh","H", "H", "H", "H", "H"),
    17: _row("H", "Dh","Dh","Dh","Dh","H", "H", "H", "H", "H"),
    18: _row("S", "Ds","Ds","Ds","Ds","S", "S", "H", "H", "H"),  # S17: A,7 vs 2 is stand
    19: _row("S", "S", "S", "S", "S", "S", "S", "S", "S", "S"),  # S17: A,8 vs 6 is stand
    20: _row("S", "S", "S", "S", "S", "S", "S", "S", "S", "S"),
}

PAIRS_S17: dict[str, dict[DealerCol, ChartCell]] = {
    "2": _row("Ph","Ph","P", "P", "P", "P", "H", "H", "H", "H"),
    "3": _row("Ph","Ph","P", "P", "P", "P", "H", "H", "H", "H"),
    "4": _row("H", "H", "H", "Ph","Ph","H", "H", "H", "H", "H"),
    "5": _row("Dh","Dh","Dh","Dh","Dh","Dh","Dh","Dh","H", "H"),
    "6": _row("Ph","P", "P", "P", "P", "H", "H", "H", "H", "H"),
    "7": _row("P", "P", "P", "P", "P", "P", "H", "H", "H", "H"),
    "8": _row("P", "P", "P", "P", "P", "P", "P", "P", "P", "P"),  # S17: 8,8 vs A is split
    "9": _row("P", "P", "P", "P", "P", "S", "P", "P", "S", "S"),
    "T": _row("S", "S", "S", "S", "S", "S", "S", "S", "S", "S"),
    "A": _row("P", "P", "P", "P", "P", "P", "P", "P", "P", "P"),
}


def chart_set(h17: bool):
    if h17:
        return HARD_H17, SOFT_H17, PAIRS_H17
    return HARD_S17, SOFT_S17, PAIRS_S17


def dealer_column(rank: str) -> DealerCol:
    """Convert a dealer up-card rank to its chart column."""
    if rank == "A":
        return "A"
    if rank in ("T", "J", "Q", "K"):
        return 10
    return int(rank)
