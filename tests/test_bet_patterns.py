"""Bet pattern tests. Verify the recognizable money-management behaviors."""
import random

from app.ai.bet_patterns import (
    bet_anti_martingale,
    bet_count_spread,
    bet_flat,
    bet_martingale,
    bet_oscars_grind,
    bet_random,
    bet_streaky,
)
from app.engine.rules import Rules


def rng() -> random.Random:
    return random.Random(0)


def _rules(min_bet=5, max_bet=500, inc=5) -> Rules:
    return Rules(min_bet=min_bet, max_bet=max_bet, bet_increment=inc)


# ---- flat --------------------------------------------------------------

def test_flat_always_returns_base():
    r = _rules()
    assert bet_flat(1000, 25, [], r, None, rng()) == 25
    assert bet_flat(1000, 25, [-25, +25, -25], r, None, rng()) == 25


# ---- martingale --------------------------------------------------------

def test_martingale_doubles_after_loss():
    r = _rules()
    # Two losses in a row -> 4x base (doubled twice).
    assert bet_martingale(1000, 10, [-10, -10], r, None, rng()) == 40


def test_martingale_resets_after_win():
    r = _rules()
    # Win then loss -> just doubled once after the loss.
    assert bet_martingale(1000, 10, [-10, +10, -10], r, None, rng()) == 20


def test_martingale_caps_at_max_bet():
    r = _rules(max_bet=50)
    # Many losses would push above max_bet; clamps.
    bet = bet_martingale(1000, 10, [-10] * 10, r, None, rng())
    assert bet <= 50


# ---- anti-martingale ---------------------------------------------------

def test_anti_martingale_doubles_after_win():
    r = _rules()
    # Win streak of 2 -> base * 4.
    assert bet_anti_martingale(1000, 10, [+10, +10], r, None, rng()) == 40


def test_anti_martingale_resets_on_loss():
    r = _rules()
    assert bet_anti_martingale(1000, 10, [+10, -10], r, None, rng()) == 10


def test_anti_martingale_caps_at_three_streak():
    r = _rules(max_bet=10000)
    # 5 wins should cap at 3 doubles -> base * 8.
    assert bet_anti_martingale(10000, 10, [+10] * 5, r, None, rng()) == 80


# ---- count spread ------------------------------------------------------

def test_count_spread_at_negative_count_bets_base():
    r = _rules()
    assert bet_count_spread(1000, 10, [], r, -2.0, rng()) == 10


def test_count_spread_scales_with_count():
    r = _rules(max_bet=10000)
    # TC=4 -> units = 3 -> 30.
    assert bet_count_spread(10000, 10, [], r, 4.0, rng()) == 30
    # TC=10 -> units = 9 -> 90.
    assert bet_count_spread(10000, 10, [], r, 10.0, rng()) == 90


def test_count_spread_caps_at_12_units():
    r = _rules(max_bet=10000)
    # TC=20 should still cap at 12 * base = 120.
    assert bet_count_spread(10000, 10, [], r, 20.0, rng()) == 120


# ---- random ------------------------------------------------------------

def test_random_stays_within_min_max():
    r = _rules(min_bet=5, max_bet=200, inc=5)
    seen = set()
    rr = random.Random(1)
    for _ in range(100):
        bet = bet_random(1000, 20, [], r, None, rr)
        assert 5 <= bet <= 200
        assert bet % 5 == 0
        seen.add(bet)
    # Variability: at least 2 distinct values across 100 picks.
    assert len(seen) >= 2


# ---- oscar's grind -----------------------------------------------------

def test_oscars_grind_starts_at_base():
    r = _rules()
    assert bet_oscars_grind(1000, 10, [], r, None, rng()) == 10


def test_oscars_grind_increments_after_win_during_deficit():
    r = _rules()
    # Loss then win -> series profit = -10 + 10 = 0, still in deficit, ratchet up.
    assert bet_oscars_grind(1000, 10, [-10, +10], r, None, rng()) == 20


# ---- bankroll guards ---------------------------------------------------

def test_bet_clamps_to_bankroll():
    r = _rules()
    # Bankroll = 7, base = 50; bet should clamp to 7 rounded down to 5.
    bet = bet_flat(7, 50, [], r, None, rng())
    assert bet == 5
