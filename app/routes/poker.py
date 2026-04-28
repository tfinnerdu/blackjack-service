"""Poker API namespace. Phase 1 surface is intentionally tiny — confirms
the route registration works, exposes the deck-builder for client UI to
use ahead of the variant DSL landing in phase 3.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..poker.cards import poker_card_from_token, poker_card_to_token
from ..poker.companion import analyze
from ..poker.deck import DeckSpec, PokerShoe
from ..poker.variants import VariantSpec, all_variants

bp = Blueprint("poker", __name__, url_prefix="/api/v1/poker")


def _err(msg: str, code: str, status: int = 400):
    return jsonify(error=msg, code=code), status


@bp.get("/health")
def health():
    return jsonify(status="ok", service="blackjack-service", module="poker")


@bp.post("/deck/peek")
def deck_peek():
    """Build a deck from spec + seed and return the first N cards as tokens.
    Sanity-check endpoint — keep around for the deck-preview UI."""
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


@bp.get("/variants")
def list_variants():
    """Built-in variant library. Phase 4 layers user-saved variants from
    SettingsTemplate (game_type='poker') on top of these."""
    return jsonify(variants=[v.to_dict() for v in all_variants()])


@bp.post("/analyze")
def analyze_endpoint():
    """Companion mode. Body:
      {
        "variant": "Texas Hold'em" | { full VariantSpec dict },
        "cards": ["AS", "KS", ...]                     # for non-Omaha variants
        "hole":  ["AS", "KS", ...]                     # Omaha variants only
        "board": ["2H", "3H", ...]                     # Omaha variants only
      }
    """
    body = request.get_json() or {}
    variant_input = body.get("variant")
    if variant_input is None:
        return _err("variant required", "BAD_REQUEST")

    try:
        if isinstance(variant_input, str):
            variant = next(
                (v for v in all_variants() if v.name == variant_input), None
            )
            if variant is None:
                return _err(f"unknown variant: {variant_input}", "BAD_REQUEST", 404)
        elif isinstance(variant_input, dict):
            variant = VariantSpec.from_dict(variant_input)
        else:
            return _err("variant must be a name or full dict", "BAD_REQUEST")

        cards = [poker_card_from_token(t) for t in body.get("cards", [])]
        hole = [poker_card_from_token(t) for t in body.get("hole", [])] if body.get("hole") else None
        board = [poker_card_from_token(t) for t in body.get("board", [])] if body.get("board") else None

        result = analyze(variant, cards, hole=hole, board=board)
    except (KeyError, ValueError) as e:
        return _err(str(e), "BAD_REQUEST")

    return jsonify(result.to_dict())
