"""Roulette wheel + bets.

A `Spin` is the random pocket landed for one round. `settle_bets` takes
a list of `Bet` objects against a Spin and returns the per-bet profit
(positive = won, negative = lost, zero = push for surrender-style rules
which we don't model in v1).

Payouts are stored as (numerator, denominator) tuples so they can be
overridden per session — same shape blackjack uses for its payout
fields. Default tables match the standard American / European house.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Literal, Optional


# ---- pockets + colors --------------------------------------------------

class WheelKind(str, Enum):
    AMERICAN = "american"   # 38 pockets: 0, 00, 1..36
    EUROPEAN = "european"   # 37 pockets: 0, 1..36


# Pocket is the raw label landed: integers 0..36 plus "00" for the
# American wheel. Stored as a string so "00" survives the round-trip.
Pocket = str

AMERICAN_POCKETS: tuple[Pocket, ...] = ("0", "00") + tuple(str(i) for i in range(1, 37))
EUROPEAN_POCKETS: tuple[Pocket, ...] = ("0",) + tuple(str(i) for i in range(1, 37))

# Standard red numbers — black is "the rest of 1..36"; 0 + 00 are green.
_RED_SET: frozenset[int] = frozenset({
    1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36,
})


def is_red(pocket: Pocket) -> bool:
    if pocket in ("0", "00"):
        return False
    try:
        return int(pocket) in _RED_SET
    except ValueError:
        return False


def pocket_color(pocket: Pocket) -> Literal["red", "black", "green"]:
    if pocket in ("0", "00"):
        return "green"
    return "red" if is_red(pocket) else "black"


# ---- bet types + default payouts --------------------------------------

class BetType(str, Enum):
    """Each bet kind we support. The `selection` on a Bet is the
    type-specific payload — a number, a list of numbers, a color, etc."""
    STRAIGHT = "straight"        # single number; selection = pocket str
    SPLIT = "split"              # two adjacent numbers; selection = list[2]
    STREET = "street"            # row of 3; selection = list[3]
    CORNER = "corner"            # 4 numbers; selection = list[4]
    SIX_LINE = "six_line"        # 2 streets; selection = list[6]
    DOZEN = "dozen"              # 1, 2, or 3 (1-12 / 13-24 / 25-36)
    COLUMN = "column"            # 1, 2, or 3 (column of the layout)
    RED = "red"
    BLACK = "black"
    EVEN = "even"
    ODD = "odd"
    LOW = "low"                  # 1-18
    HIGH = "high"                # 19-36


# (numerator, denominator). Profit = stake * num // den. Stake is
# returned to the player on top of profit on a win; lost on a loss.
Payout = tuple[int, int]

_BASE_PAYOUTS: dict[BetType, Payout] = {
    BetType.STRAIGHT: (35, 1),
    BetType.SPLIT: (17, 1),
    BetType.STREET: (11, 1),
    BetType.CORNER: (8, 1),
    BetType.SIX_LINE: (5, 1),
    BetType.DOZEN: (2, 1),
    BetType.COLUMN: (2, 1),
    BetType.RED: (1, 1),
    BetType.BLACK: (1, 1),
    BetType.EVEN: (1, 1),
    BetType.ODD: (1, 1),
    BetType.LOW: (1, 1),
    BetType.HIGH: (1, 1),
}

# American + European share the same payout table; the difference is
# the wheel itself (extra 00 changes the house edge from 2.7% to 5.26%).
AMERICAN_PAYOUTS: dict[BetType, Payout] = dict(_BASE_PAYOUTS)
EUROPEAN_PAYOUTS: dict[BetType, Payout] = dict(_BASE_PAYOUTS)


# ---- bet model ---------------------------------------------------------

@dataclass
class Bet:
    """One wager. `selection` is type-specific:

      - STRAIGHT: pocket string ("0" / "00" / "1".."36")
      - SPLIT / STREET / CORNER / SIX_LINE: list of pocket strings
      - DOZEN / COLUMN: int 1, 2, or 3
      - RED / BLACK / EVEN / ODD / LOW / HIGH: ignored (None)

    The engine doesn't enforce that adjacent numbers really are
    adjacent on the layout — splits across non-adjacent numbers will
    still settle correctly, they'll just lose more often than the
    payout assumes.
    """
    bet_type: BetType
    stake: int
    selection: object | None = None

    def to_dict(self) -> dict:
        return {
            "bet_type": self.bet_type.value,
            "stake": self.stake,
            "selection": self.selection,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Bet":
        return cls(
            bet_type=BetType(d["bet_type"]),
            stake=int(d["stake"]),
            selection=d.get("selection"),
        )


# ---- spin --------------------------------------------------------------

@dataclass
class Spin:
    """Result of a single wheel spin."""
    pocket: Pocket
    color: Literal["red", "black", "green"]
    is_zero: bool

    def to_dict(self) -> dict:
        return {"pocket": self.pocket, "color": self.color, "is_zero": self.is_zero}


@dataclass
class SpinResult:
    """A spin + per-bet outcomes. `payouts` parallels `bets`."""
    spin: Spin
    bets: list[Bet]
    payouts: list[int]   # profit per bet (positive = won, negative = lost)

    @property
    def total_profit(self) -> int:
        return sum(self.payouts)

    def to_dict(self) -> dict:
        return {
            "spin": self.spin.to_dict(),
            "bets": [b.to_dict() for b in self.bets],
            "payouts": list(self.payouts),
            "total_profit": self.total_profit,
        }


class Wheel:
    """Spin source. Seeded for determinism — same seed + same number of
    spins always yields the same sequence."""

    def __init__(self, kind: WheelKind = WheelKind.AMERICAN, seed: Optional[int] = None):
        self.kind = kind
        self._rng = random.Random(seed)
        self._pockets = AMERICAN_POCKETS if kind == WheelKind.AMERICAN else EUROPEAN_POCKETS

    def spin(self) -> Spin:
        pocket = self._rng.choice(self._pockets)
        return Spin(
            pocket=pocket,
            color=pocket_color(pocket),
            is_zero=pocket in ("0", "00"),
        )


def spin_wheel(kind: WheelKind, seed: Optional[int] = None) -> Spin:
    """Convenience wrapper that constructs a Wheel and spins once. Used
    for one-off resolution where keeping a wheel around isn't useful."""
    return Wheel(kind, seed=seed).spin()


