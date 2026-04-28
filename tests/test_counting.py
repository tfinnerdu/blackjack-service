from app.counting import HI_LO_VALUES, Counter, hi_lo_value
from app.engine.cards import Card, Suit


def C(rank: str, suit: str = "S") -> Card:
    return Card(rank, Suit(suit))


def test_hi_lo_card_values():
    for r in ("2", "3", "4", "5", "6"):
        assert hi_lo_value(r) == 1
    for r in ("7", "8", "9"):
        assert hi_lo_value(r) == 0
    for r in ("T", "J", "Q", "K", "A"):
        assert hi_lo_value(r) == -1


def test_counter_running_count_updates():
    c = Counter(decks=6)
    c.see_many([C("2"), C("3"), C("T"), C("A"), C("8")])
    # +1 +1 -1 -1 0 = 0
    assert c.running_count == 0
    assert c.cards_seen == 5


def test_counter_true_count_at_full_shoe():
    c = Counter(decks=6)
    c.running_count = 6  # forced for math test
    # 6 decks * 52 = 312 cards remaining; 6 / 6.0 = 1.0
    assert c.true_count == 1.0


def test_counter_true_count_scales_with_remaining_decks():
    c = Counter(decks=6)
    # Burn through 4 decks (208 cards) — 2 decks remaining.
    for _ in range(208):
        c.see(C("8"))  # 0-value card; running stays 0
    c.running_count = 4
    # 4 / 2.0 = 2.0
    assert c.true_count == 2.0


def test_counter_handles_zero_decks_remaining():
    c = Counter(decks=1)
    for _ in range(52):
        c.see(C("8"))
    assert c.cards_remaining == 0
    assert c.true_count == 0.0  # don't divide by zero


def test_counter_reset():
    c = Counter(decks=6)
    c.see_many([C("2"), C("T")])
    c.reset()
    assert c.running_count == 0
    assert c.cards_seen == 0
