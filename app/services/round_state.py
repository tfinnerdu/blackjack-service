"""Round snapshot + restore. Serializes engine.Round + Shoe state to JSON
so an in-flight round can survive a process restart, page reload, or
a phone losing the tab in the background.

Keeps the engine pure: the engine module never imports JSON or sees
this code.
"""
from __future__ import annotations

import json
from typing import Any

from ..engine.cards import card_from_token, card_to_token
from ..engine.hand import Hand
from ..engine.round import (
    Round,
    RoundState,
    Seat,
    SideBetWagers,
)
from ..engine.rules import Rules, SideBets
from ..engine.shoe import Shoe


def _hand_to_dict(h: Hand) -> dict:
    return {
        "cards": [card_to_token(c) for c in h.cards],
        "bet": h.bet,
        "doubled": h.doubled,
        "surrendered": h.surrendered,
        "is_split_hand": h.is_split_hand,
        "from_split_aces": h.from_split_aces,
        "insurance_bet": h.insurance_bet,
        "stood": h.stood,
        "finished": h.finished,
    }


def _hand_from_dict(d: dict) -> Hand:
    return Hand(
        cards=[card_from_token(t) for t in d["cards"]],
        bet=d["bet"],
        doubled=d["doubled"],
        surrendered=d["surrendered"],
        is_split_hand=d["is_split_hand"],
        from_split_aces=d["from_split_aces"],
        insurance_bet=d["insurance_bet"],
        stood=d["stood"],
        finished=d["finished"],
    )


def _seat_to_dict(s: Seat) -> dict:
    sb = s.side_bets
    return {
        "seat_num": s.seat_num,
        "main_bet": s.main_bet,
        "is_human": s.is_human,
        "bankroll_before": s.bankroll_before,
        "insurance_decided": s.insurance_decided,
        "side_bet_results": dict(s.side_bet_results),
        "finished": s.finished,
        "side_bets": {
            "twenty_one_plus_three": sb.twenty_one_plus_three,
            "perfect_pairs": sb.perfect_pairs,
            "lucky_ladies": sb.lucky_ladies,
            "royal_match": sb.royal_match,
            "match_the_dealer": sb.match_the_dealer,
            "over_under_13": sb.over_under_13,
            "over_under_pick": sb.over_under_pick,
            "bust_it": sb.bust_it,
            "buster_blackjack": sb.buster_blackjack,
        },
        "hands": [_hand_to_dict(h) for h in s.hands],
    }


def _seat_from_dict(d: dict) -> Seat:
    sb = SideBetWagers(
        twenty_one_plus_three=d["side_bets"]["twenty_one_plus_three"],
        perfect_pairs=d["side_bets"]["perfect_pairs"],
        lucky_ladies=d["side_bets"]["lucky_ladies"],
        royal_match=d["side_bets"]["royal_match"],
        match_the_dealer=d["side_bets"]["match_the_dealer"],
        over_under_13=d["side_bets"]["over_under_13"],
        over_under_pick=d["side_bets"]["over_under_pick"],
        bust_it=d["side_bets"]["bust_it"],
        buster_blackjack=d["side_bets"]["buster_blackjack"],
    )
    seat = Seat(
        seat_num=d["seat_num"],
        main_bet=d["main_bet"],
        side_bets=sb,
        is_human=d["is_human"],
        bankroll_before=d["bankroll_before"],
        insurance_decided=d["insurance_decided"],
        side_bet_results=dict(d["side_bet_results"]),
        finished=d["finished"],
    )
    seat.hands = [_hand_from_dict(h) for h in d["hands"]]
    return seat


def round_to_dict(rnd: Round, *, cards_dealt_at_start: int, cards_consumed: int) -> dict:
    """Serialize a round. Caller passes shoe positioning info since the
    engine.Round doesn't track 'how far into the session' the shoe was
    when this round began.
    """
    return {
        "state": rnd.state.value,
        "cards_dealt_at_start": cards_dealt_at_start,
        "cards_consumed": cards_consumed,
        "active_seat_idx": rnd._active_seat_idx,
        "active_hand_idx": rnd._active_hand_idx,
        "split_counts": {str(k): v for k, v in rnd._split_count_per_seat.items()},
        "dealer": _hand_to_dict(rnd.dealer),
        "seats": [_seat_to_dict(s) for s in rnd.seats],
    }


def round_from_dict(
    data: dict,
    rules: Rules,
    side_bets: SideBets,
    shoe: Shoe,
) -> Round:
    """Reconstruct a Round. The shoe must already be positioned correctly
    (i.e., burned forward to cards_dealt_at_start + cards_consumed)."""
    rnd = Round(rules, side_bets, shoe)
    rnd.state = RoundState(data["state"])
    rnd._active_seat_idx = data["active_seat_idx"]
    rnd._active_hand_idx = data["active_hand_idx"]
    rnd._split_count_per_seat = {int(k): v for k, v in data["split_counts"].items()}
    rnd.dealer = _hand_from_dict(data["dealer"])
    rnd.seats = [_seat_from_dict(s) for s in data["seats"]]
    return rnd


def round_to_json(rnd: Round, *, cards_dealt_at_start: int, cards_consumed: int) -> str:
    return json.dumps(round_to_dict(
        rnd,
        cards_dealt_at_start=cards_dealt_at_start,
        cards_consumed=cards_consumed,
    ))


def round_from_json(payload: str, rules: Rules, side_bets: SideBets, shoe: Shoe) -> Round:
    return round_from_dict(json.loads(payload), rules, side_bets, shoe)
