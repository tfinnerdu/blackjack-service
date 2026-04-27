"""Strategy API. Stateless — caller sends the hand state + rules + optional
count; we return what the book says.

POST /api/v1/strategy/ask
{
  "hand": ["TS", "6H"],
  "dealer_up": "9C",
  "rules": { "dealer_hits_soft_17": true, "double_after_split": true, ... },
  "can_double": true,
  "can_split": false,
  "can_surrender": true,
  "true_count": 0.5    // optional
}

Response:
{
  "action": "stand",
  "source": "index",
  "deviation": "16 vs 10: stand at TC>=0",
  "basic_action": "hit"
}
"""
from __future__ import annotations

from dataclasses import fields
from typing import Any

from flask import Blueprint, jsonify, request

from ..engine.cards import Card, Suit, card_from_token
from ..engine.hand import Hand
from ..engine.rules import DoubleRule, Rules, ShuffleMode, SurrenderRule
from ..strategy import Capabilities, basic_strategy
from ..strategy.book import book

bp = Blueprint("strategy", __name__, url_prefix="/api/v1/strategy")


def _err(msg: str, code: str, status: int = 400):
    return jsonify(error=msg, code=code), status


def _parse_card(token: str) -> Card:
    return card_from_token(token)


# ---- rule coercion ----------------------------------------------------

_ENUM_FIELDS = {
    "shuffle_mode": ShuffleMode,
    "double_rule": DoubleRule,
    "surrender": SurrenderRule,
}


def _build_rules(rules_dict: dict[str, Any] | None) -> Rules:
    """Construct a Rules from a partial dict; missing fields use defaults."""
    rules_dict = rules_dict or {}
    valid_keys = {f.name for f in fields(Rules)}
    kwargs: dict[str, Any] = {}
    for k, v in rules_dict.items():
        if k not in valid_keys:
            continue
        if k in _ENUM_FIELDS and isinstance(v, str):
            v = _ENUM_FIELDS[k](v)
        elif k in ("blackjack_payout", "insurance_payout") and isinstance(v, list):
            v = tuple(v)
        kwargs[k] = v
    return Rules(**kwargs)


@bp.post("/ask")
def ask():
    body = request.get_json() or {}
    try:
        rules = _build_rules(body.get("rules"))
        cards = [_parse_card(t) for t in body.get("hand", [])]
        if len(cards) < 2:
            return _err("hand must have at least 2 cards", "BAD_REQUEST")
        dealer_up = _parse_card(body["dealer_up"])
    except (KeyError, ValueError) as e:
        return _err(str(e), "BAD_REQUEST")

    hand = Hand(cards=cards)
    caps = Capabilities(
        can_double=bool(body.get("can_double", len(cards) == 2)),
        can_split=bool(body.get("can_split", False)),
        can_surrender=bool(body.get("can_surrender", False)),
    )

    tc = body.get("true_count")
    if tc is not None:
        tc = float(tc)

    call = book(hand, dealer_up, rules, caps, true_count=tc)
    basic = basic_strategy(hand, dealer_up, rules, caps)

    return jsonify(
        action=call.action,
        source=call.source,
        deviation=call.deviation,
        basic_action=basic,
        note=call.note,
    )
