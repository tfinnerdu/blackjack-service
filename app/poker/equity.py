"""Monte Carlo equity estimator.

Given a variant + the user's hole cards + visible board + opponent count,
estimate win / tie / loss percentage by simulating the rest of the deal
many times against random opponent holdings.

Scope (v1):
  - Community-card variants only (Hold'em + Omaha + Hi/Lo)
  - Standard 52-card deck (no wild rules) — wild variants would need
    evaluate_with_wilds in the inner loop and we want this fast

A 2000-iteration run completes in well under 1s on a free-tier Render
worker for Hold'em with 5 opponents; 5000 iterations stays under a few
seconds. UI defaults to 2000.
"""
from __future__ import annotations

import random
from typing import Optional

from .cards import Card, Joker, PokerCard, poker_card_to_token
from .deck import build_deck
from .evaluator.high import best_high
from .variants import HandRequirement, VariantSpec


class EquityError(Exception):
    pass


def _token(c: PokerCard) -> str:
    return poker_card_to_token(c)


def _eval_with_wilds(
    hole: list[PokerCard],
    board: list[PokerCard],
    variant: VariantSpec,
    mode,  # WildMode (avoids top-level import cycle)
    is_omaha: bool,
):
    """Best high hand for a player + board respecting variant wild rules.

    Reuses the round-time path conceptually: identify wild cards via the
    variant's static rule matchers (joker / rank / suit / specific /
    one-eyed-jack), then iterate 5-card combos (or 2-from-hole + 3-from-
    board for Omaha) and substitute via evaluate_with_wilds.

    AFTER_RANK is NOT applied here — equity sims simulate community
    deals randomly, and we don't track 'next-card' adjacency. Variants
    that rely on triggers will get a slightly inflated estimate vs
    actual play; documented in the route response.
    """
    from itertools import combinations
    from .companion import _matches
    from .evaluator import classify_high, evaluate_with_wilds
    from .evaluator.high import best_high
    from .variants import WildKind

    static_rules = [r for r in variant.wilds if r.kind != WildKind.AFTER_RANK]

    def _is_wild(card: PokerCard) -> bool:
        return any(_matches(card, r) for r in static_rules)

    if is_omaha:
        candidates = [list(h) + list(b) for h in combinations(hole, 2)
                      for b in combinations(board, 3)]
    else:
        cards = list(hole) + list(board)
        candidates = [list(c) for c in combinations(cards, 5)]

    # Fast path when no card in any combo is wild — every candidate is
    # the same in that respect, so just pick best naturally.
    if not any(_is_wild(c) for c in (list(hole) + list(board))):
        if is_omaha:
            return best_high([], must_use=2, hole=hole, board=board)
        return best_high(list(hole) + list(board))

    best = None
    for combo in candidates:
        wild_in = [i for i, c in enumerate(combo) if _is_wild(c)]
        if wild_in:
            rank = evaluate_with_wilds(combo, wild_indices=wild_in, mode=mode)
        else:
            rank = classify_high(combo)
        if best is None or rank > best:
            best = rank
    return best


