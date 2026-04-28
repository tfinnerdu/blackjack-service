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


def monte_carlo_equity(
    variant: VariantSpec,
    hole: list[PokerCard],
    board: list[PokerCard],
    *,
    opponents: int = 1,
    iterations: int = 2000,
    seed: Optional[int] = None,
) -> dict:
    """Estimate hero's win / tie / loss frequency.

    Hero plays `hole` against `opponents` random hands from the remaining
    deck; the rest of the board is dealt randomly per iteration.
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
    if variant.wilds:
        raise EquityError(
            "equity sim doesn't support variants with wild rules (use the companion)"
        )
    if any(isinstance(c, Joker) for c in hole + board):
        raise EquityError("equity sim doesn't accept jokers in hole or board")
    if opponents < 1:
        raise EquityError("opponents must be >= 1")
    if iterations < 50 or iterations > 20000:
        raise EquityError("iterations must be 50..20000")

    n_hole = variant.deal.hole_cards
    if n_hole and len(hole) != n_hole:
        raise EquityError(f"variant requires {n_hole} hole cards, got {len(hole)}")

    target_community = sum(variant.deal.community_streets)
    if len(board) > target_community:
        raise EquityError(f"too many board cards (max {target_community})")

    # Remaining deck: full deck minus hole + board cards (token-deduped).
    used = {_token(c) for c in hole + board}
    deck_pool = build_deck(variant.deck)
    remaining: list[PokerCard] = []
    for c in deck_pool:
        if isinstance(c, Joker):
            continue  # we asserted no jokers above
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

    for _ in range(iterations):
        deck = list(remaining)
        rng.shuffle(deck)
        idx = 0
        opp_holes: list[list[PokerCard]] = []
        for _ in range(opponents):
            opp_holes.append(deck[idx:idx + n_hole])
            idx += n_hole
        completed_board = list(board) + deck[idx:idx + (target_community - len(board))]

        if is_omaha:
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
