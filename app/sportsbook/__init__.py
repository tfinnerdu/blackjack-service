"""Sportsbook engine: odds math, parlay payouts, settlement.

A `Slip` is one wager — either a SINGLE leg or a PARLAY of multiple
legs. American odds in (-110, +130, etc.) round-trip via decimal odds
internally; we settle on decimal odds because parlay math is just a
product across legs.

The engine is pure functions on dicts; the DB layer in
`app.services.sportsbook` calls into here.
"""
from .odds import (
    SLIP_PARLAY,
    SLIP_SINGLE,
    LEG_LOST,
    LEG_PUSH,
    LEG_VOID,
    LEG_WON,
    american_to_decimal,
    decimal_to_american,
    parlay_decimal_odds,
    potential_payout,
    settle_legs,
    settle_slip,
)

__all__ = [
    "SLIP_PARLAY",
    "SLIP_SINGLE",
    "LEG_LOST",
    "LEG_PUSH",
    "LEG_VOID",
    "LEG_WON",
    "american_to_decimal",
    "decimal_to_american",
    "parlay_decimal_odds",
    "potential_payout",
    "settle_legs",
    "settle_slip",
]