def monte_carlo_equity(
    variant: VariantSpec,
    hole: list[PokerCard],
    board: list[PokerCard],
    *,
    opponents: int = 1,
    iterations: Optional[int] = None,
    seed: Optional[int] = None,
) -> dict:
    """Estimate hero's win / tie / loss frequency.

    Hero plays `hole` against `opponents` random hands from the remaining
    deck; the rest of the board is dealt randomly per iteration.

    Wild variants are supported: the inner-loop evaluator switches to a
    wild-aware path that tries every 5-card combo and substitution. That's
    significantly slower than the no-wilds path, so the iteration default
    drops from 2000 -> 500 when the variant has wilds (the caller can
    still pass a custom value).
    """
    if variant.deal.up_cards or variant.deal.stud_streets or variant.deal.draws:
        raise EquityError("equity sim supports community-card variants only")
    if variant.hand not in (
        HandRequirement.BEST_5_OF_ALL,
        HandRequirement.OMAHA_2_HOLE_3_BOARD,
    ):
        raise EquityError(
            f"unsupported hand requirement: {variant.hand.value}"
        )
    if opponents < 1:
        raise EquityError("opponents must be >= 1")

    has_wilds = bool(variant.wilds) or variant.deck.jokers > 0
    if iterations is None:
        iterations = 500 if has_wilds else 2000
    if iterations < 50 or iterations > 20000:
        raise EquityError("iterations must be 50..20000")

    n_hole = variant.deal.hole_cards
    if n_hole and len(hole) != n_hole:
        raise EquityError(f"variant requires {n_hole} hole cards, got {len(hole)}")

    target_community = sum(variant.deal.community_streets)
    if len(board) > target_community:
        raise EquityError(f"too many board cards (max {target_community})")

    # Remaining deck: full deck minus hole + board cards (token-deduped).
    # Jokers stay in for variants that include them so they can land on the
    # board or in opponent holes.
    used = {_token(c) for c in hole + board}
    deck_pool = build_deck(variant.deck)
    remaining: list[PokerCard] = []
    for c in deck_pool:
        tok = _token(c)
        if tok in used:
            continue
        remaining.append(c)

    cards_per_iter = n_hole * opponents + (target_community - len(board))
    if cards_per_iter > len(remaining):
        raise EquityError("not enough cards left in the deck for this scenario")

    rng = random.Random(seed)
    is_omaha = variant.hand == HandRequirement.OMAHA_2_HOLE_3_BOARD
    wins = ties = losses = 0

    # Pick the strictest mode declared by any variant rule (matches what
    # round.py uses at showdown).
    if has_wilds:
        modes = {r.mode for r in variant.wilds}
        from .evaluator.wilds import WildMode as _WM
        if _WM.STRAIGHT_FLUSH_ONLY in modes:
            wild_mode = _WM.STRAIGHT_FLUSH_ONLY
        elif _WM.BUG in modes:
            wild_mode = _WM.BUG
        else:
            wild_mode = _WM.FULLY_WILD

    for _ in range(iterations):
        deck = list(remaining)
        rng.shuffle(deck)
        idx = 0
        opp_holes: list[list[PokerCard]] = []
        for _ in range(opponents):
            opp_holes.append(deck[idx:idx + n_hole])
            idx += n_hole
        completed_board = list(board) + deck[idx:idx + (target_community - len(board))]

        if has_wilds:
            hero_rank = _eval_with_wilds(
                hole, completed_board, variant, wild_mode, is_omaha,
            )
            opp_ranks = [
                _eval_with_wilds(oh, completed_board, variant, wild_mode, is_omaha)
                for oh in opp_holes
            ]
        elif is_omaha:
            hero_rank = best_high([], must_use=2, hole=hole, board=completed_board)
            opp_ranks = [
                best_high([], must_use=2, hole=oh, board=completed_board)
                for oh in opp_holes
            ]
        else:
            hero_rank = best_high(hole + completed_board)
            opp_ranks = [best_high(oh + completed_board) for oh in opp_holes]

        max_opp = max(opp_ranks)
        if hero_rank > max_opp:
            wins += 1
        elif hero_rank == max_opp:
            ties += 1
        else:
            losses += 1

    total = wins + ties + losses
    return {
        "variant": variant.name,
        "opponents": opponents,
        "iterations": iterations,
        "wins": wins,
        "ties": ties,
        "losses": losses,
        "win_pct": round(wins / total * 100, 2),
        "tie_pct": round(ties / total * 100, 2),
        "loss_pct": round(losses / total * 100, 2),
        "equity_pct": round((wins + ties / 2) / total * 100, 2),
    }


__all__ = ["EquityError", "monte_carlo_equity"]
