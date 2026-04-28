"""Roulette engine.

Pure-function spin + bet resolution. The wheel is selected at session
creation: American (38 pockets, 0 + 00 + 1..36) or European (37 pockets,
single 0 + 1..36). Payouts use the standard table — straight 35:1, split
17:1, etc. — and are configurable per session if a future variant wants
to tweak them.

State + persistence live in `app.casino.session`; this module is just
math + types so it stays unit-test friendly.
"""
from .wheel import (
    AMERICAN_PAYOUTS,
    AMERICAN_POCKETS,
    Bet,
    BetType,
    EUROPEAN_PAYOUTS,
    EUROPEAN_POCKETS,
    Pocket,
    Spin,
    SpinResult,
    Wheel,
    WheelKind,
    is_red,
    pocket_color,
    settle_bets,
    spin_wheel,
)

__all__ = [
    "AMERICAN_PAYOUTS",
    "AMERICAN_POCKETS",
    "Bet",
    "BetType",
    "EUROPEAN_PAYOUTS",
    "EUROPEAN_POCKETS",
    "Pocket",
    "Spin",
    "SpinResult",
    "Wheel",
    "WheelKind",
    "is_red",
    "pocket_color",
    "settle_bets",
    "spin_wheel",
]
