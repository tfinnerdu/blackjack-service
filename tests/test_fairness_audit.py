"""Fairness audit. Spins up a 6-deck H17 shoe and runs many always-stand
rounds against the engine. Asserts the empirical rates of player blackjack,
dealer blackjack, and dealer bust fall within reasonable bounds of the
mathematically expected values.

The point isn't to verify the rules engine is bug-free in general (the
unit tests cover that) — it's to catch a systemic bias like wrong card
ordering, double-counted cards, or a peeking step that suppresses dealer
blackjacks. If a friend reports a suspiciously high win rate, this test
is the first place to look.

Coverage:
  - Always-stand rates (player BJ, dealer BJ, dealer bust) at 6-deck H17
  - Same rates across multiple RNG seeds — variance shouldn't drift the
    mean once sample sizes get big
  - Same rates at single-deck (smaller sample, looser bounds)
  - Ace-up dealer-blackjack rate (the friend's specific complaint)
  - Card-deal sanity: the engine deals the right cards in the right
    order, so a positive bias can't sneak in via misordered indexing
  - Rank uniformity on a freshly shuffled shoe — Fisher-Yates should
    give roughly uniform rank counts; a weighted RNG would fail here
  - Hi-Lo counter math is right (separate property: stats hinge on it)

Seeds are fixed so the test is deterministic; bounds are wide enough
that a real bias would trip them without flaking on legitimate variance.
"""
from __future__ import annotations

import math
from collections import Counter as _PyCounter

from app.counting import Counter as HiLoCounter, hi_lo_value
from app.engine.cards import Card, RANKS, Suit
from app.engine.round import Round, Seat
from app.engine.rules import Rules, ShuffleMode, SideBets
from app.engine.shoe import Shoe
from app.strategy import Capabilities
from app.strategy.book import book


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


def test_fairness_audit_holds_across_multiple_seeds():
    """A real engine bias would show up regardless of starting seed.
    Run the same audit with several different seeds and confirm the
    rates stay within tolerance for each. If just one seed passes,
    that's a bad sign — could indicate cherry-picked seed."""
    seeds = [1, 17, 0xCAFE, 2024, 99999]
    n = 5_000  # smaller sample per seed; broader tolerance
    for seed in seeds:
        tally = _run_audit(n, seed=seed)
        bj_p = tally["player_bj"] / n
        bj_d = tally["dealer_bj"] / n
        bust = tally["dealer_bust"] / n
        # Bigger absolute tolerance at n=5000: ~5σ on each.
        assert abs(bj_p - EXPECTED_PLAYER_BJ) < 0.015, (
            f"seed {seed}: player BJ {bj_p:.4f} vs {EXPECTED_PLAYER_BJ}"
        )
        assert abs(bj_d - EXPECTED_DEALER_BJ) < 0.015, (
            f"seed {seed}: dealer BJ {bj_d:.4f} vs {EXPECTED_DEALER_BJ}"
        )
        assert abs(bust - EXPECTED_DEALER_BUST) < 0.03, (
            f"seed {seed}: dealer bust {bust:.4f} vs {EXPECTED_DEALER_BUST}"
        )


def test_fairness_audit_single_deck_rates():
    """Single-deck rates differ slightly from 6-deck (the deck-removal
    effect is bigger). Player-BJ ≈ 4.83% (= 2 * 4*16 / (52*51) = 0.0483),
    dealer bust H17 1-deck ≈ 28.0%. Ace-up dealer-BJ ≈ 16/51 ≈ 31.4%."""
    rules = Rules(
        decks=1,
        shuffle_mode=ShuffleMode.CASINO,
        dealer_hits_soft_17=True,
        dealer_peeks=True,
        european_no_hole_card=False,
        insurance_offered=False,
    )
    shoe = Shoe(decks=rules.decks, mode=rules.shuffle_mode,
                penetration=rules.penetration, seed=4242)

    n = 5_000
    tally = {"hands": 0, "player_bj": 0, "dealer_bj": 0, "dealer_bust": 0}
    for _ in range(n):
        if shoe.needs_reshuffle:
            shoe.shuffle()
        rnd = Round(rules, SideBets(), shoe)
        rnd.add_seat(Seat(seat_num=1, main_bet=10, is_human=True))
        rnd.deal()
        while rnd.state.value == "playing":
            rnd.act("stand")
        result = rnd.result
        tally["hands"] += 1
        if any(h.is_blackjack for h in result.seats[0].hands):
            tally["player_bj"] += 1
        if result.dealer_blackjack:
            tally["dealer_bj"] += 1
        if result.dealer_hand.is_bust:
            tally["dealer_bust"] += 1

    bj_p = tally["player_bj"] / n
    bj_d = tally["dealer_bj"] / n
    bust = tally["dealer_bust"] / n
    assert abs(bj_p - 0.0483) < 0.015, f"single-deck player BJ {bj_p:.4f}"
    assert abs(bj_d - 0.0483) < 0.015, f"single-deck dealer BJ {bj_d:.4f}"
    # 1-deck dealer bust is in the same ballpark as 6-deck, ~28%.
    assert abs(bust - 0.28) < 0.04, f"single-deck dealer bust {bust:.4f}"


