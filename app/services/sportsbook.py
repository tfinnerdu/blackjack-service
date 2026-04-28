"""Sportsbook session orchestration.

Each session is a paper-trading bankroll the user wagers against the
slate of `SportsEvent` rows for the current day. Slips are placed at
the odds visible at placement time; settlement happens when the host
hits "advance day", which:
  1. Rolls the day cursor forward
  2. For each event whose `day <= new cursor`, sets final scores +
     market winners
  3. Settles every pending slip whose legs all reference now-resolved
     markets
"""
from __future__ import annotations

import json
import random
from typing import Optional

from ..db import db
from ..models import (
    BettingMarket,
    BettingSlip,
    SportsEvent,
    SportsbookSession,
)
from ..sportsbook import (
    SLIP_PARLAY,
    SLIP_SINGLE,
    american_to_decimal,
    parlay_decimal_odds,
    potential_payout,
    settle_slip,
)
from ..sportsbook.fixtures import (
    FixtureEvent,
    generate_day_slate,
    winner_keys_for_event,
)


class SportsbookError(Exception):
    """Caller-visible problem (insufficient bankroll, missing market, etc.)."""


# How many days of fixtures to seed at session creation. Each
# advance-day refills the future window.
DEFAULT_SLATE_LOOKAHEAD = 3


# ---- session lifecycle -----------------------------------------------

def create_sportsbook_session(
    *,
    starting_bankroll: int = 1000,
    seed: Optional[int] = None,
) -> SportsbookSession:
    if starting_bankroll <= 0:
        raise SportsbookError("starting_bankroll must be > 0")
    sess = SportsbookSession(
        starting_bankroll=starting_bankroll,
        bankroll=starting_bankroll,
    )
    db.session.add(sess)
    db.session.commit()

    seed = seed if seed is not None else random.randint(0, 2**31 - 1)
    # Pre-seed the next few days so the user has a full slate today
    # PLUS some scheduled-for-tomorrow events to think about.
    _ensure_slate_through(seed, sess.current_day + DEFAULT_SLATE_LOOKAHEAD)
    return sess


def _ensure_slate_through(seed: int, target_day: int) -> None:
    """Generate fixtures for any day that doesn't yet have rows. Idempotent.
    Multiple sessions share the same slate — events are global by `day`."""
    existing_days = {
        row[0] for row in db.session.query(SportsEvent.day).distinct().all()
    }
    for day in range(target_day + 1):
        if day in existing_days:
            continue
        slate = generate_day_slate(day=day, seed=seed)
        for fix in slate:
            ev = SportsEvent(
                sport=fix.sport,
                league=fix.league,
                home_team=fix.home_team,
                away_team=fix.away_team,
                day=day,
                status="scheduled",
                home_score=fix.home_score,
                away_score=fix.away_score,
            )
            db.session.add(ev)
            db.session.flush()  # need ev.id for markets
            for market in fix.markets:
                m = BettingMarket(
                    event_id=ev.id,
                    market_type=market.market_type,
                    selections_json=json.dumps(market.selections),
                    status="open",
                )
                db.session.add(m)
    db.session.commit()


# ---- listing ---------------------------------------------------------

def list_open_events(sess: SportsbookSession) -> list[dict]:
    """Events the user can still bet on — those at day >= current_day
    AND status='scheduled'. Returns a JSON-serializable list."""
    rows = (
        SportsEvent.query
        .filter(SportsEvent.day >= sess.current_day)
        .filter(SportsEvent.status == "scheduled")
        .order_by(SportsEvent.day.asc(), SportsEvent.id.asc())
        .all()
    )
    return [r.to_dict() for r in rows]


def list_user_slips(sess: SportsbookSession) -> list[dict]:
    rows = (
        BettingSlip.query
        .filter_by(session_id=sess.id)
        .order_by(BettingSlip.placed_at.desc())
        .all()
    )
    return [r.to_dict() for r in rows]


# ---- placing slips ---------------------------------------------------

