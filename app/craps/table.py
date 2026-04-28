"""Craps state machine + bet resolution.

A `CrapsTable` carries the phase (COME_OUT / POINT_ON), the point if
set, and a book of currently-active bets keyed by bet ID. Each call
to `resolve_roll` advances state by one roll and returns a list of
per-bet outcomes (resolved + remaining).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Optional


# ---- dice -------------------------------------------------------------

@dataclass
class Roll:
    d1: int
    d2: int

    @property
    def total(self) -> int:
        return self.d1 + self.d2

    @property
    def is_hard(self) -> bool:
        """A 'hard' roll is doubles (e.g. 3-3 = hard six)."""
        return self.d1 == self.d2

    def to_dict(self) -> dict:
        return {"d1": self.d1, "d2": self.d2, "total": self.total, "hard": self.is_hard}


def roll_dice(rng: Optional[random.Random] = None) -> Roll:
    rng = rng or random.Random()
    return Roll(rng.randint(1, 6), rng.randint(1, 6))


# ---- phase ------------------------------------------------------------

class Phase(str, Enum):
    COME_OUT = "come_out"
    POINT_ON = "point_on"


# ---- bets -------------------------------------------------------------

class BetType(str, Enum):
    PASS_LINE = "pass_line"
    DONT_PASS = "dont_pass"
    PASS_ODDS = "pass_odds"          # behind-the-line odds (true odds)
    DONT_PASS_ODDS = "dont_pass_odds"
    COME = "come"
    DONT_COME = "dont_come"
    PLACE = "place"                  # selection = number 4/5/6/8/9/10
    FIELD = "field"
    ANY_SEVEN = "any_seven"
    ANY_CRAPS = "any_craps"
    HARD = "hard"                    # selection = 4/6/8/10


# Each bet has an id (so callers can refer to it across rolls), a type,
# stake, optional selection, and an established_point for COME-style
# bets that need to remember which number their bet now travels with.

@dataclass
class Bet:
    bet_id: str
    bet_type: BetType
    stake: int
    selection: Optional[int] = None
    established_point: Optional[int] = None
    # Active = still on the table. For one-roll bets, this flips False
    # after the next roll regardless of result.

    def to_dict(self) -> dict:
        return {
            "bet_id": self.bet_id,
            "bet_type": self.bet_type.value,
            "stake": self.stake,
            "selection": self.selection,
            "established_point": self.established_point,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Bet":
        return cls(
            bet_id=str(d["bet_id"]),
            bet_type=BetType(d["bet_type"]),
            stake=int(d["stake"]),
            selection=d.get("selection"),
            established_point=d.get("established_point"),
        )


# ---- rules + table ----------------------------------------------------

# Standard Bank Craps payouts.
# Place numbers: 4/10 → 9:5, 5/9 → 7:5, 6/8 → 7:6.
PLACE_PAYOUTS: dict[int, tuple[int, int]] = {
    4: (9, 5), 5: (7, 5), 6: (7, 6),
    8: (7, 6), 9: (7, 5), 10: (9, 5),
}

# True odds on the come-out point.
TRUE_ODDS: dict[int, tuple[int, int]] = {
    4: (2, 1), 10: (2, 1),
    5: (3, 2), 9: (3, 2),
    6: (6, 5), 8: (6, 5),
}

# Don't-pass / don't-come odds are the inverse — bettor lays the
# better-paying side, so "wins less than they risk".
LAY_ODDS: dict[int, tuple[int, int]] = {
    4: (1, 2), 10: (1, 2),
    5: (2, 3), 9: (2, 3),
    6: (5, 6), 8: (5, 6),
}

# Hardway payouts: 4/10 = 7:1, 6/8 = 9:1.
HARD_PAYOUTS: dict[int, tuple[int, int]] = {
    4: (7, 1), 10: (7, 1),
    6: (9, 1), 8: (9, 1),
}


@dataclass
class CrapsRules:
    # Some houses pay 3x on field 12 (and only 2x on 2). We default to
    # a typical 2x-2 / 3x-12 paytable.
    field_2_pays: tuple[int, int] = (2, 1)
    field_12_pays: tuple[int, int] = (3, 1)
    any_seven_pays: tuple[int, int] = (4, 1)
    any_craps_pays: tuple[int, int] = (7, 1)
    min_bet: int = 1
    max_bet: int = 500

    def to_dict(self) -> dict:
        return {
            "field_2_pays": list(self.field_2_pays),
            "field_12_pays": list(self.field_12_pays),
            "any_seven_pays": list(self.any_seven_pays),
            "any_craps_pays": list(self.any_craps_pays),
            "min_bet": self.min_bet,
            "max_bet": self.max_bet,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CrapsRules":
        return cls(
            field_2_pays=tuple(d.get("field_2_pays", (2, 1))),
            field_12_pays=tuple(d.get("field_12_pays", (3, 1))),
            any_seven_pays=tuple(d.get("any_seven_pays", (4, 1))),
            any_craps_pays=tuple(d.get("any_craps_pays", (7, 1))),
            min_bet=int(d.get("min_bet", 1)),
            max_bet=int(d.get("max_bet", 500)),
        )


@dataclass
class CrapsTable:
    phase: Phase = Phase.COME_OUT
    point: Optional[int] = None

    def to_dict(self) -> dict:
        return {"phase": self.phase.value, "point": self.point}

    @classmethod
    def from_dict(cls, d: dict) -> "CrapsTable":
        return cls(
            phase=Phase(d.get("phase", "come_out")),
            point=d.get("point"),
        )


def create_table() -> CrapsTable:
    return CrapsTable()


# ---- per-bet outcome -------------------------------------------------

@dataclass
class BetOutcome:
    bet_id: str
    profit: int
    resolved: bool   # if True, bet should be removed from the book after this roll
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "bet_id": self.bet_id,
            "profit": self.profit,
            "resolved": self.resolved,
            "note": self.note,
        }


@dataclass
class RollResult:
    roll: Roll
    phase_before: Phase
    phase_after: Phase
    point_before: Optional[int]
    point_after: Optional[int]
    outcomes: list[BetOutcome] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "roll": self.roll.to_dict(),
            "phase_before": self.phase_before.value,
            "phase_after": self.phase_after.value,
            "point_before": self.point_before,
            "point_after": self.point_after,
            "outcomes": [o.to_dict() for o in self.outcomes],
            "total_profit": sum(o.profit for o in self.outcomes),
        }


# ---- payout helpers --------------------------------------------------

def _pay(stake: int, payout: tuple[int, int]) -> int:
    n, d = payout
    return stake * n // d


# ---- per-bet resolution ----------------------------------------------

def _resolve_pass_line(bet: Bet, table: CrapsTable, total: int) -> BetOutcome:
    if table.phase == Phase.COME_OUT:
        if total in (7, 11):
            return BetOutcome(bet.bet_id, bet.stake, True, "pass: natural")
        if total in (2, 3, 12):
            return BetOutcome(bet.bet_id, -bet.stake, True, "pass: craps")
        # Establishes the point — the bet stays on the table.
        return BetOutcome(bet.bet_id, 0, False, f"pass: point {total}")
    # POINT_ON — resolve against the point.
    if total == table.point:
        return BetOutcome(bet.bet_id, bet.stake, True, "pass: point made")
    if total == 7:
        return BetOutcome(bet.bet_id, -bet.stake, True, "pass: seven-out")
    return BetOutcome(bet.bet_id, 0, False, "pass: roll-by")


def _resolve_dont_pass(bet: Bet, table: CrapsTable, total: int) -> BetOutcome:
    if table.phase == Phase.COME_OUT:
        if total in (7, 11):
            return BetOutcome(bet.bet_id, -bet.stake, True, "dont: natural")
        if total in (2, 3):
            return BetOutcome(bet.bet_id, bet.stake, True, "dont: craps win")
        if total == 12:
            return BetOutcome(bet.bet_id, 0, True, "dont: 12 pushes")
        return BetOutcome(bet.bet_id, 0, False, f"dont: point {total}")
    if total == table.point:
        return BetOutcome(bet.bet_id, -bet.stake, True, "dont: point made")
    if total == 7:
        return BetOutcome(bet.bet_id, bet.stake, True, "dont: seven-out wins dont")
    return BetOutcome(bet.bet_id, 0, False, "dont: roll-by")


def _resolve_pass_odds(bet: Bet, table: CrapsTable, total: int) -> BetOutcome:
    if table.phase == Phase.COME_OUT or table.point is None:
        # Odds are returned (no profit, no loss) when the line bet is
        # still establishing — they're not in play.
        return BetOutcome(bet.bet_id, 0, False, "pass odds: no point yet")
    if total == table.point:
        return BetOutcome(bet.bet_id, _pay(bet.stake, TRUE_ODDS[table.point]),
                          True, "pass odds: hit")
    if total == 7:
        return BetOutcome(bet.bet_id, -bet.stake, True, "pass odds: seven-out")
    return BetOutcome(bet.bet_id, 0, False, "pass odds: roll-by")


def _resolve_dont_pass_odds(bet: Bet, table: CrapsTable, total: int) -> BetOutcome:
    if table.phase == Phase.COME_OUT or table.point is None:
        return BetOutcome(bet.bet_id, 0, False, "dont odds: no point yet")
    if total == table.point:
        return BetOutcome(bet.bet_id, -bet.stake, True, "dont odds: point made")
    if total == 7:
        return BetOutcome(bet.bet_id, _pay(bet.stake, LAY_ODDS[table.point]),
                          True, "dont odds: seven-out")
    return BetOutcome(bet.bet_id, 0, False, "dont odds: roll-by")


def _resolve_come(bet: Bet, total: int) -> tuple[BetOutcome, Optional[int]]:
    """Returns (outcome, established_point_or_None). If the bet just
    established a point, established_point is the new point and the
    bet remains on the book with that selection."""
    if bet.established_point is None:
        # Behaves like a Pass Line on its own come-out.
        if total in (7, 11):
            return BetOutcome(bet.bet_id, bet.stake, True, "come: natural"), None
        if total in (2, 3, 12):
            return BetOutcome(bet.bet_id, -bet.stake, True, "come: craps"), None
        return BetOutcome(bet.bet_id, 0, False, f"come: point {total}"), total
    if total == bet.established_point:
        return BetOutcome(bet.bet_id, bet.stake, True, "come: point made"), None
    if total == 7:
        return BetOutcome(bet.bet_id, -bet.stake, True, "come: seven-out"), None
    return BetOutcome(bet.bet_id, 0, False, "come: roll-by"), None


def _resolve_dont_come(bet: Bet, total: int) -> tuple[BetOutcome, Optional[int]]:
    if bet.established_point is None:
        if total in (7, 11):
            return BetOutcome(bet.bet_id, -bet.stake, True, "dont come: natural"), None
        if total in (2, 3):
            return BetOutcome(bet.bet_id, bet.stake, True, "dont come: craps win"), None
        if total == 12:
            return BetOutcome(bet.bet_id, 0, True, "dont come: 12 pushes"), None
        return BetOutcome(bet.bet_id, 0, False, f"dont come: point {total}"), total
    if total == bet.established_point:
        return BetOutcome(bet.bet_id, -bet.stake, True, "dont come: point made"), None
    if total == 7:
        return BetOutcome(bet.bet_id, bet.stake, True, "dont come: seven wins"), None
    return BetOutcome(bet.bet_id, 0, False, "dont come: roll-by"), None


def _resolve_place(bet: Bet, total: int) -> BetOutcome:
    if bet.selection not in PLACE_PAYOUTS:
        return BetOutcome(bet.bet_id, -bet.stake, True,
                          f"place: invalid selection {bet.selection}")
    if total == bet.selection:
        return BetOutcome(bet.bet_id, _pay(bet.stake, PLACE_PAYOUTS[bet.selection]),
                          True, f"place {bet.selection}: hit")
    if total == 7:
        return BetOutcome(bet.bet_id, -bet.stake, True, "place: seven-out")
    return BetOutcome(bet.bet_id, 0, False, "place: roll-by")


def _resolve_field(bet: Bet, total: int, rules: CrapsRules) -> BetOutcome:
    if total == 2:
        return BetOutcome(bet.bet_id, _pay(bet.stake, rules.field_2_pays),
                          True, "field: 2")
    if total == 12:
        return BetOutcome(bet.bet_id, _pay(bet.stake, rules.field_12_pays),
                          True, "field: 12")
    if total in (3, 4, 9, 10, 11):
        return BetOutcome(bet.bet_id, bet.stake, True, "field: hit 1:1")
    return BetOutcome(bet.bet_id, -bet.stake, True, "field: miss")


def _resolve_any_seven(bet: Bet, total: int, rules: CrapsRules) -> BetOutcome:
    if total == 7:
        return BetOutcome(bet.bet_id, _pay(bet.stake, rules.any_seven_pays),
                          True, "any 7: hit")
    return BetOutcome(bet.bet_id, -bet.stake, True, "any 7: miss")


def _resolve_any_craps(bet: Bet, total: int, rules: CrapsRules) -> BetOutcome:
    if total in (2, 3, 12):
        return BetOutcome(bet.bet_id, _pay(bet.stake, rules.any_craps_pays),
                          True, "any craps: hit")
    return BetOutcome(bet.bet_id, -bet.stake, True, "any craps: miss")


def _resolve_hard(bet: Bet, roll: Roll) -> BetOutcome:
    n = bet.selection
    if n not in HARD_PAYOUTS:
        return BetOutcome(bet.bet_id, -bet.stake, True,
                          f"hard: invalid {n}")
    if roll.total == n and roll.is_hard:
        return BetOutcome(bet.bet_id, _pay(bet.stake, HARD_PAYOUTS[n]),
                          True, f"hard {n}: hit")
    if roll.total == n and not roll.is_hard:
        return BetOutcome(bet.bet_id, -bet.stake, True, f"hard {n}: easy")
    if roll.total == 7:
        return BetOutcome(bet.bet_id, -bet.stake, True, "hard: seven-out")
    return BetOutcome(bet.bet_id, 0, False, "hard: roll-by")


# ---- orchestrator -----------------------------------------------------

def resolve_roll(table: CrapsTable, roll: Roll, bets: Iterable[Bet],
                 rules: Optional[CrapsRules] = None) -> RollResult:
    """Apply `roll` to `table` + `bets`, returning the per-bet outcomes
    and the post-roll table state. Bets that resolved are flagged
    `resolved=True`; the caller should remove them from its book.
    Bets that established a come-point have their `established_point`
    mutated in place so they carry forward correctly.
    """
    rules = rules or CrapsRules()
    phase_before = table.phase
    point_before = table.point
    outcomes: list[BetOutcome] = []
    total = roll.total

    for bet in bets:
        if bet.bet_type == BetType.PASS_LINE:
            outcomes.append(_resolve_pass_line(bet, table, total))
        elif bet.bet_type == BetType.DONT_PASS:
            outcomes.append(_resolve_dont_pass(bet, table, total))
        elif bet.bet_type == BetType.PASS_ODDS:
            outcomes.append(_resolve_pass_odds(bet, table, total))
        elif bet.bet_type == BetType.DONT_PASS_ODDS:
            outcomes.append(_resolve_dont_pass_odds(bet, table, total))
        elif bet.bet_type == BetType.COME:
            o, new_point = _resolve_come(bet, total)
            if new_point is not None:
                bet.established_point = new_point
            outcomes.append(o)
        elif bet.bet_type == BetType.DONT_COME:
            o, new_point = _resolve_dont_come(bet, total)
            if new_point is not None:
                bet.established_point = new_point
            outcomes.append(o)
        elif bet.bet_type == BetType.PLACE:
            outcomes.append(_resolve_place(bet, total))
        elif bet.bet_type == BetType.FIELD:
            outcomes.append(_resolve_field(bet, total, rules))
        elif bet.bet_type == BetType.ANY_SEVEN:
            outcomes.append(_resolve_any_seven(bet, total, rules))
        elif bet.bet_type == BetType.ANY_CRAPS:
            outcomes.append(_resolve_any_craps(bet, total, rules))
        elif bet.bet_type == BetType.HARD:
            outcomes.append(_resolve_hard(bet, roll))
        else:
            outcomes.append(BetOutcome(bet.bet_id, 0, True,
                                       f"unknown bet type {bet.bet_type}"))

    # Advance table state.
    if table.phase == Phase.COME_OUT:
        if total in (4, 5, 6, 8, 9, 10):
            table.phase = Phase.POINT_ON
            table.point = total
    else:  # POINT_ON
        if total == table.point or total == 7:
            table.phase = Phase.COME_OUT
            table.point = None

    return RollResult(
        roll=roll,
        phase_before=phase_before,
        phase_after=table.phase,
        point_before=point_before,
        point_after=table.point,
        outcomes=outcomes,
    )
