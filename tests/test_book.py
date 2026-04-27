"""Book oracle tests. Specifically, that count-based deviations override
basic strategy when the threshold is crossed and fall back when it isn't.
"""
from app.engine.cards import Card, Suit
from app.engine.hand import Hand
from app.engine.rules import Rules
from app.strategy import Capabilities
from app.strategy.book import book, book_insurance


def C(rank: str, suit: str = "S") -> Card:
    return Card(rank, Suit(suit))


def H(*ranks: str) -> Hand:
    h = Hand()
    for r in ranks:
        h.add_card(C(r))
    return h


def caps(d=True, sp=True, sr=True) -> Capabilities:
    return Capabilities(can_double=d, can_split=sp, can_surrender=sr)


def test_no_count_uses_basic_strategy():
    rules = Rules()
    call = book(H("T", "6"), C("T"), rules, caps())
    # Without a count, 16 vs T = surrender (basic strategy).
    assert call.action == "surrender"
    assert call.source == "basic"


def test_16_vs_t_at_tc0_stands_via_index():
    rules = Rules()
    call = book(H("T", "6"), C("T"), rules, caps(sr=False), true_count=0.0)
    # 16 vs T: stand at TC>=0 — overrides basic surrender.
    assert call.action == "stand"
    assert call.source == "index"
    assert "16 vs 10" in (call.deviation or "")


def test_16_vs_t_at_negative_count_falls_back_to_basic():
    rules = Rules()
    call = book(H("T", "6"), C("T"), rules, caps(sr=False), true_count=-1.0)
    # Below threshold — basic chart says hit (surrender denied).
    assert call.source == "basic"
    assert call.action == "hit"


def test_12_vs_3_at_high_count_stands():
    rules = Rules()
    call = book(H("7", "5"), C("3"), rules, caps(), true_count=2.5)
    # Threshold +2 — at TC 2.5 we stand.
    assert call.action == "stand"
    assert call.source == "index"


def test_12_vs_3_at_low_count_hits():
    rules = Rules()
    call = book(H("7", "5"), C("3"), rules, caps(), true_count=1.0)
    assert call.action == "hit"
    assert call.source == "basic"


def test_tt_vs_5_split_at_high_count():
    rules = Rules()
    call = book(H("T", "T"), C("5"), rules, caps(), true_count=5.5)
    assert call.action == "split"
    assert call.source == "index"


def test_tt_vs_5_normal_count_stands():
    rules = Rules()
    call = book(H("T", "T"), C("5"), rules, caps(), true_count=2.0)
    assert call.action == "stand"
    assert call.source == "basic"


def test_surrender_index_takes_priority_when_capable():
    rules = Rules()
    # 14 vs T at TC>=+3 surrender deviation.
    call = book(H("T", "4"), C("T"), rules, caps(), true_count=3.0)
    assert call.action == "surrender"
    assert call.source == "index"


def test_insurance_below_threshold_declines():
    call = book_insurance(true_count=2.0)
    assert call.note == "decline insurance"


def test_insurance_at_threshold_takes_it():
    call = book_insurance(true_count=3.0)
    assert call.note == "take insurance"
    assert "Insurance" in (call.deviation or "")
