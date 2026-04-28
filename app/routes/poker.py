"""Poker API namespace. Phase 1 surface is intentionally tiny — confirms
the route registration works, exposes the deck-builder for client UI to
use ahead of the variant DSL landing in phase 3.
"""
from __future__ import annotations

import json

from flask import Blueprint, jsonify, request

from ..db import db
from ..poker.ai import all_personalities
from ..poker.cards import poker_card_from_token, poker_card_to_token
from ..poker.companion import analyze
from ..poker.deck import DeckSpec, PokerShoe
from ..poker.equity import EquityError, monte_carlo_equity
from ..poker.pot import BetAction
from ..poker.variants import VariantSpec, all_variants
from ..services.poker_games import (
    GameError,
    POKER_COOKIE,
    active_hand_view,
    create_session,
    get_current_session,
    session_stats,
    start_hand,
    take_action,
    take_discard,
)

bp = Blueprint("poker", __name__, url_prefix="/api/v1/poker")

POKER_COOKIE_MAX_AGE = 60 * 60 * 24 * 60   # 60 days


def _attach_cookie(response, token: str):
    response.set_cookie(
        POKER_COOKIE, token,
        max_age=POKER_COOKIE_MAX_AGE,
        httponly=True, samesite="Lax", secure=False,
    )
    return response


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
    """Built-in variant library merged with user-saved variants
    (SettingsTemplate rows with game_type='poker'). Built-ins come first."""
    from ..models import SettingsTemplate

    payload = [v.to_dict() for v in all_variants()]
    user_saved = (
        SettingsTemplate.query
        .filter_by(game_type="poker", is_builtin=False)
        .order_by(SettingsTemplate.name.asc())
        .all()
    )
    for t in user_saved:
        # User templates store the variant blob in rules_json (we reuse the
        # column rather than adding a new one for v1).
        spec = json.loads(t.rules_json)
        spec.setdefault("name", t.name)
        spec.setdefault("description", t.description)
        # Annotate so the UI can show 'saved' and offer a delete control.
        spec["_saved_template_id"] = t.id
        payload.append(spec)
    return jsonify(variants=payload)


@bp.post("/variants")
def save_variant():
    """Persist a user-built variant under SettingsTemplate(game_type='poker').
    Body must be a complete VariantSpec dict (the same shape POST /analyze
    accepts inline)."""
    from ..models import SettingsTemplate

    body = request.get_json() or {}
    try:
        spec = VariantSpec.from_dict(body)
    except (KeyError, ValueError) as e:
        return _err(str(e), "BAD_REQUEST")
    name = spec.name.strip()
    if not name:
        return _err("name required", "BAD_REQUEST")
    if SettingsTemplate.query.filter_by(name=name).first():
        return _err("name already exists", "DUPLICATE")
    t = SettingsTemplate(
        game_type="poker",
        name=name,
        description=spec.description,
        rules_json=json.dumps(spec.to_dict()),
        side_bets_json="{}",
        is_builtin=False,
    )
    db.session.add(t)
    db.session.commit()
    out = spec.to_dict()
    out["_saved_template_id"] = t.id
    return jsonify(out), 201


@bp.delete("/variants/<int:template_id>")
def delete_variant(template_id: int):
    from ..models import SettingsTemplate

    t = db.session.get(SettingsTemplate, template_id)
    if not t or t.game_type != "poker":
        return _err("variant not found", "NOT_FOUND", 404)
    if t.is_builtin:
        return _err("cannot delete a built-in variant", "BUILTIN_READ_ONLY", 403)
    db.session.delete(t)
    db.session.commit()
    return ("", 204)


@bp.get("/personalities")
def list_personalities():
    return jsonify(personalities=all_personalities())


# ---- simulator session ------------------------------------------------

@bp.post("/sessions")
def create_session_endpoint():
    body = request.get_json() or {}
    variant_name = body.get("variant", "Texas Hold'em")
    variant = next((v for v in all_variants() if v.name == variant_name), None)
    if variant is None:
        return _err(f"unknown variant: {variant_name}", "BAD_REQUEST")
    try:
        starting_stack = int(body.get("starting_stack", 1000))
        small_blind = int(body.get("small_blind", 5))
        big_blind = int(body.get("big_blind", 10))
        bots = body.get("bots") or []
        sess = create_session(
            variant=variant,
            starting_stack=starting_stack,
            small_blind=small_blind,
            big_blind=big_blind,
            bots=bots,
            human_name=body.get("human_name") or "You",
        )
    except (ValueError, KeyError) as e:
        return _err(str(e), "BAD_REQUEST")
    response = jsonify(sess.to_dict())
    response.status_code = 201
    return _attach_cookie(response, sess.token)


