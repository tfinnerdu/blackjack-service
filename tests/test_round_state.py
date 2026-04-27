"""Snapshot + restore round-trip test. Reuses the rigged-shoe pattern
from test_round.py.
"""
from app.engine.cards import Card, Suit
from app.engine.round import Round, Seat
from app.engine.rules import Rules, SideBets
from app.services.round_state import round_from_json, round_to_json


def C(rank: str, suit: str = "S") -> Card:
    return Card(rank, Suit(suit))


class RiggedShoe:
    def __init__(self, cards):
        self._cards = list(cards)
        self.shuffles = 1
        self.mode = "casino"

    def next_card(self):
        return self._cards.pop(0)

    def deal(self, n):
        return [self.next_card() for _ in range(n)]

    @property
    def needs_reshuffle(self):
        return False


def test_round_snapshot_restore_mid_play():
    rules = Rules(insurance_offered=False, dealer_peeks=False)
    sbets = SideBets()
    cards = [C("T"), C("6"), C("8"), C("T")]  # P=18, dealer 6up
    rnd = Round(rules, sbets, RiggedShoe(cards))
    rnd.add_seat(Seat(seat_num=1, main_bet=10, is_human=True))
    rnd.deal()
    assert rnd.state.value == "playing"

    payload = round_to_json(rnd, cards_dealt_at_start=0, cards_consumed=4)

    # Rebuild — shoe needs the player's hit card + dealer's hit card.
    new_shoe = RiggedShoe([C("3"), C("6")])  # player 18+3=21, dealer 16+6=22 bust
    restored = round_from_json(payload, rules, sbets, new_shoe)
    assert restored.state.value == "playing"
    assert restored.active_seat.seat_num == 1
    assert restored.active_hand.total == 18

    restored.act("hit")
    assert restored.active_hand.total == 21
    restored.act("stand")
    assert restored.state.value == "complete"
    assert restored.result.dealer_hand.is_bust
    assert restored.result.outcomes[0].result == "win"


def test_round_snapshot_preserves_split_state():
    rules = Rules(insurance_offered=False, dealer_peeks=False)
    sbets = SideBets()
    cards = [
        C("8", "S"), C("6"),       # P1, dealer up
        C("8", "H"), C("T"),       # P2, dealer hole
        C("5"), C("4"),             # split draws
    ]
    rnd = Round(rules, sbets, RiggedShoe(cards))
    rnd.add_seat(Seat(seat_num=1, main_bet=10, is_human=True))
    rnd.deal()
    rnd.act("split")
    assert len(rnd.seats[0].hands) == 2

    payload = round_to_json(rnd, cards_dealt_at_start=0, cards_consumed=6)
    restored = round_from_json(payload, rules, sbets, RiggedShoe([]))
    assert len(restored.seats[0].hands) == 2
    assert restored._split_count_per_seat[1] == 1
    assert restored.seats[0].hands[0].is_split_hand
    assert restored.seats[0].hands[1].is_split_hand
