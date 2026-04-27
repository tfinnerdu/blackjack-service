"""Dealer play. The dealer is a pure function of the rules + the cards drawn."""
from __future__ import annotations

from .hand import Hand
from .rules import Rules
from .shoe import Shoe


def dealer_should_hit(hand: Hand, rules: Rules) -> bool:
    """Standard dealer logic.

    - Hits below 17 always.
    - On soft 17: hits if H17, stands if S17.
    - Stands on hard 17 and above.
    """
    total = hand.total
    if total < 17:
        return True
    if total == 17 and hand.is_soft and rules.dealer_hits_soft_17:
        return True
    return False


def play_dealer(hand: Hand, shoe: Shoe, rules: Rules) -> None:
    """Mutate the dealer's hand by drawing until standing or busting."""
    while dealer_should_hit(hand, rules):
        hand.add_card(shoe.next_card())
    hand.stood = not hand.is_bust
    hand.finished = True


def dealer_has_blackjack_potential(up_card_rank: str) -> bool:
    """Whether the up-card is one where the dealer would peek for blackjack."""
    return up_card_rank == "A" or up_card_rank in ("T", "J", "Q", "K")
