"""Roulette engine tests. Covers:

  - Pocket coloring (red / black / green)
  - Straight-up payouts (35:1)
  - Outside bets win/lose against sample spins
  - 0 / 00 lose every outside bet (house edge sanity)
  - Wheel seeded determinism
  - Empirical hit rates over many spins land near theoretical
"""
from __future__ import annotations

import pytest

from app.roulette import (
    AMERICAN_POCKETS,
    Bet,
    BetType,
    EUROPEAN_POCKETS,
    Spin,
    Wheel,
    WheelKind,
    is_red,
    pocket_color,
    settle_bets,
)


def _spin(pocket: str) -> Spin:
    return Spin(pocket=pocket, color=pocket_color(pocket), is_zero=pocket in ("0", "00"))


# ---- coloring ----------------------------------------------------------

def test_pocket_colors_match_published_table():
    # Standard reds: 1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36
    reds = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
    for n in range(1, 37):
        assert is_red(str(n)) == (n in reds), (
            f"pocket {n} red mismatch (expected {n in reds})"
        )
    assert pocket_color("0") == "green"
    assert pocket_color("00") == "green"
    assert pocket_color("17") == "black"
    assert pocket_color("18") == "red"


# ---- straight bets -----------------------------------------------------

def test_straight_bet_pays_35_to_1_on_hit():
    bet = Bet(bet_type=BetType.STRAIGHT, stake=10, selection="17")
    res = settle_bets(_spin("17"), [bet])
    assert res.payouts == [350]


def test_straight_bet_loses_stake_on_miss():
    bet = Bet(bet_type=BetType.STRAIGHT, stake=10, selection="17")
    res = settle_bets(_spin("18"), [bet])
    assert res.payouts == [-10]


def test_straight_bet_on_0_pays_when_0_lands():
    bet = Bet(bet_type=BetType.STRAIGHT, stake=5, selection="0")
    res = settle_bets(_spin("0"), [bet])
    assert res.payouts == [175]


# ---- outside bets ------------------------------------------------------

def test_red_wins_on_red_loses_on_black():
    red = Bet(bet_type=BetType.RED, stake=10)
    assert settle_bets(_spin("18"), [red]).payouts == [10]
    assert settle_bets(_spin("17"), [red]).payouts == [-10]


def test_zero_loses_every_outside_bet():
    """0 and 00 are the house's edge — they kill all outside bets."""
    spin0 = _spin("0")
    spin00 = _spin("00")
    outside_bets = [
        Bet(BetType.RED, 10),
        Bet(BetType.BLACK, 10),
        Bet(BetType.EVEN, 10),
        Bet(BetType.ODD, 10),
        Bet(BetType.LOW, 10),
        Bet(BetType.HIGH, 10),
        Bet(BetType.DOZEN, 10, selection=1),
        Bet(BetType.COLUMN, 10, selection=1),
    ]
    for spin in (spin0, spin00):
        result = settle_bets(spin, outside_bets)
        assert all(p == -10 for p in result.payouts), (
            f"a bet didn't lose to {spin.pocket}: {result.payouts}"
        )


def test_dozens_split_pocket_range():
    d1 = Bet(BetType.DOZEN, 10, selection=1)
    d2 = Bet(BetType.DOZEN, 10, selection=2)
    d3 = Bet(BetType.DOZEN, 10, selection=3)
    # 7 is in dozen 1 (1-12)
    assert settle_bets(_spin("7"), [d1, d2, d3]).payouts == [20, -10, -10]
    # 13 is in dozen 2
    assert settle_bets(_spin("13"), [d1, d2, d3]).payouts == [-10, 20, -10]
    # 36 is in dozen 3
    assert settle_bets(_spin("36"), [d1, d2, d3]).payouts == [-10, -10, 20]


def test_columns_match_layout():
    c1 = Bet(BetType.COLUMN, 10, selection=1)
    c2 = Bet(BetType.COLUMN, 10, selection=2)
    c3 = Bet(BetType.COLUMN, 10, selection=3)
    # 1 is column 1 (n % 3 == 1).
    assert settle_bets(_spin("1"), [c1, c2, c3]).payouts == [20, -10, -10]
    # 2 is column 2.
    assert settle_bets(_spin("2"), [c1, c2, c3]).payouts == [-10, 20, -10]
    # 3 is column 3 (n % 3 == 0, matches sel == 3).
    assert settle_bets(_spin("3"), [c1, c2, c3]).payouts == [-10, -10, 20]