def place_slip(
    sess: SportsbookSession,
    *,
    legs_input: list[dict],
    stake: int,
    slip_type: Optional[str] = None,
) -> BettingSlip:
    """Validate + persist a new slip.

    `legs_input`: list of `{"market_id": int, "selection_key": str}`.
    Stake is in dollars. Slip type defaults to "single" when one leg,
    "parlay" otherwise.
    """
    if not legs_input:
        raise SportsbookError("at least one leg required")
    if stake <= 0:
        raise SportsbookError("stake must be > 0")
    if stake > sess.bankroll:
        raise SportsbookError(
            f"insufficient bankroll: stake {stake} > bankroll {sess.bankroll}"
        )
    if len(legs_input) > 10:
        raise SportsbookError("max 10 legs per parlay")

    inferred_type = slip_type or (
        SLIP_SINGLE if len(legs_input) == 1 else SLIP_PARLAY
    )
    if inferred_type not in (SLIP_SINGLE, SLIP_PARLAY):
        raise SportsbookError(
            f"slip_type must be 'single' or 'parlay'; got {inferred_type!r}"
        )
    if inferred_type == SLIP_SINGLE and len(legs_input) != 1:
        raise SportsbookError("single slips must have exactly one leg")

    # Resolve each leg against the live market record. Pin the odds
    # at placement so a future odds shift can't change the payout.
    resolved_legs: list[dict] = []
    seen_market_ids: set[int] = set()
    for leg in legs_input:
        try:
            market_id = int(leg["market_id"])
            selection_key = str(leg["selection_key"])
        except (KeyError, TypeError, ValueError):
            raise SportsbookError(f"malformed leg: {leg!r}")

        if market_id in seen_market_ids:
            raise SportsbookError("a parlay can't include the same market twice")
        seen_market_ids.add(market_id)

        market = db.session.get(BettingMarket, market_id)
        if market is None:
            raise SportsbookError(f"market {market_id} not found")
        if market.status != "open":
            raise SportsbookError(f"market {market_id} is closed")

        # Confirm the selection key exists in this market.
        selections = json.loads(market.selections_json)
        match = next(
            (s for s in selections if s["key"] == selection_key), None,
        )
        if match is None:
            raise SportsbookError(
                f"market {market_id} has no selection {selection_key!r}"
            )

        # Confirm the parent event is still scheduled — can't bet on
        # an event that's already final.
        event = db.session.get(SportsEvent, market.event_id)
        if event is None or event.status != "scheduled":
            raise SportsbookError(
                f"event for market {market_id} is no longer scheduled"
            )

        resolved_legs.append({
            "market_id": market_id,
            "selection_key": selection_key,
            "odds": int(match["odds"]),
            "label": match.get("label"),
            "line": match.get("line"),
            "market_type": market.market_type,
            "event_id": event.id,
            "event_label": f"{event.away_team} @ {event.home_team}",
            "event_day": event.day,
        })

    payout_total = potential_payout(stake, [int(l["odds"]) for l in resolved_legs])

    slip = BettingSlip(
        session_id=sess.id,
        slip_type=inferred_type,
        legs_json=json.dumps(resolved_legs),
        stake=int(stake),
        potential_payout=int(payout_total),
        status="pending",
        placed_on_day=sess.current_day,
    )
    db.session.add(slip)
    sess.bankroll -= int(stake)
    sess.slips_placed += 1
    sess.total_staked += int(stake)
    db.session.commit()
    return slip


# ---- advance day + settlement ----------------------------------------

def advance_day(sess: SportsbookSession, *, seed: Optional[int] = None) -> dict:
    """Move the session's day cursor forward by 1. Resolves every
    event with day == new_current_day. Settles every pending slip
    whose legs are now fully resolved.

    Returns a summary dict with the events resolved + slips settled.
    """
    new_day = sess.current_day + 1

    # "Advance day" means everything scheduled for the day we're
    # *leaving* (sess.current_day) plus any earlier still-scheduled
    # events become final. We pull every scheduled event at day <
    # new_day so a session that's been idle for a while catches up
    # all at once instead of having to advance one day at a time.
    events_to_resolve = (
        SportsEvent.query
        .filter(SportsEvent.day < new_day)
        .filter(SportsEvent.status == "scheduled")
        .order_by(SportsEvent.day.asc())
        .all()
    )
    settled_events = []
    for event in events_to_resolve:
        # Build a FixtureEvent stand-in to reuse the winner_keys helper.
        # The DB already has final scores from generate_day_slate; we
        # just use them.
        from ..sportsbook.fixtures import FixtureMarket as _FM
        markets_for_helper = []
        for m in event.markets:
            markets_for_helper.append(_FM(
                market_type=m.market_type,
                selections=json.loads(m.selections_json),
            ))
        event_helper = FixtureEvent(
            sport=event.sport, league=event.league,
            home_team=event.home_team, away_team=event.away_team,
            home_score=event.home_score or 0,
            away_score=event.away_score or 0,
            markets=markets_for_helper,
        )
        winners = winner_keys_for_event(event_helper)
        for m in event.markets:
            m.winner_key = winners.get(m.market_type)
            m.status = "settled"
        event.status = "final"
        settled_events.append(event.to_dict())

    # Settle pending slips for THIS session that reference now-
    # resolved markets. Other sessions get settled when their own
    # advance_day call comes through (so each user can pace
    # independently).
    slips_settled: list[dict] = []
    pending_slips = (
        BettingSlip.query
        .filter_by(session_id=sess.id, status="pending")
        .all()
    )
    for slip in pending_slips:
        legs = json.loads(slip.legs_json)
        market_ids = [int(l["market_id"]) for l in legs]
        markets = (
            BettingMarket.query
            .filter(BettingMarket.id.in_(market_ids))
            .all()
        )
        market_results = {m.id: m.winner_key for m in markets}
        outcome = settle_slip(
            slip_type=slip.slip_type,
            legs=legs,
            stake=slip.stake,
            market_results=market_results,
        )
        if outcome["status"] == "pending":
            continue  # at least one leg still in the future
        slip.status = outcome["status"]
        slip.payout_actual = int(outcome["payout_actual"])
        slip.leg_results_json = json.dumps(outcome["leg_results"])
        from datetime import datetime, timezone
        slip.settled_at = datetime.now(timezone.utc)

        sess.bankroll += int(outcome["payout_actual"])
        sess.total_returned += int(outcome["payout_actual"])
        if outcome["status"] == "won":
            sess.slips_won += 1
        elif outcome["status"] == "lost":
            sess.slips_lost += 1
        elif outcome["status"] in ("push", "void"):
            sess.slips_pushed += 1
        slips_settled.append(slip.to_dict())

    sess.current_day = new_day

    # Top up the future slate so the user always has lookahead games.
    target = sess.current_day + DEFAULT_SLATE_LOOKAHEAD
    seed_for_topup = seed if seed is not None else random.randint(0, 2**31 - 1)
    _ensure_slate_through(seed_for_topup, target)

    db.session.commit()
    return {
        "current_day": sess.current_day,
        "events_resolved": settled_events,
        "slips_settled": slips_settled,
    }


