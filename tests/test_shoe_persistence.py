"""Regression tests for the cross-shuffle shoe-replay bug.

A user reported that hands appeared to repeat after the shoe was
reshuffled mid-session. The cause: shoe state was persisted as
(seed, cards_dealt) only — no shuffle counter — so any rebuild after
the first reshuffle rewound the shoe to the *initial* permutation
instead of the current one.

These tests prove that:
  1. The shoe model exposes `shuffles` so a session can record it.
  2. shoe_from_session lands on the same permutation the original was on,
     even after one or more reshuffles.
  3. Successive shuffles produce *different* permutations (not just
     re-running shuffle on the same RNG state).
  4. The cut-card position varies between shoes (jitter is on by default).
"""
from __future__ import annotations

import json

from app import create_app
from app.config import Config
from app.engine.rules import ShuffleMode
from app.engine.shoe import Shoe
from app.services.games import StartRoundRequest, start_round
from app.services.sessions import (
    create_from_template,
    shoe_from_session,
)


class _TC(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test"


# ---- shoe primitive --------------------------------------------------

def test_shoe_records_shuffle_count():
    shoe = Shoe(decks=6, seed=42)
    assert shoe.shuffles == 1
    shoe.shuffle()
    assert shoe.shuffles == 2


def test_successive_shuffles_produce_different_permutations():
    shoe = Shoe(decks=6, seed=42)
    first = list(shoe._cards)
    shoe.shuffle()
    second = list(shoe._cards)
    assert first != second, "two consecutive shuffles produced identical permutations"


def test_cut_card_jitter_varies_position():
    """With jitter on, repeated shuffles land on different cut-card
    positions. Sample 12 shuffles; we should see at least 4 distinct
    cut indices."""
    shoe = Shoe(decks=6, seed=42)
    cuts = {shoe._cut_card_index}
    for _ in range(12):
        shoe.shuffle()
        cuts.add(shoe._cut_card_index)
    assert len(cuts) >= 4, f"cut card index didn't vary: {cuts}"


def test_cards_to_cut_decrements_with_each_card():
    shoe = Shoe(decks=6, seed=42)
    initial = shoe.cards_to_cut
    shoe.next_card()
    assert shoe.cards_to_cut == initial - 1


# ---- session-level rebuild after reshuffle ---------------------------

def test_shoe_from_session_lands_on_current_permutation_after_reshuffle():
    """The headline regression: shoe_from_session must reproduce the
    SAME cards a live shoe is dealing — even after the shoe has been
    re-shuffled mid-session. Compares: (a) a shoe built from a session
    with shoe_shuffles=2 against (b) the same physical shoe we'd get
    by manually applying one extra shuffle.
    """
    app = create_app(_TC())
    with app.app_context():
        sess = create_from_template(
            template_id=None,
            starting_bankroll=1000,
            player_seat=1,
            rules_overrides={
                "decks": 1, "penetration": 0.5,
                "seats": 1, "min_bet": 5, "max_bet": 100, "bet_increment": 5,
            },
            seed=12345,
        )
        # Pretend the session has crossed exactly one reshuffle and is
        # 10 cards into the second permutation.
        sess.shoe_shuffles = 2
        sess.cards_dealt = 10

        rebuilt = shoe_from_session(sess)
        rebuilt_next = [rebuilt.next_card() for _ in range(5)]

        # Manual reference shoe: same seed, manually shuffle once more,
        # burn 10 cards. Should match the rebuilt shoe.
        ref = Shoe(decks=1, mode=ShuffleMode.CASINO, penetration=0.5, seed=12345)
        ref.shuffle()  # advance to the second permutation
        for _ in range(10):
            ref.next_card()
        ref_next = [ref.next_card() for _ in range(5)]

        assert rebuilt_next == ref_next, (
            "shoe_from_session didn't replay the second permutation; "
            "bug regression — players will see repeated hands after reshuffle"
        )

        # Also verify the BUGGY behavior would have looked different:
        # a naive rebuild without the shuffles counter would burn into
        # the first permutation. Confirm those cards differ.
        naive = Shoe(decks=1, mode=ShuffleMode.CASINO, penetration=0.5, seed=12345)
        for _ in range(10):
            naive.next_card()
        naive_next = [naive.next_card() for _ in range(5)]
        assert naive_next != rebuilt_next, (
            "first/second permutations happen to match — pick a different seed"
        )


def test_reset_shoe_clears_shuffle_counter():
    """A fresh reset_shoe goes back to shuffles=1 with a new seed —
    not the same permutation the previous shoe was on."""
    from app.services.sessions import reset_shoe
    app = create_app(_TC())
    with app.app_context():
        sess = create_from_template(
            template_id=None,
            starting_bankroll=500,
            player_seat=1,
            rules_overrides={"seats": 1, "decks": 1, "penetration": 0.4},
            seed=7777,
        )
        sess.shoe_shuffles = 5
        sess.cards_dealt = 30
        reset_shoe(sess)
        assert sess.shoe_shuffles == 1
        assert sess.cards_dealt == 0
