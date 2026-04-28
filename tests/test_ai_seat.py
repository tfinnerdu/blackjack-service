"""End-to-end tests for AISeat — combines playstyle + bet pattern."""
from app.ai import AISeat
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


def test_ai_seat_bust_returns_zero_bet():
    seat = AISeat(seat_num=1, base_bet=10, bankroll=0, rebuy_on_bust=False)
    assert seat.is_bust
    assert seat.pick_bet(Rules()) == 0


def test_ai_seat_rebuy_on_bust():
    seat = AISeat(
        seat_num=1, base_bet=10, bankroll=0, rebuy_on_bust=True, rebuy_amount=200
    )
    bet = seat.pick_bet(Rules())
    assert bet > 0
    assert seat.bankroll == 200


def test_ai_seat_book_action():
    seat = AISeat(seat_num=2, playstyle="book", bankroll=200)
    rules = Rules(dealer_hits_soft_17=True)
    caps = Capabilities(can_double=True, can_split=False, can_surrender=True)
    action = seat.pick_action(H("T", "6"), C("T"), rules, caps, None)
    assert action == "surrender"


def test_ai_seat_record_result_updates_bankroll_and_history():
    seat = AISeat(seat_num=1, bankroll=200, base_bet=10)
    seat.record_result(15)
    assert seat.bankroll == 215
    seat.record_result(-10)
    assert seat.bankroll == 205
    assert seat.last_results == [15, -10]


def test_drunk_seat_uses_mistake_rate():
    seat = AISeat(
        seat_num=1, playstyle="drunk", bankroll=200,
        drunk_mistake_rate=1.0, seed=42,
    )
    rules = Rules()
    caps = Capabilities(can_double=True, can_split=False, can_surrender=False)
    # With 100% mistake rate the seat should not always pick book action.
    seen = set()
    for _ in range(20):
        seen.add(seat.pick_action(H("T", "6"), C("9"), rules, caps, None))
    # At least two distinct actions across 20 picks.
    assert len(seen) >= 2


def test_unknown_playstyle_raises():
    import pytest

    seat = AISeat(seat_num=1, playstyle="not_a_thing", bankroll=200)
    with pytest.raises(KeyError):
        seat.pick_action(H("T", "6"), C("9"), Rules(),
                        Capabilities(True, False, False), None)