# ---- analytics --------------------------------------------------------

def session_analytics(sess: SportsbookSession) -> dict:
    """Compute summary stats + interesting cuts for the analytics page.

    Returns:
      summary: bankroll / ROI / hit rate
      by_market_type: hit rate per moneyline/spread/total
      by_slip_type: hit rate single vs parlay
      streak: current win/loss streak
      worst_legs: lowest-EV losing slips (high odds, surprising losses)
    """
    slips = list_user_slips(sess)
    settled = [s for s in slips if s["status"] in ("won", "lost", "push", "void")]
    total_settled = len(settled)
    wins = sum(1 for s in settled if s["status"] == "won")
    losses = sum(1 for s in settled if s["status"] == "lost")
    pushes = sum(1 for s in settled if s["status"] in ("push", "void"))

    win_rate = (wins / max(1, wins + losses)) if (wins + losses) else 0.0
    roi = (
        (sess.total_returned - sess.total_staked) / sess.total_staked
        if sess.total_staked else 0.0
    )

    # Per-market-type hit rate (for SINGLE bets only — parlays muddy
    # the attribution).
    by_market: dict[str, dict] = {}
    for s in settled:
        if s["slip_type"] != "single" or not s["legs"]:
            continue
        leg = s["legs"][0]
        mtype = leg.get("market_type", "unknown")
        bucket = by_market.setdefault(mtype, {"won": 0, "lost": 0, "push": 0})
        if s["status"] == "won":
            bucket["won"] += 1
        elif s["status"] == "lost":
            bucket["lost"] += 1
        elif s["status"] in ("push", "void"):
            bucket["push"] += 1

    # Single vs parlay split.
    by_slip_type: dict[str, dict] = {}
    for s in settled:
        bucket = by_slip_type.setdefault(s["slip_type"], {
            "won": 0, "lost": 0, "push": 0, "staked": 0, "returned": 0,
        })
        bucket["staked"] += s["stake"]
        bucket["returned"] += s["payout_actual"]
        if s["status"] == "won":
            bucket["won"] += 1
        elif s["status"] == "lost":
            bucket["lost"] += 1
        elif s["status"] in ("push", "void"):
            bucket["push"] += 1

    # Recent streak (wins/losses, ignoring pushes).
    streak_count = 0
    streak_sign = 0  # +1 win streak, -1 loss streak
    for s in settled:
        if s["status"] == "push":
            continue
        sign = 1 if s["status"] == "won" else -1
        if streak_sign == 0:
            streak_sign = sign
            streak_count = 1
        elif sign == streak_sign:
            streak_count += 1
        else:
            break  # streak broke at this earlier slip

    # Surprising losses: legs at +200 or longer that lost. Catches
    # "underdog stories you missed" — useful for trend hunting.
    surprising_losses = []
    for s in settled:
        if s["status"] != "lost":
            continue
        leg_results = s.get("leg_results") or []
        for l in leg_results:
            if l.get("outcome") == "lost" and int(l.get("odds", 0)) >= 200:
                surprising_losses.append({
                    "slip_id": s["id"],
                    "leg_label": l.get("label"),
                    "event_label": l.get("event_label"),
                    "odds": l.get("odds"),
                })
    surprising_losses = surprising_losses[:5]

    return {
        "summary": {
            "bankroll": sess.bankroll,
            "starting_bankroll": sess.starting_bankroll,
            "net_profit": sess.bankroll - sess.starting_bankroll,
            "total_staked": sess.total_staked,
            "total_returned": sess.total_returned,
            "roi_pct": round(roi * 100, 2),
            "slips_placed": sess.slips_placed,
            "slips_won": sess.slips_won,
            "slips_lost": sess.slips_lost,
            "slips_pushed": sess.slips_pushed,
            "win_rate_pct": round(win_rate * 100, 1),
            "settled_count": total_settled,
            "wins": wins,
            "losses": losses,
            "pushes": pushes,
        },
        "by_market_type": by_market,
        "by_slip_type": by_slip_type,
        "streak": {"sign": streak_sign, "count": streak_count},
        "surprising_losses": surprising_losses,
    }