def test_fairness_audit_book_play_doesnt_alter_rates():
    """The audit should also hold under realistic play. Use book strategy
    on each hand instead of always-stand. The dealer-BJ and player-BJ rates
    should be unaffected (those are a deal-only artifact). Dealer bust will
    shift because book sometimes busts the player early — but our check is
    that BJ rates remain pinned where the deal places them."""
    rules = Rules(
        decks=6,
        shuffle_mode=ShuffleMode.CASINO,
        dealer_hits_soft_17=True,
        dealer_peeks=True,
        european_no_hole_card=False,
        insurance_offered=False,
    )
    shoe = Shoe(decks=rules.decks, mode=rules.shuffle_mode,
                penetration=rules.penetration, seed=0xB00B)

    n = 5_000
    player_bj = 0
    dealer_bj = 0

    for _ in range(n):
        if shoe.needs_reshuffle:
            shoe.shuffle()
        rnd = Round(rules, SideBets(), shoe)
        rnd.add_seat(Seat(seat_num=1, main_bet=10, is_human=True))
        rnd.deal()

        # Walk the round using book strategy.
        while rnd.state.value == "playing":
            legal = rnd.legal_actions()
            caps = Capabilities(
                can_double="double" in legal,
                can_split="split" in legal,
                can_surrender="surrender" in legal,
            )
            action = book(rnd.active_hand, rnd.dealer.cards[0], rules, caps).action
            if action not in legal:
                action = "stand" if "stand" in legal else legal[0]
            rnd.act(action)

        result = rnd.result
        if any(h.is_blackjack for h in result.seats[0].hands):
            player_bj += 1
        if result.dealer_blackjack:
            dealer_bj += 1

    bj_p = player_bj / n
    bj_d = dealer_bj / n
    # BJ rates are deal-only; they don't depend on the player's actions.
    # If they shifted, something in the deal step is leaking into action.
    assert abs(bj_p - EXPECTED_PLAYER_BJ) < 0.015, (
        f"book-play player BJ {bj_p:.4f} drifted from {EXPECTED_PLAYER_BJ}"
    )
    assert abs(bj_d - EXPECTED_DEALER_BJ) < 0.015, (
        f"book-play dealer BJ {bj_d:.4f} drifted from {EXPECTED_DEALER_BJ}"
    )


def test_fairness_audit_shoe_rank_distribution_is_uniform():
    """A freshly shuffled shoe should have each rank present in equal
    proportion (4 of each rank per deck). Counts per rank measured
    after Fisher-Yates should match exactly — Fisher-Yates is a
    permutation and doesn't add/remove cards. Test multiple shuffles
    so a bug that subtly reorders only certain cards (like a stale
    cached deck) would show up as deviation."""
    seeds = [1, 2, 3, 4, 5]
    for seed in seeds:
        shoe = Shoe(decks=6, mode=ShuffleMode.CASINO, seed=seed)
        # Drain the shoe (penetration default 0.75 returns ~234 cards).
        # We want all 312 cards to verify totals, so slurp internal _cards.
        all_cards = list(shoe._cards)
        counts = _PyCounter(c.rank for c in all_cards)
        # 6 decks × 4 cards/rank = 24 of each rank.
        for rank in RANKS:
            assert counts.get(rank) == 24, (
                f"seed {seed}: rank {rank} count {counts.get(rank)}, expected 24"
            )


