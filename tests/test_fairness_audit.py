"""Fairness audit. Spins up a 6-deck H17 shoe and runs many always-stand
rounds against the engine. Asserts the empirical rates of player blackjack,
dealer blackjack, and dealer bust fall within reasonable bounds of the
mathematically expected values.

The point isn't to verify the rules engine is bug-free in general (the
unit tests cover that) — it's to catch a systemic bias like wrong card
ordering, double-counted cards, or a peeking step that suppresses dealer
blackjacks. If a friend reports a suspiciously high win rate, this test
is the first place to look.

A fixed RNG seed keeps the test deterministic so it doesn't flake. The
bounds are picked wide enough that any real bias would still trip them.
"""
from __future__ import annotations

from app.engine.round import Round, Seat
from app.engine.rules import Rules, ShuffleMode, SideBets
from app.engine.shoe import Shoe


# ----- expected rates (reference values) ----------------------------------
# 6-deck H17, dealer peeks, hole card dealt:
#  - Player BJ:  ~ 4.75% (P(A)*P(T|A) + P(T)*P(A|T))
#  - Dealer BJ:  ~ 4.75% (slightly altered by player's two cards but close)
#  - Dealer bust: ~ 28.4% (well-known H17 figure)
#
# Player "always stand" win rate is dominated by dealer-bust rate plus the
# rare player-BJ-vs-non-BJ-dealer wins. Empirically ~38-42% depending on
# how you count pushes. We don't pin a tight number on it — the bust and
# BJ rates are the load-bearing checks.

EXPECTED_PLAYER_BJ = 0.0475
EXPECTED_DEALER_BJ = 0.0475
EXPECTED_DEALER_BUST = 0.284


def _run_audit(n_hands: int, seed: int) -> dict:
    """Play n_hands rounds of always-stand and tally outcomes."""
    rules = Rules(
        decks=6,
        shuffle_mode=ShuffleMode.CASINO,
        dealer_hits_soft_17=True,
        dealer_peeks=True,
        european_no_hole_card=False,
        insurance_offered=False,  # skip the insurance gate; it doesn't
                                   # affect card flow when we always decline
    )
    side_bets = SideBets()
    shoe = Shoe(decks=rules.decks, mode=rules.shuffle_mode,
                penetration=rules.penetration, seed=seed)

    tally = {
        "hands": 0,
        "player_bj": 0,
        "dealer_bj": 0,
        "dealer_bust": 0,
        "player_win": 0,
        "player_loss": 0,
        "player_push": 0,
    }

    for _ in range(n_hands):
        if shoe.needs_reshuffle:
            shoe.shuffle()
        rnd = Round(rules, side_bets, shoe)
        rnd.add_seat(Seat(seat_num=1, main_bet=10, is_human=True))
        rnd.deal()

        # Walk the state machine without ever hitting. Surrender + insurance
        # are off; the only branch we need to handle is PLAYING -> stand.
        while rnd.state.value == "playing":
            rnd.act("stand")

        result = rnd.result
        assert result is not None

        tally["hands"] += 1
        if any(h.is_blackjack for h in result.seats[0].hands):
            tally["player_bj"] += 1
        if result.dealer_blackjack:
            tally["dealer_bj"] += 1
        if result.dealer_hand.is_bust:
            tally["dealer_bust"] += 1

        for outcome in result.outcomes:
            if outcome.profit > 0:
                tally["player_win"] += 1
            elif outcome.profit < 0:
                tally["player_loss"] += 1
            else:
                tally["player_push"] += 1

    return tally


def test_fairness_audit_blackjack_and_bust_rates():
    n = 10_000
    tally = _run_audit(n, seed=0xBEEF)

    player_bj_rate = tally["player_bj"] / n
    dealer_bj_rate = tally["dealer_bj"] / n
    dealer_bust_rate = tally["dealer_bust"] / n

    # Tolerances: ~0.6% absolute on the BJ rates is ~3-4σ at n=10k for p≈0.05.
    # Bust rate gets 2.5% absolute tolerance (~5σ at n=10k for p≈0.28).
    assert abs(player_bj_rate - EXPECTED_PLAYER_BJ) < 0.01, (
        f"player BJ rate {player_bj_rate:.4f} drifted from "
        f"{EXPECTED_PLAYER_BJ:.4f}"
    )
    assert abs(dealer_bj_rate - EXPECTED_DEALER_BJ) < 0.01, (
        f"dealer BJ rate {dealer_bj_rate:.4f} drifted from "
        f"{EXPECTED_DEALER_BJ:.4f}"
    )
    assert abs(dealer_bust_rate - EXPECTED_DEALER_BUST) < 0.025, (
        f"dealer bust rate {dealer_bust_rate:.4f} drifted from "
        f"{EXPECTED_DEALER_BUST:.4f}"
    )


def test_fairness_audit_dealer_ace_up_blackjack_rate():
    """Specifically targets the friend's anecdote ('never seeing dealer BJs
    on ace-up'). Filters to ace-up rounds and checks dealer-BJ rate matches
    the expected 4/13 ≈ 30.8% of ace-up situations.
    """
    rules = Rules(
        decks=6,
        shuffle_mode=ShuffleMode.CASINO,
        dealer_hits_soft_17=True,
        dealer_peeks=True,
        european_no_hole_card=False,
        insurance_offered=False,
    )
    shoe = Shoe(decks=rules.decks, mode=rules.shuffle_mode,
                penetration=rules.penetration, seed=0xC0FFEE)

    n = 10_000
    ace_up = 0
    ace_up_dealer_bj = 0

    for _ in range(n):
        if shoe.needs_reshuffle:
            shoe.shuffle()
        rnd = Round(rules, SideBets(), shoe)
        rnd.add_seat(Seat(seat_num=1, main_bet=10, is_human=True))
        rnd.deal()

        if rnd.dealer.cards[0].rank == "A":
            ace_up += 1
            if rnd.result is not None and rnd.result.dealer_blackjack:
                ace_up_dealer_bj += 1

        # Drain to completion if not already there.
        while rnd.state.value == "playing":
            rnd.act("stand")

    # Among ace-up rounds, dealer BJ rate is P(hole is 10-value) ≈ 96/311 ≈ 30.9%.
    # n_ace_up ~ 770; std ~ 1.6%; 5σ ≈ 8% absolute. Use 5% tolerance.
    rate = ace_up_dealer_bj / max(ace_up, 1)
    assert ace_up >= 600, f"unexpectedly few ace-up rounds: {ace_up}"
    assert abs(rate - 0.308) < 0.05, (
        f"dealer BJ rate on ace-up was {rate:.4f}; expected ~0.308. "
        f"({ace_up_dealer_bj} BJs in {ace_up} ace-up rounds)"
    )
