"""Bet sizing patterns. Each function decides how much an AI seat bets on
the next round given its bankroll, recent history, and (for counters) the
true count.

Inputs:
- bankroll: current bankroll
- base_bet: the seat's base wager unit
- last_results: list of recent profits in chronological order (most recent last);
  empty for the first hand of a session
- rules: table rules (for min_bet/max_bet/bet_increment)
- true_count: optional, only used by spread pattern
- rng: deterministic randomness for 'random' pattern

All functions clamp to [rules.min_bet, rules.max_bet] and round to bet_increment.
"""
from __future__ import annotations

import random
from typing import Callable, Optional

from ..engine.rules import Rules


BetFn = Callable[
    [int, int, list[int], Rules, Optional[float], random.Random],
    int,
]


def _clamp(amount: int, rules: Rules, bankroll: int) -> int:
    """Clamp to [min_bet, min(max_bet, bankroll)] rounded to bet_increment."""
    cap = min(rules.max_bet, bankroll)
    if cap < rules.min_bet:
        return rules.min_bet  # caller decides whether the seat sits out
    amount = max(rules.min_bet, min(amount, cap))
    inc = rules.bet_increment
    if inc > 1:
        amount = (amount // inc) * inc
        if amount < rules.min_bet:
            amount = rules.min_bet
    return amount


# ---- flat --------------------------------------------------------------

def bet_flat(bankroll, base, last_results, rules, true_count, rng) -> int:
    return _clamp(base, rules, bankroll)


# ---- martingale (double after loss) ------------------------------------

def bet_martingale(bankroll, base, last_results, rules, true_count, rng) -> int:
    """Classic loss-chaser. Double until you win, reset to base after a win."""
    bet = base
    for profit in reversed(last_results):
        if profit < 0:
            bet *= 2
        else:
            break
    return _clamp(bet, rules, bankroll)


# ---- anti-martingale / paroli (double after win) -----------------------

def bet_anti_martingale(bankroll, base, last_results, rules, true_count, rng) -> int:
    """Press wins; reset on a loss or push. Caps streak at 3 wins."""
    streak = 0
    for profit in reversed(last_results):
        if profit > 0:
            streak += 1
            if streak >= 3:
                break
        else:
            break
    bet = base * (2 ** streak)
    return _clamp(bet, rules, bankroll)


# ---- Oscar's Grind -----------------------------------------------------

def bet_oscars_grind(bankroll, base, last_results, rules, true_count, rng) -> int:
    """Goal: net +1 base unit per series. Increase bet by 1 unit after a win
    (unless that would over-shoot the +1 goal); reset to base after a series.

    Simplified implementation: tracks profit-since-last-base-bet. While the
    series is still in deficit, win streaks ratchet the bet up by 1 unit.
    """
    if not last_results:
        return _clamp(base, rules, bankroll)

    # Sum until the most recent series boundary (bet returns to base after
    # a winning series). For simplicity, treat the last 0 or first net-positive
    # streak end as the boundary.
    series_profit = 0
    series_bet = base
    for profit in last_results:
        series_profit += profit
        if profit > 0 and series_profit >= base:
            # Series ended at +1 unit goal; reset.
            series_profit = 0
            series_bet = base
        elif profit > 0:
            series_bet += base

    return _clamp(series_bet, rules, bankroll)


# ---- count-based spread -----------------------------------------------

def bet_count_spread(bankroll, base, last_results, rules, true_count, rng) -> int:
    """Counter's bet ramp. Spread = (TC - 1) * base, floored at base.

    A 1-12 spread on a 6-deck game is conventional; we cap at 12*base so a
    huge count doesn't put the whole bankroll on one hand.
    """
    if true_count is None or true_count < 1:
        return _clamp(base, rules, bankroll)
    units = max(1, int(true_count - 1))
    units = min(units, 12)
    return _clamp(base * units, rules, bankroll)


# ---- random within range ----------------------------------------------

def bet_random(bankroll, base, last_results, rules, true_count, rng) -> int:
    """Pick a random multiple of bet_increment between min_bet and 4*base.
    Capped by bankroll and max_bet."""
    high = min(rules.max_bet, base * 4, bankroll)
    if high < rules.min_bet:
        return rules.min_bet
    inc = max(1, rules.bet_increment)
    steps = (high - rules.min_bet) // inc
    pick = rules.min_bet + rng.randint(0, steps) * inc
    return _clamp(pick, rules, bankroll)


# ---- streaky (presses up on wins, pulls back on losses) ----------------

def bet_streaky(bankroll, base, last_results, rules, true_count, rng) -> int:
    """Bet rises with a recent win streak, falls with a losing streak.
    Less aggressive than anti-martingale: +50% per win, -25% per loss.
    """
    multiplier = 1.0
    for profit in reversed(last_results[-5:]):
        if profit > 0:
            multiplier *= 1.5
        elif profit < 0:
            multiplier *= 0.75
    bet = max(int(base * multiplier), rules.min_bet)
    return _clamp(bet, rules, bankroll)


# ---- registry ----------------------------------------------------------

BET_PATTERNS: dict[str, BetFn] = {
    "flat": bet_flat,
    "martingale": bet_martingale,
    "anti_martingale": bet_anti_martingale,
    "oscars_grind": bet_oscars_grind,
    "count_spread": bet_count_spread,
    "random": bet_random,
    "streaky": bet_streaky,
}


def get_bet_pattern(name: str) -> BetFn:
    if name not in BET_PATTERNS:
        raise KeyError(f"unknown bet pattern: {name!r}; choose from {sorted(BET_PATTERNS)}")
    return BET_PATTERNS[name]


def all_bet_patterns() -> list[str]:
    return list(BET_PATTERNS.keys())
