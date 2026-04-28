from collections import Counter

from app.engine.cards import RANKS
from app.engine.rules import ShuffleMode
from app.engine.shoe import Shoe


def test_fresh_shoe_has_correct_card_count():
    for n in (1, 2, 4, 6, 8):
        shoe = Shoe(decks=n, seed=1)
        assert shoe.cards_remaining == n * 52


def test_seeded_shoe_is_deterministic():
    a = Shoe(decks=6, seed=12345)
    b = Shoe(decks=6, seed=12345)
    assert a.deal(20) == b.deal(20)


def test_different_seeds_produce_different_orders():
    a = Shoe(decks=6, seed=1)
    b = Shoe(decks=6, seed=2)
    assert a.deal(20) != b.deal(20)


def test_rank_distribution_after_full_shoe():
    shoe = Shoe(decks=6, seed=99)
    # Drain it.
    counts = Counter(c.rank for c in shoe.deal(shoe.total_cards))
    for rank in RANKS:
        assert counts[rank] == 6 * 4  # 6 decks * 4 suits per rank


def test_cut_card_triggers_reshuffle_signal():
    shoe = Shoe(decks=6, seed=7, mode=ShuffleMode.CASINO, penetration=0.5)
    shoe.deal(int(6 * 52 * 0.5) - 1)
    assert not shoe.needs_reshuffle
    shoe.deal(2)
    assert shoe.needs_reshuffle


def test_csm_never_signals_reshuffle():
    shoe = Shoe(decks=6, seed=7, mode=ShuffleMode.CSM, penetration=0.5)
    shoe.deal(500)
    assert not shoe.needs_reshuffle


def test_hand_shuffle_still_yields_full_deck():
    shoe = Shoe(decks=2, seed=11, mode=ShuffleMode.HAND)
    counts = Counter(c.rank for c in shoe.deal(shoe.total_cards))
    for rank in RANKS:
        assert counts[rank] == 2 * 4
