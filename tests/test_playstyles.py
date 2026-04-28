"""Playstyle behavior tests. We assert the recognizable archetypal moves
each style is supposed to make, not random RNG specifics."""
import random

from app.ai.playstyles import (
    play_aggressive,
    play_book,
    play_counter,
    play_drunk,
    play_hunch,
    play_mimic_dealer,
    play_streaky,
    play_superstitious,
    play_tight,
)
from app.engine.cards import Card, Suit
from app.engine.hand import Hand
from app.engine.rules import Rules
from app.strategy import Capabilities


def C(rank: str, suit: str = "S") -> Card:
    return Card(rank, Suit(suit))


def H(*ranks: str) -> Hand:
    h = Hand()
    for r in ranks:
        h.add_card(C(r))
    return h


def caps(d=True, sp=True, sr=True) -> Capabilities:
    return Capabilities(can_double=d, can_split=sp, can_surrender=sr)


def rng() -> random.Random:
    return random.Random(0)


# ---- book + counter ----------------------------------------------------

def test_book_matches_basic_strategy():
    rules = Rules(dealer_hits_soft_17=True)
    assert play_book(H("T", "6"), C("T"), rules, caps(), None, rng()) == "surrender"


def test_counter_uses_count():
    rules = Rules(dealer_hits_soft_17=True)
    # 16 vs T at TC=0 -> stand (deviation), without surrender capability.
    assert play_counter(H("T", "6"), C("T"), rules, caps(sr=False), 0.0, rng()) == "stand"


# ---- tight -------------------------------------------------------------

def test_tight_never_doubles():
    rules = Rules()
    # 11 vs 6 — book says double; tight hits.
    assert play_tight(H("5", "6"), C("6"), rules, caps(), None, rng()) == "hit"


def test_tight_only_splits_aces_and_eights():
    rules = Rules()
    assert play_tight(H("A", "A"), C("6"), rules, caps(), None, rng()) == "split"
    assert play_tight(H("8", "8"), C("6"), rules, caps(), None, rng()) == "split"
    # Other pairs: tight stands or hits per total — never split.
    assert play_tight(H("9", "9"), C("6"), rules, caps(), None, rng()) == "stand"
    assert play_tight(H("3", "3"), C("4"), rules, caps(), None, rng()) == "hit"


def test_tight_stands_hard_12_plus():
    rules = Rules()
    assert play_tight(H("T", "2"), C("T"), rules, caps(), None, rng()) == "stand"


# ---- aggressive --------------------------------------------------------

def test_aggressive_doubles_9_to_11():
    rules = Rules()
    # Non-pair 9 and 11 totals double.
    assert play_aggressive(H("4", "5"), C("T"), rules, caps(), None, rng()) == "double"
    assert play_aggressive(H("6", "5"), C("T"), rules, caps(), None, rng()) == "double"
    # 5,5 is a pair — aggressive splits all pairs first, so this is "split".
    assert play_aggressive(H("5", "5"), C("T"), rules, caps(), None, rng()) == "split"


def test_aggressive_splits_all_pairs():
    rules = Rules()
    for r in ("2", "3", "4", "6", "7", "9", "T"):
        assert (
            play_aggressive(H(r, r), C("6"), rules, caps(), None, rng())
            == "split"
        )


def test_aggressive_hits_soft_18():
    rules = Rules()
    # vs dealer 9: aggressive hits soft 18.
    assert play_aggressive(H("A", "7"), C("9"), rules, caps(), None, rng()) == "hit"


# ---- mimic dealer ------------------------------------------------------

def test_mimic_dealer_hits_below_17():
    rules = Rules(dealer_hits_soft_17=True)
    assert play_mimic_dealer(H("9", "5"), C("T"), rules, caps(), None, rng()) == "hit"


def test_mimic_dealer_h17_hits_soft_17():
    rules = Rules(dealer_hits_soft_17=True)
    assert play_mimic_dealer(H("A", "6"), C("T"), rules, caps(), None, rng()) == "hit"


def test_mimic_dealer_s17_stands_soft_17():
    rules = Rules(dealer_hits_soft_17=False)
    assert play_mimic_dealer(H("A", "6"), C("T"), rules, caps(), None, rng()) == "stand"


def test_mimic_dealer_never_doubles_or_splits():
    rules = Rules()
    # 11 vs 6 — book doubles. Mimic just hits.
    assert play_mimic_dealer(H("5", "6"), C("6"), rules, caps(), None, rng()) == "hit"
    assert play_mimic_dealer(H("8", "8"), C("6"), rules, caps(), None, rng()) == "hit"


# ---- hunch -------------------------------------------------------------

def test_hunch_sometimes_stands_on_stiff_vs_strong_dealer():
    rules = Rules()
    # Use a seeded RNG; 100 hunch decisions should have at least one
    # 'stand' on 14 vs T even though book says hit (no surrender cap).
    seen_stand = False
    seen_hit = False
    r = random.Random(7)
    for _ in range(100):
        a = play_hunch(H("T", "4"), C("T"), rules, caps(sr=False), None, r)
        if a == "stand":
            seen_stand = True
        elif a == "hit":
            seen_hit = True
    assert seen_stand and seen_hit


# ---- drunk -------------------------------------------------------------

def test_drunk_with_zero_mistake_rate_plays_book():
    rules = Rules()
    for _ in range(20):
        action = play_drunk(
            H("T", "6"), C("9"), rules, caps(), None, random.Random(1), 0.0
        )
        # 16 vs 9: book says surrender if available; it is here.
        assert action == "surrender"


def test_drunk_with_full_mistake_rate_diverges():
    rules = Rules()
    seen_actions = set()
    r = random.Random(2)
    for _ in range(50):
        seen_actions.add(
            play_drunk(H("T", "6"), C("9"), rules, caps(), None, r, 1.0)
        )
    # With 100% mistake rate, the action chosen should not always be the book play.
    assert len(seen_actions) >= 2


# ---- superstitious -----------------------------------------------------

def test_superstitious_never_hits_16():
    rules = Rules()
    # 16 vs 7 — book hits. Superstitious stands.
    assert (
        play_superstitious(H("T", "6"), C("7"), rules, caps(), None, rng())
        == "stand"
    )


def test_superstitious_splits_tens_vs_5_or_6():
    rules = Rules()
    assert (
        play_superstitious(H("T", "T"), C("5"), rules, caps(), None, rng())
        == "split"
    )
    assert (
        play_superstitious(H("T", "T"), C("6"), rules, caps(), None, rng())
        == "split"
    )
    # vs other up cards, holds the 20.
    assert (
        play_superstitious(H("T", "T"), C("8"), rules, caps(), None, rng())
        == "stand"
    )


def test_superstitious_refuses_surrender():
    rules = Rules()
    # 16 vs T — book surrenders. Superstitious does not.
    a = play_superstitious(H("T", "6"), C("T"), rules, caps(), None, rng())
    assert a != "surrender"


# ---- streaky -----------------------------------------------------------

def test_streaky_action_matches_book():
    rules = Rules()
    # Streaky's distinction is in bet sizing, not action selection.
    assert play_streaky(H("T", "6"), C("7"), rules, caps(sr=False), None, rng()) == "hit"