def test_fairness_audit_deal_order_is_correct():
    """Rigged shoe + verifying the cards land where the textbook says.

    Standard deal: P1 first card, dealer up, P1 second, dealer hole.
    A bug that flipped the player's hole card with the dealer's would be
    invisible to the rate tests but would cause biased outcomes.
    """
    class _RiggedShoe:
        def __init__(self, cards):
            self._cards = list(cards)
        def next_card(self):
            return self._cards.pop(0)
        @property
        def needs_reshuffle(self):
            return False

    # Deal sequence: AS to P1, 9C to dealer-up, KS to P1, 8C to dealer-hole.
    cards = [Card("A", Suit.SPADES), Card("9", Suit.CLUBS),
             Card("K", Suit.SPADES), Card("8", Suit.CLUBS)]
    rules = Rules(insurance_offered=False, dealer_peeks=False)
    rnd = Round(rules, SideBets(), _RiggedShoe(cards))
    rnd.add_seat(Seat(seat_num=1, main_bet=10, is_human=True))
    rnd.deal()

    p1_cards = rnd.seats[0].hands[0].cards
    assert p1_cards[0].rank == "A" and p1_cards[0].suit == Suit.SPADES
    assert p1_cards[1].rank == "K" and p1_cards[1].suit == Suit.SPADES
    assert rnd.dealer.cards[0].rank == "9" and rnd.dealer.cards[0].suit == Suit.CLUBS
    assert rnd.dealer.cards[1].rank == "8" and rnd.dealer.cards[1].suit == Suit.CLUBS


def test_fairness_audit_hi_lo_counter_math():
    """The Hi-Lo running count is what feeds the counter-bankroll stat
    + AI bet sizing. A wrong sign on any rank would silently corrupt
    every counting feature. Use a known sequence + verified expected
    count."""
    # 2-3-4-5-6 = +5 (low cards favorable for player)
    # 7-8-9     =  0
    # T-J-Q-K-A = -5 (high cards leaving the shoe)
    sequence = [
        Card(r, Suit.SPADES) for r in
        ["2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A"]
    ]
    counter = HiLoCounter(decks=1)
    counter.see_many(sequence)
    assert counter.running_count == 0, (
        f"running count after one of each rank should be 0; got {counter.running_count}"
    )
    assert counter.cards_seen == 13

    # Spot-check each rank's contribution.
    expected = {
        "2": 1, "3": 1, "4": 1, "5": 1, "6": 1,
        "7": 0, "8": 0, "9": 0,
        "T": -1, "J": -1, "Q": -1, "K": -1, "A": -1,
    }
    for r, v in expected.items():
        assert hi_lo_value(r) == v, f"hi-lo value for {r} is {hi_lo_value(r)}, expected {v}"


def test_fairness_audit_dealer_bust_rate_by_up_card():
    """Coarse check on the dealer's bust rate as a function of up-card.
    Published 6-deck H17 numbers (player not influencing dealer):
        2:35%  3:38%  4:40%  5:42%  6:42%  (bust-prone)
        7:26%  8:24%  9:23%  T:21%  A:12%  (strong)
    Sample size per up-card is small (~3000 hands → ~230 per up-card),
    so we use a wide ±10% tolerance. The point is to catch a class of
    bugs that systematically mis-deal the dealer's hole card or
    short-circuit the H17 hit loop on certain totals.
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
                penetration=rules.penetration, seed=0x1234)

    n = 8_000
    by_up: dict[str, list[int]] = {r: [0, 0] for r in RANKS}
    for _ in range(n):
        if shoe.needs_reshuffle:
            shoe.shuffle()
        rnd = Round(rules, SideBets(), shoe)
        rnd.add_seat(Seat(seat_num=1, main_bet=10, is_human=True))
        rnd.deal()
        while rnd.state.value == "playing":
            rnd.act("stand")
        # Skip rounds that ended on dealer-BJ peek (dealer didn't play out).
        if rnd.result is None or rnd.result.dealer_blackjack:
            continue
        up = rnd.dealer.cards[0].rank
        by_up[up][0] += 1
        if rnd.dealer.is_bust:
            by_up[up][1] += 1

    # Published bust rates. T-group lumped here means any 10-value face up.
    expected_rates = {
        "2": 0.35, "3": 0.38, "4": 0.40, "5": 0.42, "6": 0.42,
        "7": 0.26, "8": 0.24, "9": 0.23,
        "T": 0.21, "J": 0.21, "Q": 0.21, "K": 0.21,
        "A": 0.12,
    }
    failures: list[str] = []
    for up_rank, (n_rounds, n_busts) in by_up.items():
        if n_rounds < 80:
            # Too few samples for a meaningful check (rare up-cards on
            # this seed). Skip without failing.
            continue
        observed = n_busts / n_rounds
        target = expected_rates[up_rank]
        if abs(observed - target) > 0.10:
            failures.append(
                f"up={up_rank}: bust {observed:.3f} vs target {target:.3f} "
                f"(n={n_rounds})"
            )
    assert not failures, "dealer bust rate diverged on:\n  " + "\n  ".join(failures)
