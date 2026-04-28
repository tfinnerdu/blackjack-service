"""Poker API namespace. Phase 1 surface is intentionally tiny — confirms
the route registration works, exposes the deck-builder for client UI to
use ahead of the variant DSL landing in phase 3.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..poker.cards import poker_card_from_token, poker_card_to_token
from ..poker.deck import DeckSpec, PokerShoe

bp = Blueprint("poker", __name__, url_prefix="/api/v1/poker")


def _err(msg: str, code: str, status: int = 400):
    return jsonify(error=msg, code=code), status


@bp.get("/health")
def health():
    return jsonify(status="ok", service="blackjack-service", module="poker")


@bp.post("/deck/peek")
def deck_peek():
    """Build a deck from spec + seed and return the first N cards as tokens.
    Sanity-check endpoint — the variant DSL replaces this in phase 3."""
    body = request.get_json() or {}
    try:
        spec = DeckSpec(
            decks=int(body.get("decks", 1)),
            jokers=int(body.get("jokers", 0)),
        )
    except (TypeError, ValueError) as e:
        return _err(str(e), "BAD_REQUEST")
    seed = body.get("seed")
    n = int(body.get("count", 5))
    if n < 1 or n > spec.total_cards:
        return _err(f"count must be 1..{spec.total_cards}", "BAD_REQUEST")
    shoe = PokerShoe(spec, seed=seed)
    cards = shoe.deal(n)
    return jsonify(
        cards=[poker_card_to_token(c) for c in cards],
        deck_size=spec.total_cards,
        cards_remaining=shoe.cards_remaining,
    )
