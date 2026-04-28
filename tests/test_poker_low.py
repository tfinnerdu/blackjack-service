"""Low-evaluator tests across all three low rules + qualifier behavior."""
from app.poker.cards import parse_cards
from app.poker.evaluator import LowRule, best_low, low_ranks_compare


def H(*tokens: str):
    return parse_cards(tokens)


# ---- Ace-to-five (no qualifier) ----------------------------------------

def test_a5_wheel_is_best():
    lr = best_low(H("AS", "2H", "3D", "4C", "5S"), LowRule.ACE_TO_FIVE)
    assert lr.qualifies
    assert lr.ranks == (5, 4, 3, 2, 1)
    assert "wheel" in lr.name


def test_a5_eight_seven_low():
    lr = best_low(H("AS", "3H", "5D", "7C", "8S"), LowRule.ACE_TO_FIVE)
    assert lr.qualifies
    assert lr.ranks == (8, 7, 5, 3, 1)


def test_a5_pairs_skipped_to_find_5_distinct():
    """A pair on the table is skipped — we just take the next-lowest card.
    With 6 cards including a pair, we still find a 5-distinct low."""
    lr = best_low(H("AS", "2H", "2D", "5C", "7S", "8C"), LowRule.ACE_TO_FIVE)
    assert lr.qualifies
    assert lr.ranks == (8, 7, 5, 2, 1)


def test_a5_fewer_than_5_distinct_does_not_qualify():
    lr = best_low(H("AS", "AH", "2D", "2C", "3S"), LowRule.ACE_TO_FIVE)
    assert not lr.qualifies


def test_a5_8_or_better_disqualifies_above_8():
    lr = best_low(
        H("AS", "3H", "5D", "7C", "9S"),
        LowRule.ACE_TO_FIVE,
        eight_or_better=True,
    )
    assert not lr.qualifies


def test_a5_8_or_better_qualifies_at_8():
    lr = best_low(
        H("AS", "3H", "5D", "7C", "8S"),
        LowRule.ACE_TO_FIVE,
        eight_or_better=True,
    )
    assert lr.qualifies


def test_a5_compare_lower_wins():
    a = best_low(H("AS", "2H", "3D", "4C", "5S"), LowRule.ACE_TO_FIVE)   # wheel
    b = best_low(H("AS", "2H", "3D", "4C", "6S"), LowRule.ACE_TO_FIVE)   # 6-low
    assert low_ranks_compare(a, b) == -1
    assert low_ranks_compare(b, a) == 1
    assert low_ranks_compare(a, a) == 0


# ---- Deuce-to-seven ----------------------------------------------------

def test_d27_seven_five_four_three_two_unsuited_is_best():
    """7-5-4-3-2 unsuited is the canonical best 2-7 low."""
    lr = best_low(
        H("2C", "3H", "4S", "5D", "7C"),
        LowRule.DEUCE_TO_SEVEN,
    )
    assert lr.qualifies
    # Class index 0 (high card), then descending values.
    assert lr.ranks == (0, 7, 5, 4, 3, 2)


def test_d27_straight_counts_against_you():
    """A real 2-3-4-5-6 straight is WORSE than a 7-high non-straight under 2-7."""
    straight = best_low(H("2C", "3H", "4S", "5D", "6C"), LowRule.DEUCE_TO_SEVEN)
    seven_high = best_low(H("2C", "3H", "4S", "5D", "7C"), LowRule.DEUCE_TO_SEVEN)
    assert low_ranks_compare(seven_high, straight) == -1


def test_d27_flush_counts_against_you():
    flush = best_low(H("2H", "3H", "4H", "5H", "7H"), LowRule.DEUCE_TO_SEVEN)
    unsuited = best_low(H("2C", "3H", "4S", "5D", "7C"), LowRule.DEUCE_TO_SEVEN)
    assert low_ranks_compare(unsuited, flush) == -1


def test_d27_ace_is_high_so_a_2_3_4_5_is_a_high_hand():
    """A-2-3-4-5: A counts high (14), so this is just a high-card-ace
    with low kickers. Beaten by 7-5-4-3-2."""
    a_high = best_low(H("AS", "2H", "3D", "4C", "5S"), LowRule.DEUCE_TO_SEVEN)
    seven_high = best_low(H("2C", "3H", "4S", "5D", "7C"), LowRule.DEUCE_TO_SEVEN)
    assert low_ranks_compare(seven_high, a_high) == -1


# ---- Badugi ------------------------------------------------------------

def test_badugi_best_4_card_a_2_3_4_four_suits():
    lr = best_low(H("AS", "2H", "3D", "4C"), LowRule.BADUGI)
    assert lr.qualifies
    # Best is A-2-3-4 across 4 distinct suits.
    # ranks tuple has size-prefix -4 + (4,3,2,1) descending = (-4, 4, 3, 2, 1)
    assert lr.ranks == (-4, 4, 3, 2, 1)


def test_badugi_pair_blocks_4th():
    """Two cards same rank — best badugi is 3 cards."""
    lr = best_low(H("AS", "AH", "3D", "4C"), LowRule.BADUGI)
    assert not lr.qualifies   # 3-card badugi only
    # Best 3-card uses A + 3 + 4 across 3 suits.
    assert lr.ranks[0] == -3   # 3-card


def test_badugi_same_suit_blocks_4th():
    """Two same-suit cards — only the lower counts."""
    lr = best_low(H("AS", "2S", "3D", "4C"), LowRule.BADUGI)
    # AS and 2S share spades; only one survives. Result: 3-card 4-3-A or 4-3-2.
    assert not lr.qualifies
    assert lr.ranks[0] == -3


def test_badugi_compare_lower_wins():
    """A-2-3-4 four-suits beats A-2-3-5 four-suits."""
    best = best_low(H("AS", "2H", "3D", "4C"), LowRule.BADUGI)
    next_best = best_low(H("AS", "2H", "3D", "5C"), LowRule.BADUGI)
    assert low_ranks_compare(best, next_best) == -1


def test_badugi_picks_best_subset_from_oversized_hand():
    """6 cards available — picks the best 4-card badugi possible."""
    lr = best_low(
        H("AS", "AH", "2D", "3C", "4H", "5S"), LowRule.BADUGI,
    )
    # AS used (spade), 2D (diamond), 3C (club), 4H (heart) -> A-2-3-4 four suits.
    assert lr.qualifies
    assert lr.ranks == (-4, 4, 3, 2, 1)


# ---- qualifier ordering across rules -----------------------------------

def test_non_qualifying_low_loses_to_qualifying():
    qualifying = best_low(
        H("AS", "3H", "5D", "7C", "8S"),
        LowRule.ACE_TO_FIVE, eight_or_better=True,
    )
    not_qualifying = best_low(
        H("AS", "3H", "5D", "7C", "9S"),
        LowRule.ACE_TO_FIVE, eight_or_better=True,
    )
    assert low_ranks_compare(qualifying, not_qualifying) == -1
    assert low_ranks_compare(not_qualifying, qualifying) == 1