def test_low_high_split_pockets():
    low = Bet(BetType.LOW, 10)
    high = Bet(BetType.HIGH, 10)
    assert settle_bets(_spin("18"), [low, high]).payouts == [10, -10]
    assert settle_bets(_spin("19"), [low, high]).payouts == [-10, 10]


# ---- inside multi-pocket bets -----------------------------------------

def test_split_pays_17_to_1():
    bet = Bet(BetType.SPLIT, 10, selection=["1", "2"])
    assert settle_bets(_spin("1"), [bet]).payouts == [170]
    assert settle_bets(_spin("2"), [bet]).payouts == [170]
    assert settle_bets(_spin("3"), [bet]).payouts == [-10]


def test_corner_pays_8_to_1():
    bet = Bet(BetType.CORNER, 10, selection=["1", "2", "4", "5"])
    assert settle_bets(_spin("4"), [bet]).payouts == [80]
    assert settle_bets(_spin("3"), [bet]).payouts == [-10]


# ---- determinism + distribution --------------------------------------

def test_seeded_wheel_is_deterministic():
    a = Wheel(WheelKind.AMERICAN, seed=42)
    b = Wheel(WheelKind.AMERICAN, seed=42)
    seq_a = [a.spin().pocket for _ in range(50)]
    seq_b = [b.spin().pocket for _ in range(50)]
    assert seq_a == seq_b


def test_american_wheel_has_38_pockets_european_has_37():
    assert len(AMERICAN_POCKETS) == 38
    assert len(EUROPEAN_POCKETS) == 37
    assert "00" in AMERICAN_POCKETS
    assert "00" not in EUROPEAN_POCKETS


def test_red_hit_rate_close_to_theoretical():
    """Empirical check: 18/38 ≈ 47.4% on American, 18/37 ≈ 48.6% on European.
    Use 8000 spins; ~1.5% std → 5σ is ~7%, plenty of room."""
    n = 8000
    wheel = Wheel(WheelKind.AMERICAN, seed=0xDEAD)
    reds = sum(1 for _ in range(n) if wheel.spin().color == "red")
    assert abs(reds / n - 18 / 38) < 0.025

    wheel = Wheel(WheelKind.EUROPEAN, seed=0xBEEF)
    reds = sum(1 for _ in range(n) if wheel.spin().color == "red")
    assert abs(reds / n - 18 / 37) < 0.025


def test_house_edge_in_long_run():
    """Bet $1 on red repeatedly. American wheel's expected loss is
    $1 * (38 spins) - $36 expected wins = -2/38 per spin = -5.26%.
    Over 10k spins, 5.26% * 10k = -526; std ≈ $99 (≈ sqrt(10k * 1)).
    Use a wide tolerance (±$300) since variance dominates at this n."""
    n = 10_000
    wheel = Wheel(WheelKind.AMERICAN, seed=0xCAFE)
    pnl = 0
    for _ in range(n):
        spin = wheel.spin()
        bet = Bet(BetType.RED, 1)
        result = settle_bets(spin, [bet])
        pnl += result.total_profit
    # Expected ≈ -526. Allow ±400 (~4σ).
    assert -1000 < pnl < 200, f"red pnl {pnl} far from expected -526 over 10k spins"


# ---- error handling ----------------------------------------------------

def test_nonpositive_stake_pays_zero():
    bet = Bet(BetType.RED, 0)
    res = settle_bets(_spin("18"), [bet])
    assert res.payouts == [0]
    bet = Bet(BetType.RED, -5)
    assert settle_bets(_spin("18"), [bet]).payouts == [0]


def test_unknown_selection_loses_silently():
    """Garbage selection on a SPLIT can't crash the resolver — it just
    fails to match and loses."""
    bet = Bet(BetType.SPLIT, 10, selection="nonsense")
    assert settle_bets(_spin("17"), [bet]).payouts == [-10]
