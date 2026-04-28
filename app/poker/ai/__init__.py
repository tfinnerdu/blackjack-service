"""Poker AI: hand-strength estimation + personality bots.

  strength.py     pre-flop + post-flop hand-strength heuristics (no equity calc)
  personalities.py 9 personality functions returning a (BetAction, amount) decision
  bot.py          AISeat dataclass binding name + personality + state

The blackjack-style philosophy: bots aren't trying to be elite. They're
trying to feel recognizable — the calling station calls a lot, the
maniac raises a lot, the bluffer bluffs the river. The hand-strength
heuristic is intentionally simple so personality choices are the main
differentiator between bots.
"""
from .bot import AIBot
from .personalities import PERSONALITIES, all_personalities, get_personality
from .strength import HandStrength, post_flop_strength, pre_flop_strength

__all__ = [
    "AIBot",
    "HandStrength",
    "PERSONALITIES",
    "all_personalities",
    "get_personality",
    "post_flop_strength",
    "pre_flop_strength",
]
