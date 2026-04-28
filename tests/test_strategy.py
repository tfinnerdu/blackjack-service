"""Strategy chart tests. Cover the canonical 'must be right' plays plus
H17/S17 differences and DAS effects.
"""
from app.engine.cards import Card, Suit
from app.engine.hand import Hand
from app.engine.rules import Rules
from app.strategy import Capabilities, basic_strategy


def C(rank: str, suit: str = "S") -> Card:
    return Card(rank, Suit(suit))


def H(*ranks: str) -> Hand:
    h = Hand()
    for r in ranks:
        h.add_card(C(r))
    return h


def caps(can_double=True, can_split=True, can_surrender=True) -> Capabilities:
    return Capabilities(
        can_double=can_double, can_split=can_split, can_surrender=can_surrender
    )


# ---- canonical hard totals ---------------------------------------------

def test_hard_16_vs_7_hits():
    rules = Rules(dealer_hits_soft_17=True)
    assert basic_strategy(H("T", "6"), C("7"), rules, caps()) == "hit"


def test_hard_16_vs_6_stands():
    rules = Rules(dealer_hits_soft_17=True)
    assert basic_strategy(H("T", "6"), C("6"), rules, caps()) == "stand"


def test_hard_11_vs_a_h17_doubles():
    rules = Rules(dealer_hits_soft_17=True)
    assert basic_strategy(H("5", "6"), C("A"), rules, caps()) == "double"


def test_hard_11_vs_a_s17_hits():
    rules = Rules(dealer_hits_soft_17=False)
    assert basic_strategy(H("5", "6"), C("A"), rules, caps()) == "hit"


def test_hard_9_doubles_3_through_6():
    rules = Rules(dealer_hits_soft_17=True)
    for up in ("3", "4", "5", "6"):
        assert basic_strategy(H("4", "5"), C(up), rules, caps()) == "double"
    assert basic_strategy(H("4", "5"), C("2"), rules, caps()) == "hit"
    assert basic_strategy(H("4", "5"), C("7"), rules, caps()) == "hit"


def test_hard_10_does_not_double_vs_t():
    rules = Rules(dealer_hits_soft_17=True)
    assert basic_strategy(H("4", "6"), C("T"), rules, caps()) == "hit"


# ---- soft totals -------------------------------------------------------

def test_soft_18_a7_vs_9_hits():
    rules = Rules(dealer_hits_soft_17=True)
    assert basic_strategy(H("A", "7"), C("9"), rules, caps()) == "hit"


def test_soft_18_a7_vs_2_h17_doubles_else_stands():
    """H17: A,7 vs 2 is Ds (double else stand) — capabilities decide."""
    rules = Rules(dealer_hits_soft_17=True)
    assert basic_strategy(H("A", "7"), C("2"), rules, caps()) == "double"
    # When can't double (3-card hand, etc.), fall back to stand.
    assert basic_strategy(H("A", "7"), C("2"), rules, caps(can_double=False)) == "stand"


def test_soft_18_a7_vs_2_s17_stands():
    rules = Rules(dealer_hits_soft_17=False)
    assert basic_strategy(H("A", "7"), C("2"), rules, caps()) == "stand"


def test_soft_19_stands_everywhere():
    rules = Rules(dealer_hits_soft_17=False)
    for up in (2, 3, 4, 5, 6, 7, 8, 9, 10):
        rank = "T" if up == 10 else str(up)
        assert basic_strategy(H("A", "8"), C(rank), rules, caps()) == "stand"


# ---- pairs -------------------------------------------------------------

def test_aces_always_split():
    rules = Rules()
    for up in (2, 3, 4, 5, 6, 7, 8, 9, 10):
        rank = "T" if up == 10 else str(up)
        assert basic_strategy(H("A", "A"), C(rank), rules, caps()) == "split"


def test_eights_always_split_s17():
    rules = Rules(dealer_hits_soft_17=False)
    for up in (2, 3, 4, 5, 6, 7, 8, 9, 10):
        rank = "T" if up == 10 else str(up)
        assert basic_strategy(H("8", "8"), C(rank), rules, caps()) == "split"


def test_eights_vs_a_h17_surrender_else_split():
    rules = Rules(dealer_hits_soft_17=True)
    assert basic_strategy(H("8", "8"), C("A"), rules, caps()) == "surrender"
    assert (
        basic_strategy(H("8", "8"), C("A"), rules, caps(can_surrender=False))
        == "split"
    )


def test_tens_never_split():
    rules = Rules()
    assert basic_strategy(H("K", "Q"), C("6"), rules, caps()) == "stand"
    assert basic_strategy(H("T", "T"), C("5"), rules, caps()) == "stand"


def test_fives_double_treat_as_ten():
    rules = Rules()
    assert basic_strategy(H("5", "5"), C("6"), rules, caps()) == "double"
    assert basic_strategy(H("5", "5"), C("T"), rules, caps()) == "hit"


def test_22_33_vs_low_split_with_das():
    rules_das = Rules(double_after_split=True)
    assert basic_strategy(H("2", "2"), C("2"), rules_das, caps()) == "split"
    assert basic_strategy(H("3", "3"), C("3"), rules_das, caps()) == "split"


def test_22_33_vs_low_hit_without_das():
    rules_no_das = Rules(double_after_split=False)
    assert basic_strategy(H("2", "2"), C("2"), rules_no_das, caps()) == "hit"
    assert basic_strategy(H("3", "3"), C("3"), rules_no_das, caps()) == "hit"


def test_44_vs_5_or_6_split_with_das_only():
    rules_das = Rules(double_after_split=True)
    rules_no_das = Rules(double_after_split=False)
    assert basic_strategy(H("4", "4"), C("5"), rules_das, caps()) == "split"
    assert basic_strategy(H("4", "4"), C("5"), rules_no_das, caps()) == "hit"


# ---- surrender ---------------------------------------------------------

def test_16_vs_t_surrender_when_allowed():
    rules = Rules(dealer_hits_soft_17=True)
    assert basic_strategy(H("T", "6"), C("T"), rules, caps()) == "surrender"
    # No surrender? Hit.
    assert (
        basic_strategy(H("T", "6"), C("T"), rules, caps(can_surrender=False))
        == "hit"
    )


def test_15_vs_a_h17_surrender():
    rules = Rules(dealer_hits_soft_17=True)
    assert basic_strategy(H("T", "5"), C("A"), rules, caps()) == "surrender"


def test_15_vs_a_s17_hits_no_surrender():
    rules = Rules(dealer_hits_soft_17=False)
    # S17 chart says hit on 15 vs A.
    assert basic_strategy(H("T", "5"), C("A"), rules, caps()) == "hit"