# ---- settlement --------------------------------------------------------

def _bet_wins(bet: Bet, spin: Spin) -> bool:
    """Whether `bet` wins given `spin`."""
    sel = bet.selection
    p = spin.pocket

    if bet.bet_type == BetType.STRAIGHT:
        return str(sel) == p

    if bet.bet_type in (BetType.SPLIT, BetType.STREET, BetType.CORNER, BetType.SIX_LINE):
        if not isinstance(sel, (list, tuple)):
            return False
        return p in [str(s) for s in sel]

    # 0 and 00 lose every outside bet — that's where the house edge
    # comes from. Cover that first.
    if spin.is_zero:
        return False

    n = int(p)

    if bet.bet_type == BetType.DOZEN:
        if sel == 1:
            return 1 <= n <= 12
        if sel == 2:
            return 13 <= n <= 24
        if sel == 3:
            return 25 <= n <= 36
        return False

    if bet.bet_type == BetType.COLUMN:
        # Column 1: 1, 4, 7, ..., 34. Column 2: 2, 5, ..., 35. Column 3: 3, 6, ..., 36.
        if sel not in (1, 2, 3):
            return False
        return n % 3 == (sel % 3)

    if bet.bet_type == BetType.RED:
        return spin.color == "red"
    if bet.bet_type == BetType.BLACK:
        return spin.color == "black"
    if bet.bet_type == BetType.EVEN:
        return n % 2 == 0
    if bet.bet_type == BetType.ODD:
        return n % 2 == 1
    if bet.bet_type == BetType.LOW:
        return 1 <= n <= 18
    if bet.bet_type == BetType.HIGH:
        return 19 <= n <= 36

    return False


def _payout_amount(stake: int, payout: tuple[int, int]) -> int:
    num, den = payout
    return stake * num // den


def settle_bets(
    spin: Spin,
    bets: Iterable[Bet],
    *,
    payouts: Optional[dict[BetType, Payout]] = None,
) -> SpinResult:
    """Resolve every bet against a spin. Returns the per-bet profit
    (winning bets net `stake * payout`; losers lose their `stake`).
    Stake is conceptually wagered and returned on a win — the integer
    we report here is the *delta* to the bettor's bankroll."""
    table = payouts or _BASE_PAYOUTS
    bets_list = list(bets)
    deltas: list[int] = []
    for b in bets_list:
        if b.stake <= 0:
            deltas.append(0)
            continue
        if _bet_wins(b, spin):
            deltas.append(_payout_amount(b.stake, table.get(b.bet_type, (1, 1))))
        else:
            deltas.append(-b.stake)
    return SpinResult(spin=spin, bets=bets_list, payouts=deltas)
