"""Wild substitution tests covering the three modes."""
import pytest

from app.poker.cards import parse_cards
from app.poker.evaluator import HandClass, evaluate_with_wilds
from app.poker.evaluator.wilds import WildMode


def H(*tokens: str):
    return parse_cards(tokens)


# ---- FULLY_WILD --------------------------------------------------------

def test_fully_wild_joker_makes_quads():
    rank = evaluate_with_wilds(
        H("AS", "AH", "AD", "5C", "JK"), mode=WildMode.FULLY_WILD
    )
    assert rank.cls == HandClass.FOUR_OF_A_KIND
    assert rank.tiebreakers[0] == 14  # quad aces


def test_fully_wild_two_jokers_make_five_of_a_kind():
    rank = evaluate_with_wilds(
        H("AS", "AH", "AD", "JK", "jk"), mode=WildMode.FULLY_WILD
    )
    assert rank.cls == HandClass.FIVE_OF_A_KIND


def test_fully_wild_completes_royal_flush():
    rank = evaluate_with_wilds(
        H("TS", "JS", "QS", "KS", "JK"), mode=WildMode.FULLY_WILD
    )
    assert rank.cls == HandClass.STRAIGHT_FLUSH
    assert rank.tiebreakers == (14,)


def test_fully_wild_with_no_jokers_short_circuits():
    """No joker -> classify_high directly."""
    rank = evaluate_with_wilds(
        H("AS", "AH", "AD", "5C", "5H"), mode=WildMode.FULLY_WILD
    )
    assert rank.cls == HandClass.FULL_HOUSE


# ---- STRAIGHT_FLUSH_ONLY (the user's home rule) ------------------------

def test_sf_only_joker_completes_flush():
    rank = evaluate_with_wilds(
        H("2S", "5S", "9S", "KS", "JK"), mode=WildMode.STRAIGHT_FLUSH_ONLY
    )
    assert rank.cls == HandClass.FLUSH
    # Best filler is the ace of spades -> A-K-9-5-2 flush.
    assert rank.tiebreakers[0] == 14


def test_sf_only_joker_completes_straight():
    rank = evaluate_with_wilds(
        H("5H", "6S", "7D", "8C", "JK"), mode=WildMode.STRAIGHT_FLUSH_ONLY
    )
    assert rank.cls == HandClass.STRAIGHT
    assert rank.tiebreakers == (9,)


def test_sf_only_joker_completes_straight_flush_when_possible():
    rank = evaluate_with_wilds(
        H("5H", "6H", "7H", "8H", "JK"), mode=WildMode.STRAIGHT_FLUSH_ONLY
    )
    assert rank.cls == HandClass.STRAIGHT_FLUSH


def test_sf_only_joker_dead_when_no_sf_possible():
    """Three of a kind + odd cards + joker. Joker can't make a S/F here, so
    it stays dead and the hand is whatever the four real cards make."""
    rank = evaluate_with_wilds(
        H("AS", "AH", "AD", "9C", "JK"), mode=WildMode.STRAIGHT_FLUSH_ONLY
    )
    # Just three aces — joker doesn't pair, doesn't extend any flush.
    assert rank.cls == HandClass.THREE_OF_A_KIND
    assert rank.tiebreakers[0] == 14


def test_sf_only_two_jokers_complete_straight_flush():
    rank = evaluate_with_wilds(
        H("5H", "7H", "8H", "JK", "jk"), mode=WildMode.STRAIGHT_FLUSH_ONLY
    )
    assert rank.cls == HandClass.STRAIGHT_FLUSH


# ---- BUG ---------------------------------------------------------------

def test_bug_completes_straight_flush_when_possible():
    rank = evaluate_with_wilds(
        H("TS", "JS", "QS", "KS", "JK"), mode=WildMode.BUG
    )
    assert rank.cls == HandClass.STRAIGHT_FLUSH
    assert rank.tiebreakers == (14,)


def test_bug_plays_as_ace_when_no_sf():
    """Pair of kings + joker. Bug joker plays as an ace (not paired with
    anything in hand), so the hand is K-K + A high kicker."""
    rank = evaluate_with_wilds(
        H("KS", "KH", "5D", "9C", "JK"), mode=WildMode.BUG
    )
    assert rank.cls == HandClass.PAIR
    # Pair of kings, kickers A-9-5.
    assert rank.tiebreakers == (13, 14, 9, 5)


# ---- explicit wild_indices (deuces wild, etc.) -------------------------

def test_explicit_wild_indices_make_quad_aces_with_deuces_wild():
    """Two aces + two deuces (treated as wild) + a kicker -> quad aces."""
    cards = H("AS", "AH", "2D", "2C", "9H")
    # Mark the deuces as wild even though they're not jokers.
    rank = evaluate_with_wilds(
        cards, wild_indices=[2, 3], mode=WildMode.FULLY_WILD
    )
    assert rank.cls == HandClass.FOUR_OF_A_KIND
    assert rank.tiebreakers[0] == 14


def test_wrong_card_count_rejected():
    with pytest.raises(ValueError):
        evaluate_with_wilds(H("AS", "KH"), mode=WildMode.FULLY_WILD)


def test_joker_outside_wild_indices_rejected():
    """If you pass wild_indices that don't cover an actual joker, the
    evaluator should refuse rather than send the joker to classify_high."""
    cards = H("AS", "KH", "QC", "JD", "JK")
    with pytest.raises(ValueError):
        evaluate_with_wilds(cards, wild_indices=[0], mode=WildMode.FULLY_WILD)
