"""Baccarat engine. Punto Banco rules — the player has no decisions;
each round, two cards go to Player and Banker, then a third may be
drawn to either side per a fixed table. Bets settle on which side
wins (or a tie).

Standard payouts:
  Player win: 1:1
  Banker win: 1:1 minus 5% commission (so 0.95:1, common variant)
  Tie:        8:1 (sometimes 9:1)
  Pair side bets: 11:1 (player pair, banker pair)

We expose:
  - deal_round(shoe) → BaccaratRound
  - settle_bets(round, bets) → list of profits
"""
from .game import (
    Bet,
    BetType,
    BaccaratRound,
    BaccaratRules,
    BaccaratShoe,
    deal_round,
    hand_total,
    rank_value,
    settle_bets,
)

__all__ = [
    "Bet",
    "BetType",
    "BaccaratRound",
    "BaccaratRules",
    "BaccaratShoe",
    "deal_round",
    "hand_total",
    "rank_value",
    "settle_bets",
]
