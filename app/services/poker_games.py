"""Poker simulator service. Mirrors blackjack/services/games.py:

  start_session: build a PokerSession with variant + bots + initial stacks
  start_hand: build HoldemRound, post blinds, deal, auto-play to human
  take_action: apply human's bet action; auto-play AI seats forward;
               settle when the hand completes
  active_hand: read-only view (resume after page reload)

The HoldemRound is rebuilt each request from the persisted snapshot — we
serialize seats / pot / state / community / holes per hand, plus the shoe
seed + cards-dealt counter so the deck stays deterministic across requests.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from typing import Any, Optional

from flask import Request, request

from ..config import Config
from ..db import db
from ..models import PokerSession
from ..poker.ai import AIBot, get_personality
from ..poker.cards import (
    PokerCard,
    poker_card_from_token,
    poker_card_to_token,
)
from ..poker.deck import DeckSpec, PokerShoe
from ..poker.pot import BetAction, Player, Pot
from ..poker.round import HandConfig, HoldemRound, RoundState
from ..poker.variants import VariantSpec

POKER_COOKIE = "bj_poker_session"
TOKEN_QUERY = "poker_session"


class GameError(Exception):
    """Caller-visible errors (bad input, illegal action, no hand, ...)."""


# ---- token / session lookup ------------------------------------------

def get_token(req: Optional[Request] = None) -> Optional[str]:
    req = req or request
    return (
        req.cookies.get(POKER_COOKIE)
        or req.args.get(TOKEN_QUERY)
        or req.headers.get("X-Poker-Session-Token")
    )


def get_current_session(req: Optional[Request] = None) -> Optional[PokerSession]:
    token = get_token(req)
    if not token:
        return None
    return PokerSession.query.filter_by(token=token).first()


# ---- session creation ------------------------------------------------

@dataclass
class SeatConfig:
    """One row of seats_json. Persisted as-is; each round we instantiate
    a fresh Player + (for non-humans) AIBot from this row."""
    seat_num: int
    name: str
    is_human: bool
    stack: int
    personality: str = "book"
    seed: Optional[int] = None
    last_results: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "seat_num": self.seat_num,
            "name": self.name,
            "is_human": self.is_human,
            "stack": self.stack,
            "personality": self.personality,
            "seed": self.seed,
            "last_results": list(self.last_results),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SeatConfig":
        return cls(
            seat_num=d["seat_num"],
            name=d["name"],
            is_human=bool(d["is_human"]),
            stack=int(d["stack"]),
            personality=d.get("personality", "book"),
            seed=d.get("seed"),
            last_results=list(d.get("last_results", [])),
        )


def create_session(
    *,
    variant: VariantSpec,
    starting_stack: int,
    small_blind: int = 5,
    big_blind: int = 10,
    bots: list[dict],
    human_name: str = "You",
    human_seat: int = 1,
    dealer_seat: int = 1,
) -> PokerSession:
    """Spin up a new poker session. `bots` is a list of {name, personality}
    dicts describing the AI seats; we assign seat numbers 2..N+1 by default
    (with the human in seat 1)."""
    seats: list[SeatConfig] = []
    seats.append(SeatConfig(
        seat_num=human_seat, name=human_name, is_human=True, stack=starting_stack,
        personality="book",
    ))
    used = {human_seat}
    next_seat = 1
    for b in bots:
        # Pick the next free seat number.
        while next_seat in used:
            next_seat += 1
        used.add(next_seat)
        # Personality validation up-front so bad input fails at creation.
        get_personality(b.get("personality", "book"))
        seats.append(SeatConfig(
            seat_num=next_seat,
            name=b.get("name") or f"Bot {next_seat}",
            is_human=False,
            stack=starting_stack,
            personality=b.get("personality", "book"),
            seed=b.get("seed"),
        ))

    config_json = json.dumps({
        "small_blind": small_blind,
        "big_blind": big_blind,
        "starting_stack": starting_stack,
    })

    sess = PokerSession(
        variant_json=json.dumps(variant.to_dict()),
        config_json=config_json,
        seats_json=json.dumps([s.to_dict() for s in seats]),
        dealer_seat=dealer_seat,
        starting_bankroll=starting_stack,
        active_hand_json=None,
    )
    db.session.add(sess)
    db.session.commit()
    return sess


# ---- hand snapshot/restore -------------------------------------------

def _variant(sess: PokerSession) -> VariantSpec:
    return VariantSpec.from_dict(json.loads(sess.variant_json))


def _config(sess: PokerSession) -> dict:
    return json.loads(sess.config_json)


def _seats(sess: PokerSession) -> list[SeatConfig]:
    return [SeatConfig.from_dict(d) for d in json.loads(sess.seats_json)]


def _save_seats(sess: PokerSession, seats: list[SeatConfig]) -> None:
    sess.seats_json = json.dumps([s.to_dict() for s in seats])


def _build_players(seats: list[SeatConfig]) -> list[Player]:
    return [
        Player(seat_num=s.seat_num, name=s.name, stack=s.stack, is_human=s.is_human)
        for s in seats
    ]


def _build_bots(seats: list[SeatConfig]) -> dict[int, AIBot]:
    bots: dict[int, AIBot] = {}
    for s in seats:
        if s.is_human:
            continue
        bot = AIBot(
            seat_num=s.seat_num,
            name=s.name,
            personality=s.personality,
            seed=s.seed,
        )
        bot.last_results = list(s.last_results)
        bots[s.seat_num] = bot
    return bots


def _hand_to_dict(rnd: HoldemRound, *, shoe_seed: int, cards_dealt: int) -> dict:
    return {
        "shoe_seed": shoe_seed,
        "cards_dealt": cards_dealt,
        "state": rnd.state.value,
        "community": [poker_card_to_token(c) for c in rnd.community],
        "holes": {
            str(seat): [poker_card_to_token(c) for c in cards]
            for seat, cards in rnd.holes.items()
        },
        "pot_committed": dict(rnd.pot.committed),
        "pot_total": rnd.pot.total,
        "pot_street_total": rnd.pot.current_street_total,
        "current_bet": rnd.current_bet,
        "last_raise": rnd.last_raise,
        "active_seat": rnd.active_seat.seat_num if rnd.active_seat else None,
        "dealer_seat": rnd.config.dealer_seat,
        "small_blind": rnd.config.small_blind,
        "big_blind": rnd.config.big_blind,
        "players": [
            {
                "seat_num": p.seat_num,
                "stack": p.stack,
                "folded": p.folded,
                "all_in": p.all_in,
                "committed_this_round": p.committed_this_round,
                "committed_total": p.committed_total,
                "has_acted_this_round": p.has_acted_this_round,
            }
            for p in rnd.players
        ],
    }


def _hand_from_dict(d: dict, sess: PokerSession) -> HoldemRound:
    """Reconstruct a HoldemRound from persisted state. Rebuilds the shoe
    by reseeding and burning the dealt-so-far count."""
    variant = _variant(sess)
    cfg = HandConfig(
        small_blind=d["small_blind"], big_blind=d["big_blind"],
        dealer_seat=d["dealer_seat"],
    )
    seats = _seats(sess)
    players = _build_players(seats)

    # Apply persisted per-player state (stack already reflects committed chips).
    saved_players = {p["seat_num"]: p for p in d["players"]}
    for p in players:
        sp = saved_players.get(p.seat_num)
        if sp is None:
            continue
        p.stack = sp["stack"]
        p.folded = sp["folded"]
        p.all_in = sp["all_in"]
        p.committed_this_round = sp["committed_this_round"]
        p.committed_total = sp["committed_total"]
        p.has_acted_this_round = sp["has_acted_this_round"]

    shoe = PokerShoe(variant.deck, seed=d["shoe_seed"])
    for _ in range(int(d["cards_dealt"])):
        shoe.next_card()

    rnd = HoldemRound(variant, players, cfg, shoe=shoe)
    rnd.state = RoundState(d["state"])
    rnd.community = [poker_card_from_token(t) for t in d["community"]]
    rnd.holes = {
        int(seat): [poker_card_from_token(t) for t in tokens]
        for seat, tokens in d["holes"].items()
    }
    # Restore pot state.
    rnd.pot.committed = {int(k): int(v) for k, v in d["pot_committed"].items()}
    rnd.pot.total = int(d["pot_total"])
    rnd.pot.current_street_total = int(d["pot_street_total"])
    rnd.current_bet = int(d["current_bet"])
    rnd.last_raise = int(d["last_raise"])
    # Active index from seat number.
    if d["active_seat"] is not None:
        rnd.active_index = next(
            i for i, p in enumerate(rnd.players) if p.seat_num == d["active_seat"]
        )
    # _starting_stacks needs to reflect the snapshot of stack at hand start;
    # we infer it from current stack + committed_total (chips that left the
    # stack went to the pot).
    rnd._starting_stacks = {
        p.seat_num: p.stack + p.committed_total for p in players
    }
    return rnd


# ---- AI auto-play ----------------------------------------------------

def _is_pre_flop(rnd: HoldemRound) -> bool:
    return rnd.state == RoundState.PRE_FLOP


def _auto_play_until_human_or_done(
    rnd: HoldemRound, bots: dict[int, AIBot],
) -> None:
    """Run AI seats until the human is up to act, or the hand is done."""
    while rnd.state not in (RoundState.SHOWDOWN, RoundState.COMPLETE):
        seat = rnd.active_seat
        if seat is None:
            return
        if seat.is_human:
            return
        bot = bots.get(seat.seat_num)
        if bot is None:
            # No bot config for this seat — fold defensively.
            rnd.act(BetAction.FOLD)
            continue
        from ..poker.pot import min_raise_to as min_raise
        move = bot.decide(
            hole=rnd.holes[seat.seat_num],
            community=list(rnd.community),
            pot_size=rnd.pot.total,
            to_call=rnd.amount_to_call(),
            min_raise_to=min_raise(rnd.current_bet, rnd.last_raise, rnd.config.big_blind),
            big_blind=rnd.config.big_blind,
            stack=seat.stack,
            legal_actions=list(rnd.legal_actions()),
            is_pre_flop=_is_pre_flop(rnd),
        )
        # Defensive: if the personality picked something illegal somehow,
        # fall back to the safest legal action.
        action = move.action if move.action in rnd.legal_actions() else _safe_fallback(rnd)
        amount = move.amount
        try:
            rnd.act(action, amount)
        except ValueError:
            rnd.act(_safe_fallback(rnd))


def _safe_fallback(rnd: HoldemRound) -> BetAction:
    legal = rnd.legal_actions()
    for pref in (BetAction.CHECK, BetAction.FOLD, BetAction.CALL):
        if pref in legal:
            return pref
    return legal[0]


# ---- public API ------------------------------------------------------

def start_hand(sess: PokerSession) -> dict:
    if sess.active_hand_json:
        raise GameError("a hand is already in progress; finish it first")

    seats = _seats(sess)
    cfg = _config(sess)
    variant = _variant(sess)

    # Drop seats that can't post the BB.
    live_seats = [s for s in seats if s.stack >= cfg["big_blind"]]
    if len(live_seats) < 2:
        raise GameError("need at least 2 seats with the big blind in chips")

    players = _build_players(live_seats)
    bots = _build_bots(live_seats)
    seed = random.randint(0, 2**31 - 1)
    shoe = PokerShoe(variant.deck, seed=seed)
    rnd = HoldemRound(variant, players, HandConfig(
        small_blind=cfg["small_blind"],
        big_blind=cfg["big_blind"],
        dealer_seat=sess.dealer_seat,
    ), shoe=shoe)
    rnd.start()
    _auto_play_until_human_or_done(rnd, bots)

    if rnd.state == RoundState.COMPLETE:
        _settle_hand(sess, rnd, seats, bots)
    else:
        sess.active_hand_json = json.dumps(_hand_to_dict(
            rnd, shoe_seed=seed, cards_dealt=shoe.cards_dealt,
        ))
    db.session.commit()
    return _round_view(rnd, sess)


def take_action(
    sess: PokerSession, action: BetAction, amount: Optional[int] = None,
) -> dict:
    if not sess.active_hand_json:
        raise GameError("no hand in progress")
    payload = json.loads(sess.active_hand_json)
    rnd = _hand_from_dict(payload, sess)
    seats = _seats(sess)
    bots = _build_bots(seats)

    seat = rnd.active_seat
    if seat is None or not seat.is_human:
        raise GameError("not the human's turn")

    if action not in rnd.legal_actions():
        raise GameError(f"illegal action; legal: {[a.value for a in rnd.legal_actions()]}")

    rnd.act(action, amount)
    _auto_play_until_human_or_done(rnd, bots)

    # Compute new cards-dealt count from the now-extended round state.
    seed = int(payload["shoe_seed"])
    new_cards_dealt = _cards_dealt_from_round(rnd)

    if rnd.state == RoundState.COMPLETE:
        _settle_hand(sess, rnd, seats, bots)
    else:
        sess.active_hand_json = json.dumps(_hand_to_dict(
            rnd, shoe_seed=seed, cards_dealt=new_cards_dealt,
        ))
    db.session.commit()
    return _round_view(rnd, sess)


def active_hand_view(sess: PokerSession) -> Optional[dict]:
    if not sess.active_hand_json:
        return None
    payload = json.loads(sess.active_hand_json)
    rnd = _hand_from_dict(payload, sess)
    return _round_view(rnd, sess)


# ---- settlement / view --------------------------------------------------

def _cards_dealt_from_round(rnd: HoldemRound) -> int:
    """Total cards dealt = sum(holes) + community + 1 burn per community
    street that has been dealt."""
    holes_total = sum(len(v) for v in rnd.holes.values())
    community = len(rnd.community)
    burns = 0
    if community >= 3:
        burns += 1  # before flop
    if community >= 4:
        burns += 1  # before turn
    if community >= 5:
        burns += 1  # before river
    return holes_total + community + burns


def _settle_hand(
    sess: PokerSession, rnd: HoldemRound,
    seats: list[SeatConfig], bots: dict[int, AIBot],
) -> None:
    """Fold settled stacks back into seats_json + clear active_hand_json."""
    for seat in seats:
        # Find the corresponding Player in the just-completed round; if it
        # didn't have enough to play, leave the seat untouched.
        live = next((p for p in rnd.players if p.seat_num == seat.seat_num), None)
        if live is None:
            continue
        seat.stack = live.stack
        # Update bot history.
        bot = bots.get(seat.seat_num)
        if bot:
            outcome = next(
                (o for o in (rnd.result.outcomes if rnd.result else []) if o.seat_num == seat.seat_num),
                None,
            )
            if outcome:
                bot.record_result(outcome.profit)
                seat.last_results = list(bot.last_results)

    _save_seats(sess, seats)
    sess.active_hand_json = None
    sess.hands_played += 1
    # Move dealer button.
    seat_nums = sorted([s.seat_num for s in seats])
    cur = sess.dealer_seat
    idx = seat_nums.index(cur) if cur in seat_nums else 0
    sess.dealer_seat = seat_nums[(idx + 1) % len(seat_nums)]


def _round_view(rnd: HoldemRound, sess: PokerSession) -> dict:
    """JSON-friendly summary of the active round."""
    seats = _seats(sess)
    seat_lookup = {s.seat_num: s for s in seats}
    players_view = []
    for p in rnd.players:
        cfg_seat = seat_lookup.get(p.seat_num)
        players_view.append({
            "seat_num": p.seat_num,
            "name": p.name,
            "is_human": p.is_human,
            "personality": cfg_seat.personality if cfg_seat else None,
            "stack": p.stack,
            "committed_this_round": p.committed_this_round,
            "folded": p.folded,
            "all_in": p.all_in,
            "is_active": rnd.active_seat is not None and rnd.active_seat.seat_num == p.seat_num,
        })
    human = next((p for p in rnd.players if p.is_human), None)
    human_hole: list[str] = []
    if human is not None:
        human_hole = [poker_card_to_token(c) for c in rnd.holes.get(human.seat_num, [])]

    legal: list[str] = []
    if rnd.active_seat is not None and rnd.active_seat.is_human:
        legal = [a.value for a in rnd.legal_actions()]

    result_view = None
    if rnd.state == RoundState.COMPLETE and rnd.result is not None:
        result_view = {
            "winner_seats": list(rnd.result.winner_seats),
            "pot_total": rnd.result.pot_total,
            "side_pots": list(rnd.result.side_pots),
            "community": list(rnd.result.community),
            "outcomes": [
                {
                    "seat_num": o.seat_num,
                    "profit": o.profit,
                    "final_hand_name": o.final_hand_name,
                    "final_cards": list(o.final_cards),
                    "won": o.won,
                    "reason": o.reason,
                }
                for o in rnd.result.outcomes
            ],
        }

    return {
        "state": rnd.state.value,
        "community": [poker_card_to_token(c) for c in rnd.community],
        "human_hole": human_hole,
        "pot_total": rnd.pot.total,
        "current_bet": rnd.current_bet,
        "to_call": rnd.amount_to_call() if rnd.active_seat else 0,
        "legal_actions": legal,
        "active_seat": rnd.active_seat.seat_num if rnd.active_seat else None,
        "players": players_view,
        "result": result_view,
        "dealer_seat": sess.dealer_seat,
    }


__all__ = [
    "GameError",
    "POKER_COOKIE",
    "TOKEN_QUERY",
    "active_hand_view",
    "create_session",
    "get_current_session",
    "get_token",
    "start_hand",
    "take_action",
]
