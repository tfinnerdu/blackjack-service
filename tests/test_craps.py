"""Craps engine tests. Covers:

  - Phase machine: come-out → point → seven-out → come-out
  - Pass / Don't Pass bets on natural / craps / point rolls
  - Pass odds + Don't Pass odds at the published true-odds rate
  - Come / Don't Come behave like a per-bet pass-line cycle
  - Place bets resolve at correct payouts
  - Field, any-seven, any-craps one-roll bets
  - Hardway bets distinguish hard from easy
  - Empirical seven-out rate matches dice probabilities
"""
from __future__ import annotations

import random

from app.craps import (
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


def _bet(bet_id: str, btype: BetType, stake: int = 10, selection=None) -> Bet:
    return Bet(bet_id=bet_id, bet_type=btype, stake=stake, selection=selection)


def _resolve_one(table: CrapsTable, total: int, bets: list[Bet],
                 d1: int = None, d2: int = None,
                 rules=None) -> RollResult:
    """Helper: pick a (d1, d2) that sums to `total` if not specified."""
    if d1 is None:
        d1 = max(1, total - 6)
        d2 = total - d1
    return resolve_roll(table, Roll(d1, d2), bets, rules)


# ---- pass / dont pass --------------------------------------------------

def test_pass_line_wins_on_come_out_seven():
    table = create_table()
    bet = _bet("p1", BetType.PASS_LINE, 10)
    result = _resolve_one(table, 7, [bet])
    assert result.outcomes[0].profit == 10
    assert result.outcomes[0].resolved is True
    assert table.phase == Phase.COME_OUT


def test_pass_line_loses_on_come_out_craps():
    for craps in (2, 3, 12):
        table = create_table()
        bet = _bet("p1", BetType.PASS_LINE, 10)
        result = _resolve_one(table, craps, [bet])
        assert result.outcomes[0].profit == -10, f"craps {craps}"


def test_pass_line_establishes_point_then_makes_it():
    table = create_table()
    bet = _bet("p1", BetType.PASS_LINE, 10)
    # First roll: 6 → point established.
    r = _resolve_one(table, 6, [bet])
    assert r.outcomes[0].profit == 0
    assert r.outcomes[0].resolved is False
    assert table.phase == Phase.POINT_ON
    assert table.point == 6

    # Roll a 5 → no resolution (roll-by).
    r = _resolve_one(table, 5, [bet])
    assert r.outcomes[0].profit == 0
    assert r.outcomes[0].resolved is False
    assert table.point == 6

    # Hit the point.
    r = _resolve_one(table, 6, [bet])
    assert r.outcomes[0].profit == 10
    assert r.outcomes[0].resolved is True
    assert table.phase == Phase.COME_OUT
    assert table.point is None


def test_pass_line_seven_out_after_point():
    table = create_table()
    bet = _bet("p1", BetType.PASS_LINE, 10)
    _resolve_one(table, 8, [bet])  # establish 8
    r = _resolve_one(table, 7, [bet])
    assert r.outcomes[0].profit == -10
    assert table.phase == Phase.COME_OUT


def test_dont_pass_pushes_on_12():
    table = create_table()
    bet = _bet("d1", BetType.DONT_PASS, 10)
    r = _resolve_one(table, 12, [bet])
    assert r.outcomes[0].profit == 0  # push, not loss
    assert r.outcomes[0].resolved is True


def test_dont_pass_wins_on_seven_out():
    table = create_table()
    bet = _bet("d1", BetType.DONT_PASS, 10)
    _resolve_one(table, 9, [bet])  # point on
    r = _resolve_one(table, 7, [bet])
    assert r.outcomes[0].profit == 10


def test_pass_odds_pays_true_odds():
    table = create_table()
    line = _bet("p1", BetType.PASS_LINE, 10)
    _resolve_one(table, 4, [line])  # establish 4
    odds = _bet("o1", BetType.PASS_ODDS, 10)
    r = _resolve_one(table, 4, [line, odds])
    # Line pays 10 (1:1); odds on 4 pay 2:1 = 20.
    assert r.outcomes[0].profit == 10  # line
    assert r.outcomes[1].profit == 20  # odds


def test_dont_pass_odds_pays_lay_odds():
    table = create_table()
    line = _bet("d1", BetType.DONT_PASS, 30)
    _resolve_one(table, 4, [line])  # establish 4
    odds = _bet("o1", BetType.DONT_PASS_ODDS, 20)  # lay 20 to win 10
    r = _resolve_one(table, 7, [line, odds])
    assert r.outcomes[0].profit == 30
    # Lay odds on 4: 1:2 → 20 * 1 / 2 = 10
    assert r.outcomes[1].profit == 10


# ---- come bets --------------------------------------------------------

def test_come_bet_establishes_then_wins_on_its_number():
    table = create_table()
    _resolve_one(table, 6, [_bet("p1", BetType.PASS_LINE, 10)])  # set point 6
    come = _bet("c1", BetType.COME, 10)
    # Establish come-point at 8.
    r = _resolve_one(table, 8, [come])
    assert r.outcomes[0].resolved is False
    assert come.established_point == 8

    # 8 again → come-bet wins. (Pass-line pre-bet doesn't apply here.)
    r = _resolve_one(table, 8, [come])
    assert r.outcomes[0].profit == 10
    assert r.outcomes[0].resolved is True


def test_come_bet_loses_on_seven():
    table = create_table()
    _resolve_one(table, 5, [_bet("p1", BetType.PASS_LINE, 10)])  # set point 5
    come = _bet("c1", BetType.COME, 10)
    _resolve_one(table, 9, [come])  # come-point 9
    r = _resolve_one(table, 7, [come])
    assert r.outcomes[0].profit == -10


# ---- place bets -------------------------------------------------------

def test_place_6_pays_7_to_6():
    table = create_table()
    _resolve_one(table, 8, [_bet("p1", BetType.PASS_LINE, 10)])  # point on
    place = _bet("pl1", BetType.PLACE, 12, selection=6)
    r = _resolve_one(table, 6, [place])
    assert r.outcomes[0].profit == 14  # 12 * 7/6 = 14


def test_place_loses_on_seven():
    table = create_table()
    _resolve_one(table, 8, [_bet("p1", BetType.PASS_LINE, 10)])
    place = _bet("pl1", BetType.PLACE, 10, selection=6)
    r = _resolve_one(table, 7, [place])
    assert r.outcomes[0].profit == -10


# ---- field -----------------------------------------------------------

def test_field_pays_double_on_2():
    table = create_table()
    bet = _bet("f1", BetType.FIELD, 10)
    r = _resolve_one(table, 2, [bet])
    assert r.outcomes[0].profit == 20


def test_field_pays_triple_on_12():
    table = create_table()
    bet = _bet("f1", BetType.FIELD, 10)
    r = _resolve_one(table, 12, [bet])
    assert r.outcomes[0].profit == 30


def test_field_loses_on_5_6_7_8():
    table = create_table()
    for total in (5, 6, 7, 8):
        bet = _bet("f1", BetType.FIELD, 10)
        # Using a fresh table since field is one-roll anyway.
        r = _resolve_one(create_table(), total, [bet])
        assert r.outcomes[0].profit == -10, f"field on {total} should lose"


# ---- one-roll prop bets -----------------------------------------------

def test_any_seven_pays_4_to_1():
    table = create_table()
    bet = _bet("a7", BetType.ANY_SEVEN, 5)
    r = _resolve_one(table, 7, [bet])
    assert r.outcomes[0].profit == 20


def test_any_craps_pays_7_to_1():
    table = create_table()
    bet = _bet("ac", BetType.ANY_CRAPS, 5)
    r = _resolve_one(table, 3, [bet])
    assert r.outcomes[0].profit == 35


# ---- hardways --------------------------------------------------------

def test_hard_8_pays_9_to_1():
    table = create_table()
    bet = _bet("h8", BetType.HARD, 5, selection=8)
    # Hard 8 = 4-4.
    r = resolve_roll(table, Roll(4, 4), [bet])
    assert r.outcomes[0].profit == 45


def test_hard_loses_on_easy_match():
    table = create_table()
    bet = _bet("h8", BetType.HARD, 5, selection=8)
    r = resolve_roll(table, Roll(5, 3), [bet])  # easy 8
    assert r.outcomes[0].profit == -5
    assert r.outcomes[0].resolved is True


def test_hard_loses_on_seven():
    table = create_table()
    bet = _bet("h8", BetType.HARD, 5, selection=8)
    r = resolve_roll(table, Roll(3, 4), [bet])
    assert r.outcomes[0].profit == -5


def test_hard_stays_on_unrelated_roll():
    table = create_table()
    bet = _bet("h8", BetType.HARD, 5, selection=8)
    r = resolve_roll(table, Roll(2, 3), [bet])  # 5
    assert r.outcomes[0].profit == 0
    assert r.outcomes[0].resolved is False


# ---- distribution ----------------------------------------------------

def test_seven_out_rate_matches_dice():
    """Pass Line house edge is famously 1.41%. Over 5000 come-out
    sequences (each is a complete pass-line resolution), we expect
    Pass to win ~49.3% of the time. We don't pin a tight rate — just
    a sanity check that wins are within 5% of expected."""
    rng = random.Random(0xCAFE)
    n = 5000
    pass_wins = 0
    for _ in range(n):
        table = create_table()
        bet = _bet("p", BetType.PASS_LINE, 1)
        # Roll until pass-line resolves.
        for _ in range(50):  # safety bound; nearly always resolves in <10
            r = resolve_roll(table, roll_dice(rng), [bet])
            if r.outcomes[0].resolved:
                if r.outcomes[0].profit > 0:
                    pass_wins += 1
                break
    rate = pass_wins / n
    # Expected pass-line win rate ≈ 0.4929.
    assert abs(rate - 0.4929) < 0.025, (
        f"pass-line win rate {rate:.4f} drifted from 0.4929"
    )
