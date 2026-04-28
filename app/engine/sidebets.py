"""Side-bet evaluators. Each function returns the profit (not including the
returned stake) for the given config + cards. A loss returns -stake.

Inputs are intentionally narrow — these are pure functions of the cards
and the side-bet config, callable from the round orchestrator at the
right moment in a deal.
"""
from __future__ import annotations

from typing import Literal

from .cards import Card, RANKS, RANK_INDEX, Suit, hand_total, is_ten
from .rules import (
    BusterBlackjack,
    BustIt,
    LuckyLadies,
    MatchTheDealer,
    OverUnder13,
    Payout,
    PerfectPairs,
    RoyalMatch,
    SideBets,
    TwentyOnePlusThree,
    payout_amount,
)


def _loss(stake: int) -> int:
    return -stake


# ---- 21+3: poker hand of player's two cards + dealer up ----------------

def evaluate_21_plus_3(
    p1: Card, p2: Card, dealer_up: Card, cfg: TwentyOnePlusThree, stake: int
) -> int:
    if not cfg.enabled or stake <= 0:
        return 0
    cards = [p1, p2, dealer_up]
    suits = {c.suit for c in cards}
    ranks = sorted(RANK_INDEX[c.rank] for c in cards)
    same_suit = len(suits) == 1
    same_rank = len({c.rank for c in cards}) == 1

    # Straight: A can be low (A-2-3) or high (Q-K-A). With "A" at index 0 in
    # RANKS, the natural sorted indices catch A-2-3 (0,1,2). For Q-K-A we
    # special-case the {A,K,Q} set.
    is_straight = (
        ranks[2] - ranks[0] == 2 and len(set(ranks)) == 3
    ) or set(c.rank for c in cards) == {"A", "K", "Q"}

    if same_rank and same_suit:
        return payout_amount(stake, cfg.suited_three_of_a_kind)
    if is_straight and same_suit:
        return payout_amount(stake, cfg.straight_flush)
    if same_rank:
        return payout_amount(stake, cfg.three_of_a_kind)
    if is_straight:
        return payout_amount(stake, cfg.straight)
    if same_suit:
        return payout_amount(stake, cfg.flush)
    return _loss(stake)


# ---- Perfect Pairs -----------------------------------------------------

def evaluate_perfect_pairs(p1: Card, p2: Card, cfg: PerfectPairs, stake: int) -> int:
    if not cfg.enabled or stake <= 0:
        return 0
    if p1.rank != p2.rank:
        return _loss(stake)
    if p1.suit == p2.suit:
        return payout_amount(stake, cfg.perfect)
    if p1.color == p2.color:
        return payout_amount(stake, cfg.colored)
    return payout_amount(stake, cfg.mixed)


# ---- Lucky Ladies ------------------------------------------------------

def evaluate_lucky_ladies(
    p1: Card, p2: Card, cfg: LuckyLadies, stake: int, dealer_blackjack: bool
) -> int:
    if not cfg.enabled or stake <= 0:
        return 0
    total, _ = hand_total([p1, p2])
    if total != 20:
        return _loss(stake)

    queen_hearts = (
        p1.rank == "Q" and p1.suit == Suit.HEARTS
        and p2.rank == "Q" and p2.suit == Suit.HEARTS
    )
    if queen_hearts and dealer_blackjack:
        return payout_amount(stake, cfg.queen_hearts_pair_with_dealer_bj)
    if queen_hearts:
        return payout_amount(stake, cfg.queen_hearts_pair)
    if p1.rank == p2.rank and p1.suit == p2.suit:
        return payout_amount(stake, cfg.matched_20)
    if p1.suit == p2.suit:
        return payout_amount(stake, cfg.suited_20)
    return payout_amount(stake, cfg.any_20)


# ---- Royal Match -------------------------------------------------------

def evaluate_royal_match(p1: Card, p2: Card, cfg: RoyalMatch, stake: int) -> int:
    if not cfg.enabled or stake <= 0:
        return 0
    if p1.suit != p2.suit:
        return _loss(stake)
    pair = {p1.rank, p2.rank}
    if pair == {"K", "Q"}:
        return payout_amount(stake, cfg.royal_match)
    return payout_amount(stake, cfg.suited)


# ---- Match the Dealer --------------------------------------------------

def evaluate_match_the_dealer(
    p1: Card, p2: Card, dealer_up: Card, cfg: MatchTheDealer, stake: int
) -> int:
    if not cfg.enabled or stake <= 0:
        return 0
    payout = 0
    for card in (p1, p2):
        if card.rank == dealer_up.rank:
            if card.suit == dealer_up.suit:
                payout += payout_amount(stake, cfg.suited_match)
            else:
                payout += payout_amount(stake, cfg.unsuited_match)
    return payout if payout > 0 else _loss(stake)


# ---- Over/Under 13 -----------------------------------------------------

def evaluate_over_under_13(
    p1: Card,
    p2: Card,
    cfg: OverUnder13,
    stake: int,
    pick: Literal["over", "under"],
) -> int:
    if not cfg.enabled or stake <= 0:
        return 0
    # Aces count as 1 for this side bet.
    val = lambda c: 1 if c.rank == "A" else c.value
    total = val(p1) + val(p2)
    if total == 13:
        return _loss(stake)
    won = (pick == "over" and total > 13) or (pick == "under" and total < 13)
    if won:
        return payout_amount(stake, cfg.payout)
    return _loss(stake)


# ---- Bust It -----------------------------------------------------------

def evaluate_bust_it(dealer_cards: list[Card], cfg: BustIt, stake: int) -> int:
    """Pays only if the dealer busts. dealer_cards must be the final dealer hand."""
    if not cfg.enabled or stake <= 0:
        return 0
    total, _ = hand_total(dealer_cards)
    if total <= 21:
        return _loss(stake)
    # Lookup table is indexed by (cards in dealer hand - 3); cap at last bucket.
    idx = min(len(dealer_cards) - 3, len(cfg.payouts) - 1)
    if idx < 0:
        return _loss(stake)
    return payout_amount(stake, cfg.payouts[idx])


# ---- Buster Blackjack --------------------------------------------------

def evaluate_buster_blackjack(
    dealer_cards: list[Card],
    cfg: BusterBlackjack,
    stake: int,
    player_has_blackjack: bool,
) -> int:
    if not cfg.enabled or stake <= 0:
        return 0
    total, _ = hand_total(dealer_cards)
    if total <= 21:
        return _loss(stake)
    idx = min(len(dealer_cards) - 3, len(cfg.payouts) - 1)
    if idx < 0:
        return _loss(stake)
    base = payout_amount(stake, cfg.payouts[idx])
    if player_has_blackjack and cfg.blackjack_multiplier > 1:
        base *= cfg.blackjack_multiplier
    return base


__all__ = [
    "evaluate_21_plus_3",
    "evaluate_perfect_pairs",
    "evaluate_lucky_ladies",
    "evaluate_royal_match",
    "evaluate_match_the_dealer",
    "evaluate_over_under_13",
    "evaluate_bust_it",
    "evaluate_buster_blackjack",
]