@bp.get("/sessions/me")
def get_session_endpoint():
    sess = get_current_session()
    if not sess:
        return _err("no active poker session", "NO_SESSION", 404)
    return jsonify(sess.to_dict())


@bp.delete("/sessions/me")
def delete_session_endpoint():
    sess = get_current_session()
    if not sess:
        return _err("no active poker session", "NO_SESSION", 404)
    db.session.delete(sess)
    db.session.commit()
    response = jsonify(deleted=True)
    response.set_cookie(POKER_COOKIE, "", max_age=0)
    return response


@bp.post("/sessions/me/hands")
def start_hand_endpoint():
    sess = get_current_session()
    if not sess:
        return _err("no active poker session", "NO_SESSION", 404)
    try:
        view = start_hand(sess)
    except GameError as e:
        return _err(str(e), "GAME_ERROR", 409)
    return jsonify(view), 201


@bp.get("/sessions/me/hands/active")
def active_hand_endpoint():
    sess = get_current_session()
    if not sess:
        return _err("no active poker session", "NO_SESSION", 404)
    view = active_hand_view(sess)
    if view is None:
        return _err("no hand in progress", "NO_HAND", 404)
    return jsonify(view)


@bp.get("/sessions/me/stats")
def session_stats_endpoint():
    sess = get_current_session()
    if not sess:
        return _err("no active poker session", "NO_SESSION", 404)
    return jsonify(session_stats(sess))


@bp.post("/sessions/me/hands/active/action")
def hand_action_endpoint():
    sess = get_current_session()
    if not sess:
        return _err("no active poker session", "NO_SESSION", 404)
    body = request.get_json() or {}
    action_str = body.get("action")
    try:
        action = BetAction(action_str)
    except ValueError:
        return _err(f"invalid action: {action_str}", "BAD_REQUEST")
    amount = body.get("amount")
    if amount is not None and not isinstance(amount, int):
        return _err("amount must be int or null", "BAD_REQUEST")
    try:
        view = take_action(sess, action, amount)
    except GameError as e:
        return _err(str(e), "GAME_ERROR", 409)
    return jsonify(view)


@bp.post("/sessions/me/hands/active/discard")
def hand_discard_endpoint():
    """Draw poker only: human picks card indices to discard. Body:
      { "indices": [0, 2] }   # 0-indexed against the player's 5 hole cards
    """
    sess = get_current_session()
    if not sess:
        return _err("no active poker session", "NO_SESSION", 404)
    body = request.get_json() or {}
    indices = body.get("indices")
    if not isinstance(indices, list) or not all(isinstance(i, int) for i in indices):
        return _err("indices must be a list of ints", "BAD_REQUEST")
    try:
        view = take_discard(sess, indices)
    except GameError as e:
        return _err(str(e), "GAME_ERROR", 409)
    return jsonify(view)


# ---- companion (existing) --------------------------------------------

@bp.post("/equity")
def equity_endpoint():
    """Monte Carlo equity estimate. Body:
      { "variant": "Texas Hold'em" | {variant dict},
        "hole": ["AS", "KS"],
        "board": ["TS", "9D", "2C"],
        "opponents": 2,
        "iterations": 2000,
        "seed": 42 (optional) }

    Community-card variants only; no wilds in v1.
    """
    body = request.get_json() or {}
    variant_input = body.get("variant")
    try:
        if isinstance(variant_input, str):
            variant = next((v for v in all_variants() if v.name == variant_input), None)
            if variant is None:
                return _err(f"unknown variant: {variant_input}", "BAD_REQUEST", 404)
        elif isinstance(variant_input, dict):
            variant = VariantSpec.from_dict(variant_input)
        else:
            return _err("variant required (name or dict)", "BAD_REQUEST")

        hole = [poker_card_from_token(t) for t in body.get("hole", [])]
        board = [poker_card_from_token(t) for t in body.get("board", [])]
        result = monte_carlo_equity(
            variant, hole, board,
            opponents=int(body.get("opponents", 1)),
            iterations=int(body.get("iterations", 2000)),
            seed=body.get("seed"),
        )
    except (EquityError, KeyError, ValueError) as e:
        return _err(str(e), "BAD_REQUEST")
    return jsonify(result)


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
        # Per-hand wild marking: positions (in the consolidated cards list,
        # or hole+board concatenated for Omaha) the user has tap-marked
        # as wild for this hand only — covers 'follow the queen' triggers.
        extra = body.get("wild_indices")
        if extra is not None and not isinstance(extra, list):
            return _err("wild_indices must be a list of ints", "BAD_REQUEST")
        if extra is not None:
            extra = [int(i) for i in extra]

        result = analyze(
            variant, cards, hole=hole, board=board,
            extra_wild_indices=extra,
        )
    except (KeyError, ValueError) as e:
        return _err(str(e), "BAD_REQUEST")

    return jsonify(result.to_dict())
