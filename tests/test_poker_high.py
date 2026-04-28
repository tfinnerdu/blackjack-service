"""High-hand evaluator tests. Each canonical hand class plus the tricky
ones (wheel straight, steel wheel, kicker order)."""
from app.poker.cards import parse_cards
from app.poker.evaluator import HandClass, best_high, classify_high


def H(*tokens: str):
    return parse_cards(tokens)


def cls(tokens):
    return classify_high(tokens).cls


# ---- canonical class detections ----------------------------------------

def test_high_card():
    assert cls(H("2C", "5D", "9H", "JS", "KH")) == HandClass.HIGH_CARD


def test_pair():
    assert cls(H("AS", "AH", "2D", "5C", "9H")) == HandClass.PAIR


def test_two_pair():
    assert cls(H("AS", "AH", "5D", "5C", "9H")) == HandClass.TWO_PAIR


def test_three_of_a_kind():
    assert cls(H("AS", "AH", "AD", "5C", "9H")) == HandClass.THREE_OF_A_KIND


def test_straight():
    assert cls(H("5S", "6H", "7D", "8C", "9H")) == HandClass.STRAIGHT


def test_wheel_straight_a_low():
    rank = classify_high(H("AS", "2H", "3D", "4C", "5H"))
    assert rank.cls == HandClass.STRAIGHT
    assert rank.tiebreakers == (5,)  # 5-high


def test_broadway_straight_a_high():
    rank = classify_high(H("TS", "JH", "QD", "KC", "AH"))
    assert rank.cls == HandClass.STRAIGHT
    assert rank.tiebreakers == (14,)


def test_flush():
    assert cls(H("2S", "5S", "9S", "JS", "KS")) == HandClass.FLUSH


def test_full_house():
    assert cls(H("AS", "AH", "AD", "5C", "5H")) == HandClass.FULL_HOUSE


def test_four_of_a_kind():
    assert cls(H("AS", "AH", "AD", "AC", "5H")) == HandClass.FOUR_OF_A_KIND


def test_straight_flush():
    assert cls(H("5H", "6H", "7H", "8H", "9H")) == HandClass.STRAIGHT_FLUSH


def test_steel_wheel_a_low_straight_flush():
    rank = classify_high(H("AH", "2H", "3H", "4H", "5H"))
    assert rank.cls == HandClass.STRAIGHT_FLUSH
    assert rank.tiebreakers == (5,)


# ---- comparison ordering -----------------------------------------------

def test_full_house_beats_flush():
    fh = classify_high(H("KS", "KH", "KD", "5C", "5H"))
    flush = classify_high(H("2S", "5S", "9S", "JS", "AS"))
    assert fh > flush


def test_higher_straight_wins():
    a = classify_high(H("9D", "TS", "JH", "QC", "KH"))   # T-J-Q-K-A? no, 9-K
    b = classify_high(H("5C", "6H", "7D", "8S", "9C"))   # 9-high straight
    assert a > b


def test_kicker_order_matters():
    # Both two-pair AA-22, kickers differ.
    a = classify_high(H("AS", "AH", "2D", "2C", "KH"))
    b = classify_high(H("AS", "AH", "2D", "2C", "QH"))
    assert a > b


def test_full_house_higher_trip_wins():
    a = classify_high(H("KS", "KH", "KD", "2C", "2H"))   # KKK22
    b = classify_high(H("QS", "QH", "QD", "AC", "AH"))   # QQQAA
    assert a > b


# ---- best_high N-from-7 -----------------------------------------------

def test_best_5_of_7_picks_straight_flush():
    cards = H("2H", "5H", "6H", "7H", "8H", "9H", "AC")
    rank = best_high(cards)
    assert rank.cls == HandClass.STRAIGHT_FLUSH
    assert rank.tiebreakers == (9,)


def test_best_5_of_7_picks_full_house_over_flush():
    # Three Ks + two 5s + two random hearts -> full house wins over the
    # flush you'd have if you kept the hearts.
    cards = H("KS", "KC", "KD", "5H", "5C", "2H", "9H")
    rank = best_high(cards)
    assert rank.cls == HandClass.FULL_HOUSE


def test_best_5_handles_exactly_5_cards():
    cards = H("KS", "KH", "QD", "QC", "9H")
    rank = best_high(cards)
    assert rank.cls == HandClass.TWO_PAIR


# ---- Omaha-style must_use=2 -------------------------------------------

def test_omaha_must_use_two_from_hole():
    """Omaha: a player whose hole has 4 hearts and the board has only 1
    heart still cannot make a flush — must use exactly 2 from hole."""
    hole = H("AH", "KH", "QH", "JH")
    board = H("2H", "3D", "4C", "5S", "6H")
    rank = best_high([], must_use=2, hole=hole, board=board)
    # Best is AH+KH from hole + 2H+3D+4C from board. No 5-card flush
    # possible because hole contributes only 2 hearts. Best high here is
    # whatever 2-from-hole + 3-from-board produces.
    # AH-KH + 4C-5S-6H = high card A. Pair-less / straight-less.
    # AH-2H from hole isn't possible (no 2H in hole). Try AH-QH +
    # 2H-3D-4C-5S-6H -> pick 5 of 7; constrained: only 5 = AH-QH-3D-5S-6H
    # etc. None give a straight/flush given the constraint. So:
    assert rank.cls in (HandClass.HIGH_CARD, HandClass.PAIR)
    # Sanity: this would be a flush WITHOUT the must_use=2 restriction.
    relaxed = best_high(list(hole) + list(board))
    assert relaxed.cls == HandClass.FLUSH


def test_omaha_must_use_two_from_hole_real_flush():
    """Omaha: 2 hearts in hole + 3 hearts on board = legitimate flush."""
    hole = H("AH", "KH", "5C", "6D")
    board = H("2H", "3H", "4H", "TS", "JD")
    rank = best_high([], must_use=2, hole=hole, board=board)
    assert rank.cls == HandClass.FLUSH
