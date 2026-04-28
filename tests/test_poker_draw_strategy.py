"""AI discard heuristic tests for draw poker."""
from app.poker.ai.draw_strategy import discard_indices
from app.poker.cards import parse_cards
from app.poker.variants import all_variants


def H(*tokens):
    return parse_cards(tokens)


def _five_card_draw():
    return next(v for v in all_variants() if v.name == "5-Card Draw")


def _two_seven():
    return next(v for v in all_variants() if v.name == "2-7 Triple Draw")


def _badugi():
    return next(v for v in all_variants() if v.name == "Badugi")


# ---- 5-Card Draw -------------------------------------------------------

def test_high_keeps_pair_discards_other_three():
    """Pair of aces + 3 unrelated cards -> discard the 3 unrelated."""
    hand = H("AS", "AH", "5C", "9D", "2H")
    assert sorted(discard_indices(hand, _five_card_draw())) == [2, 3, 4]


def test_high_keeps_trips():
    hand = H("AS", "AH", "AD", "9D", "2H")
    assert sorted(discard_indices(hand, _five_card_draw())) == [3, 4]


def test_high_keeps_4_card_flush_discards_offsuit():
    """4 hearts + 1 club -> discard the club."""
    hand = H("AH", "9H", "5H", "2H", "TC")
    discards = discard_indices(hand, _five_card_draw())
    assert discards == [4]


def test_high_open_ended_straight_keeps_4_consecutive():
    """5-6-7-8 + random K -> keep the straight draw, discard K."""
    hand = H("5C", "6D", "7H", "8S", "KC")
    discards = discard_indices(hand, _five_card_draw())
    assert discards == [4]


def test_high_garbage_keeps_top_card_only():
    """No pair, no flush draw, no straight draw -> keep ace, discard 4."""
    hand = H("AC", "9D", "5H", "3S", "2C")
    discards = discard_indices(hand, _five_card_draw())
    # The ace is at index 0, so we expect [1, 2, 3, 4].
    assert sorted(discards) == [1, 2, 3, 4]


# ---- 2-7 Triple Draw --------------------------------------------------

def test_d27_keeps_low_unpaired():
    """7-5-4-3-2 unsuited is the nuts; discard nothing."""
    hand = H("7C", "5H", "4D", "3S", "2C")
    assert discard_indices(hand, _two_seven()) == []


def test_d27_discards_aces():
    """Aces are HIGH in 2-7 — bot should discard them."""
    hand = H("AC", "5H", "4D", "3S", "2C")
    discards = discard_indices(hand, _two_seven())
    assert 0 in discards


def test_d27_discards_8_and_above():
    hand = H("KC", "JH", "8D", "3S", "2C")
    discards = discard_indices(hand, _two_seven())
    # KC, JH, 8D should all be discarded.
    assert sorted(discards)[:3] == [0, 1, 2]


def test_d27_discards_pair():
    """Pairs are bad in 2-7."""
    hand = H("3C", "3H", "5D", "6S", "7C")
    discards = discard_indices(hand, _two_seven())
    # One of the 3s should be in the discard list.
    assert 0 in discards or 1 in discards


# ---- Badugi -----------------------------------------------------------

def test_badugi_keeps_4_distinct_suits_and_ranks():
    """A-2-3-4 in 4 different suits is the nuts; stand pat."""
    hand = H("AS", "2H", "3D", "4C")
    assert discard_indices(hand, _badugi()) == []


def test_badugi_drops_duplicate_suit():
    """Two spades -> drop the higher one."""
    hand = H("AS", "5S", "3D", "4C")
    discards = discard_indices(hand, _badugi())
    # 5S (index 1) is the higher spade; should be discarded.
    assert 1 in discards


def test_badugi_drops_paired_rank():
    """Two 4s -> drop one."""
    hand = H("AS", "2H", "4D", "4C")
    discards = discard_indices(hand, _badugi())
    # One of the 4s gets dropped.
    assert 2 in discards or 3 in discards
