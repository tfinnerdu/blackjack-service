"""Odds + payout primitives.

American odds convention:
  - Negative odds (e.g. -150) = "lay $150 to win $100". Decimal = 1 + 100/150.
  - Positive odds (e.g. +130) = "lay $100 to win $130".  Decimal = 1 + 130/100.
  - Even money is +100 (or -100), decimal 2.0.

Parlay payout = stake * product(decimal_odds_per_leg). Pushed legs
drop out of the product (they're treated as if they didn't exist —
the parlay shrinks). Lost legs sink the whole slip.
"""
from __future__ import annotations

from typing import Iterable


SLIP_SINGLE = "single"
SLIP_PARLAY = "parlay"

LEG_WON = "won"
LEG_LOST = "lost"
LEG_PUSH = "push"
LEG_VOID = "void"   # event was canceled; treat like push for settlement


def american_to_decimal(american: int) -> float:
    """Convert American odds (e.g. -150, +130) to decimal (e.g. 1.667, 2.30).
    Returns the *full* decimal — multiply stake by this to get the
    return on a winning bet (stake included)."""
    if american == 0:
        raise ValueError("american odds cannot be 0")
    if american > 0:
        return 1.0 + american / 100.0
    return 1.0 + 100.0 / abs(american)


def decimal_to_american(decimal: float) -> int:
    """Inverse of american_to_decimal. Used by the UI / tests."""
    if decimal <= 1.0:
        raise ValueError("decimal odds must be > 1.0")
    if decimal >= 2.0:
        return int(round((decimal - 1.0) * 100))
    return int(round(-100.0 / (decimal - 1.0)))


def parlay_decimal_odds(legs_decimal: Iterable[float]) -> float:
    """Combined decimal odds for a parlay = product of every leg's
    decimal odds. An empty iterable returns 1.0 (no return)."""
    product = 1.0
    for d in legs_decimal:
        product *= d
    return product


def potential_payout(stake: int, american_odds_per_leg: list[int]) -> int:
    """Total return on a winning slip with these legs (single = 1 leg,
    parlay = many). Includes the stake. Rounded to nearest dollar
    so e.g. -150 on $150 pays $250 and not $249 (1.6666… truncation)."""
    if stake <= 0:
        return 0
    decimals = [american_to_decimal(o) for o in american_odds_per_leg]
    combined = parlay_decimal_odds(decimals)
    return int(round(stake * combined))


def settle_legs(
    legs: list[dict],
    market_results: dict[int, str | None],
) -> list[dict]:
    """Look up each leg's outcome from the per-market winner_key map.

    `legs` is a list of {"market_id", "selection_key", "odds"}.
    `market_results` maps market_id -> winner_key ("home"/"away"/"over"/
    "under"/"PUSH"/"VOID" or None for "still pending").

    Returns a parallel list of {"market_id", "selection_key", "odds",
    "outcome": LEG_WON|LEG_LOST|LEG_PUSH|LEG_VOID|None} entries.
    """
    out: list[dict] = []
    for leg in legs:
        winner = market_results.get(int(leg["market_id"]))
        leg_out = dict(leg)
        if winner is None:
            leg_out["outcome"] = None  # still pending
        elif winner == "PUSH":
            leg_out["outcome"] = LEG_PUSH
        elif winner == "VOID":
            leg_out["outcome"] = LEG_VOID
        elif winner == leg["selection_key"]:
            leg_out["outcome"] = LEG_WON
        else:
            leg_out["outcome"] = LEG_LOST
        out.append(leg_out)
    return out


def settle_slip(
    *,
    slip_type: str,
    legs: list[dict],
    stake: int,
    market_results: dict[int, str | None],
) -> dict:
    """Apply settlement to a slip. Returns a dict:
        {
          "status": "pending" | "won" | "lost" | "push" | "void",
          "payout_actual": int,
          "leg_results": [...]
        }

    Rules:
      - Any leg LOST -> slip LOST, payout 0.
      - All legs PUSH/VOID -> slip PUSH, payout = stake (stake returned).
      - Pending leg present and no losses -> slip stays PENDING.
      - Otherwise: surviving legs determine the parlay payout. PUSH
        legs drop from the parlay product (the parlay shrinks).
    """
    leg_results = settle_legs(legs, market_results)
    statuses = {l["outcome"] for l in leg_results}

    if LEG_LOST in statuses:
        return {"status": "lost", "payout_actual": 0, "leg_results": leg_results}

    pending = any(l["outcome"] is None for l in leg_results)
    won_legs = [l for l in leg_results if l["outcome"] == LEG_WON]
    push_legs = [l for l in leg_results if l["outcome"] in (LEG_PUSH, LEG_VOID)]

    if pending:
        return {"status": "pending", "payout_actual": 0, "leg_results": leg_results}

    if not won_legs:
        # All push/void — full stake refund.
        return {"status": "push", "payout_actual": int(stake), "leg_results": leg_results}

    # Pure win path: stake * product(decimal_odds_for_won_legs).
    decimals = [american_to_decimal(int(l["odds"])) for l in won_legs]
    combined = parlay_decimal_odds(decimals)
    payout = int(round(stake * combined))
    return {"status": "won", "payout_actual": payout, "leg_results": leg_results}
