"""Variant DSL tests: round-trip, library completeness, sanity checks."""
from app.poker.deck import DeckSpec
from app.poker.evaluator.low import LowRule
from app.poker.evaluator.wilds import WildMode
from app.poker.variants import (
    DealScheme,
    HandRequirement,
    HiLoSplit,
    VariantSpec,
    WildKind,
    WildRule,
    all_variants,
)


def test_library_contains_required_variants():
    names = {v.name for v in all_variants()}
    for required in (
        "Texas Hold'em",
        "Omaha",
        "Omaha Hi/Lo (8 or better)",
        "7-Card Stud",
        "7-Card Stud Hi/Lo (8 or better)",
        "Razz",
        "5-Card Draw",
        "2-7 Triple Draw",
        "Badugi",
        "Follow the Queen",
        "Baseball",
        "Anaconda (Pass the Trash)",
    ):
        assert required in names


def test_holdem_53_joker_sf_only_matches_home_rule():
    v = next(v for v in all_variants() if "53-card" in v.name)
    assert v.deck.jokers == 1
    assert len(v.wilds) == 1
    rule = v.wilds[0]
    assert rule.kind == WildKind.JOKER
    assert rule.mode == WildMode.STRAIGHT_FLUSH_ONLY


def test_omaha_hilo_uses_2_3_constraint_and_a5_low():
    v = next(v for v in all_variants() if v.name == "Omaha Hi/Lo (8 or better)")
    assert v.hand == HandRequirement.OMAHA_2_HOLE_3_BOARD
    assert v.hi_lo == HiLoSplit.SPLIT
    assert v.lo_rule == LowRule.ACE_TO_FIVE
    assert v.lo_eight_or_better is True


def test_razz_is_lo_only_a5():
    v = next(v for v in all_variants() if v.name == "Razz")
    assert v.hi_lo == HiLoSplit.LO_ONLY
    assert v.lo_rule == LowRule.ACE_TO_FIVE
    assert v.lo_eight_or_better is False


def test_two_seven_triple_draw_uses_d27():
    v = next(v for v in all_variants() if v.name == "2-7 Triple Draw")
    assert v.lo_rule == LowRule.DEUCE_TO_SEVEN
    assert v.deal.draws == [5, 5, 5]


def test_badugi_uses_badugi_rule():
    v = next(v for v in all_variants() if v.name == "Badugi")
    assert v.hand == HandRequirement.BADUGI_4_OF_HOLE
    assert v.lo_rule == LowRule.BADUGI


def test_follow_the_queen_marks_queens_wild():
    v = next(v for v in all_variants() if v.name == "Follow the Queen")
    assert v.wilds[0].kind == WildKind.RANK
    assert v.wilds[0].rank == "Q"


def test_baseball_marks_3s_and_9s_wild():
    v = next(v for v in all_variants() if v.name == "Baseball")
    ranks = {w.rank for w in v.wilds if w.kind == WildKind.RANK}
    assert ranks == {"3", "9"}


def test_ice_age_marks_four_ranks_wild():
    v = next(v for v in all_variants() if v.name == "Ice Age")
    ranks = {w.rank for w in v.wilds if w.kind == WildKind.RANK}
    assert ranks == {"3", "6", "9", "Q"}


def test_variant_round_trip_through_dict():
    for v in all_variants():
        d = v.to_dict()
        v2 = VariantSpec.from_dict(d)
        assert v.to_dict() == v2.to_dict(), f"round-trip mismatch on {v.name}"


def test_custom_variant_construction():
    """Confirm a hand-built variant constructs cleanly."""
    v = VariantSpec(
        name="My Custom Game",
        description="Test",
        family="home",
        deck=DeckSpec(decks=1, jokers=2),
        deal=DealScheme(hole_cards=5, draws=[3]),
        wilds=[WildRule(kind=WildKind.JOKER, mode=WildMode.FULLY_WILD)],
        hand=HandRequirement.EXACTLY_5_HOLE,
        hi_lo=HiLoSplit.SPLIT,
        lo_rule=LowRule.ACE_TO_FIVE,
        lo_eight_or_better=True,
    )
    d = v.to_dict()
    assert d["deck"] == {"decks": 1, "jokers": 2}
    assert d["lo_rule"] == "ace_to_five"
    assert d["lo_eight_or_better"] is True
