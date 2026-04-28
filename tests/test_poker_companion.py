"""Companion-mode evaluator: variant + cards -> analysis."""
from app.poker.cards import parse_cards
from app.poker.companion import analyze
from app.poker.variants import all_variants


def H(*tokens: str):
    return parse_cards(tokens)


def _variant(name: str):
    return next(v for v in all_variants() if v.name == name)


# ---- Hold'em -----------------------------------------------------------

def test_holdem_analyzes_flush():
    v = _variant("Texas Hold'em")
    cards = H("AS", "KS", "5S", "9S", "2S", "7H", "8D")
    a = analyze(v, cards)
    assert a.hi is not None
    assert a.hi.cls_name == "Flush"
    assert a.lo is None
    assert a.hi_lo_explanation.startswith("High hand wins")


def test_holdem_53_joker_completes_flush_under_sf_only():
    v = _variant("Hold'em (53-card, joker S/F only)")
    # Player has joker + 4 hearts.
    cards = H("JK", "AH", "KH", "5H", "9H", "7C", "2D")
    a = analyze(v, cards)
    assert a.hi.cls_name == "Flush"
    assert "joker" in (a.wild_resolution or "")


def test_holdem_53_joker_dead_when_no_sf():
    v = _variant("Hold'em (53-card, joker S/F only)")
    # No flush draw, no straight draw — joker should die.
    cards = H("JK", "AS", "AH", "5C", "9C", "7D", "2D")
    a = analyze(v, cards)
    # AA + 5/9/7/2 = pair of aces. Joker dead.
    assert a.hi.cls_name == "Pair"


# ---- Omaha -------------------------------------------------------------

def test_omaha_must_use_two_from_hole():
    v = _variant("Omaha")
    hole = H("AH", "KH", "QH", "JH")
    board = H("2H", "3H", "4D", "5D", "6S")
    a = analyze(v, [], hole=hole, board=board)
    # Without the 2+3 constraint this would be a 5-heart flush. With it,
    # only 2 hearts can come from the hole — no flush.
    assert a.hi.cls_name != "Flush"


def test_omaha_hilo_qualifies_with_8_or_better_low():
    v = _variant("Omaha Hi/Lo (8 or better)")
    hole = H("AH", "2D", "TC", "JC")
    board = H("3S", "4H", "8D", "KD", "QC")
    a = analyze(v, [], hole=hole, board=board)
    assert a.lo is not None
    assert a.lo.qualifies
    assert "Pot splits" in a.hi_lo_explanation


def test_omaha_hilo_no_low_when_no_qualifier():
    v = _variant("Omaha Hi/Lo (8 or better)")
    # All board cards 9 or above -> no qualifying low possible.
    hole = H("AH", "AD", "TC", "JC")
    board = H("9S", "TH", "JD", "QD", "KC")
    a = analyze(v, [], hole=hole, board=board)
    assert a.lo is not None
    assert not a.lo.qualifies
    assert "qualifying" in a.lo.explanation.lower()


# ---- Razz --------------------------------------------------------------

def test_razz_lo_only_no_hi():
    v = _variant("Razz")
    cards = H("AH", "2D", "3C", "4S", "5H", "QC", "KD")
    a = analyze(v, cards)
    assert a.hi is None  # lo-only
    assert a.lo is not None
    assert a.lo.qualifies
    assert "wheel" in a.lo.name.lower()


# ---- 2-7 Triple Draw ---------------------------------------------------

def test_d27_seven_high_unsuited_is_best():
    v = _variant("2-7 Triple Draw")
    cards = H("2C", "3H", "4S", "5D", "7C")
    a = analyze(v, cards)
    assert a.hi is None
    assert a.lo is not None
    assert "7" in a.lo.name


def test_d27_explains_aces_high():
    v = _variant("2-7 Triple Draw")
    cards = H("2C", "3H", "4S", "5D", "7C")
    a = analyze(v, cards)
    assert "high" in a.lo.explanation.lower()


# ---- Badugi ------------------------------------------------------------

def test_badugi_qualifies_with_4_distinct_suits():
    v = _variant("Badugi")
    a = analyze(v, H("AS", "2H", "3D", "4C"))
    assert a.lo.qualifies
    assert "4-card" in a.lo.name


def test_badugi_does_not_qualify_with_pair():
    v = _variant("Badugi")
    a = analyze(v, H("AS", "AH", "3D", "4C"))
    assert not a.lo.qualifies


# ---- Wild rules across variants ---------------------------------------

def test_baseball_treats_3s_and_9s_as_wild():
    v = _variant("Baseball")
    cards = H("3H", "9D", "AS", "AH", "KS", "QH", "JC")
    a = analyze(v, cards)
    # Two wilds + AA -> minimum quad aces (or better).
    assert a.hi.cls_value >= 7  # FOUR_OF_A_KIND or higher


def test_follow_the_queen_treats_queens_as_wild():
    v = _variant("Follow the Queen")
    cards = H("QH", "AS", "AH", "AD", "5C", "8H", "9D")
    a = analyze(v, cards)
    # Joker-equivalent wild + trip aces -> at least quads.
    assert a.hi.cls_value >= 7


# ---- hands_that_beat_you ----------------------------------------------

def test_hands_that_beat_a_pair_includes_two_pair_through_5oak():
    v = _variant("Texas Hold'em")
    cards = H("AS", "AH", "5C", "9D", "2H", "8C", "TD")
    a = analyze(v, cards)
    assert "Two pair" in a.hands_that_beat_you
    assert "Straight flush" in a.hands_that_beat_you
