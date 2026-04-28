"""Canonical built-in templates. The settings_template table seeds these on
first boot; they're flagged read-only so users can't edit them in place
(they can clone-and-edit).
"""
from __future__ import annotations

from .rules import (
    DoubleRule,
    Rules,
    ShuffleMode,
    SideBets,
    SurrenderRule,
)


def _enable_common_side_bets() -> SideBets:
    """Default side-bet config with the common ones turned on so the
    rule-template UI shows realistic options. Users still toggle these per game.
    """
    sb = SideBets()
    sb.twenty_one_plus_three.enabled = True
    sb.perfect_pairs.enabled = True
    sb.lucky_ladies.enabled = True
    return sb


def vegas_strip() -> tuple[Rules, SideBets, str, str]:
    return (
        Rules(
            decks=6,
            shuffle_mode=ShuffleMode.CASINO,
            penetration=0.75,
            seats=5,
            player_seat=3,
            dealer_hits_soft_17=True,
            dealer_peeks=True,
            european_no_hole_card=False,
            blackjack_payout=(6, 5),
            insurance_payout=(2, 1),
            double_rule=DoubleRule.ANY_TWO,
            double_after_split=True,
            max_splits=3,
            resplit_aces=False,
            hit_split_aces=False,
            surrender=SurrenderRule.LATE,
            insurance_offered=True,
            starting_bankroll=500,
            min_bet=10,
            max_bet=500,
            bet_increment=5,
        ),
        _enable_common_side_bets(),
        "Vegas Strip 6:5 H17",
        "Six-deck Strip rules: 6:5 blackjack, dealer hits soft 17, late surrender, double after split.",
    )


def vegas_downtown() -> tuple[Rules, SideBets, str, str]:
    return (
        Rules(
            decks=2,
            shuffle_mode=ShuffleMode.CASINO,
            penetration=0.7,
            seats=5,
            player_seat=3,
            dealer_hits_soft_17=True,
            dealer_peeks=True,
            blackjack_payout=(3, 2),
            double_rule=DoubleRule.ANY_TWO,
            double_after_split=True,
            max_splits=3,
            resplit_aces=False,
            hit_split_aces=False,
            surrender=SurrenderRule.NONE,
            insurance_offered=True,
            starting_bankroll=500,
            min_bet=5,
            max_bet=500,
            bet_increment=5,
        ),
        SideBets(),
        "Vegas Downtown 3:2 H17",
        "Double-deck downtown rules: 3:2 blackjack, dealer hits soft 17, no surrender.",
    )


def single_deck() -> tuple[Rules, SideBets, str, str]:
    return (
        Rules(
            decks=1,
            shuffle_mode=ShuffleMode.CASINO,
            penetration=0.5,
            seats=3,
            player_seat=2,
            dealer_hits_soft_17=True,
            dealer_peeks=True,
            blackjack_payout=(3, 2),
            double_rule=DoubleRule.TEN_ELEVEN,
            double_after_split=False,
            max_splits=3,
            resplit_aces=False,
            hit_split_aces=False,
            surrender=SurrenderRule.NONE,
            insurance_offered=True,
            starting_bankroll=300,
            min_bet=10,
            max_bet=300,
            bet_increment=5,
        ),
        SideBets(),
        "Single-Deck 3:2 H17",
        "One deck, dealer hits soft 17, double on 10-11 only, 3:2 blackjack. Modern single-deck reality.",
    )


def european_no_hole() -> tuple[Rules, SideBets, str, str]:
    return (
        Rules(
            decks=6,
            shuffle_mode=ShuffleMode.CASINO,
            penetration=0.75,
            seats=5,
            player_seat=3,
            dealer_hits_soft_17=False,
            dealer_peeks=False,
            european_no_hole_card=True,
            blackjack_payout=(3, 2),
            double_rule=DoubleRule.NINE_TEN_ELEVEN,
            double_after_split=False,
            max_splits=3,
            resplit_aces=False,
            hit_split_aces=False,
            surrender=SurrenderRule.LATE,
            insurance_offered=True,
            starting_bankroll=500,
            min_bet=10,
            max_bet=500,
            bet_increment=5,
        ),
        _enable_common_side_bets(),
        "European No-Hole 3:2 S17",
        "European rules: dealer doesn't take a hole card until players act, S17, 3:2, double 9-10-11.",
    )


def all_presets() -> list[tuple[Rules, SideBets, str, str]]:
    return [
        vegas_strip(),
        vegas_downtown(),
        single_deck(),
        european_no_hole(),
    ]
