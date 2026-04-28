"""Craps engine.

State machine: between rounds, the table is in COME_OUT phase. The
shooter rolls. On a come-out roll:
  - 7 / 11 → Pass Line wins; Don't Pass loses (12 pushes Don't Pass).
  - 2 / 3 / 12 → Pass Line loses; Don't Pass wins on 2/3, pushes on 12.
  - 4-6, 8-10 → that becomes the POINT; phase flips to POINT_ON.

While the point is on:
  - Roll the point → Pass Line wins; Don't Pass loses.
  - Roll a 7 → "seven-out": Pass Line loses; Don't Pass wins. Phase
    returns to COME_OUT.
  - Other rolls → no-op for line bets, but place / hard-way / one-roll
    bets resolve.

Bet types implemented (v1):
  - PASS_LINE / DONT_PASS (line bets)
  - PASS_ODDS / DONT_PASS_ODDS (true-odds, only legal once a point is on)
  - COME / DONT_COME — like pass/don't-pass but established on a per-bet
    basis after the point is set
  - PLACE_4..PLACE_10 — bet a specific number; pays if it rolls before 7
  - FIELD — one-roll bet on 2/3/4/9/10/11/12, with 2x on 2 and 3x on 12
  - ANY_SEVEN — one-roll bet that the next roll is a 7 (pays 4:1)
  - ANY_CRAPS — one-roll on 2/3/12 (pays 7:1)
  - HARD_4 / HARD_6 / HARD_8 / HARD_10 — pair-of-Ns before a 7 OR an
    "easy" version of N (e.g. 6 = 5+1 is easy, 3+3 is hard)

This gives the most common live-table experience without modeling
every prop bet. Future additions: lay bets, big 6/8, hop bets.
"""
from .table import (
    Bet,
    BetType,
    CrapsRules,
    CrapsTable,
    Phase,
    Roll,
    RollResult,
    create_table,
    resolve_roll,
    roll_dice,
)

__all__ = [
    "Bet",
    "BetType",
    "CrapsRules",
    "CrapsTable",
    "Phase",
    "Roll",
    "RollResult",
    "create_table",
    "resolve_roll",
    "roll_dice",
]
