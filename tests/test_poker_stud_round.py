"""7-Card Stud + Razz state machine tests."""
import pytest

from app.poker.cards import parse_cards
from app.poker.deck import DeckSpec
from app.poker.pot import BetAction, Player
from app.poker.stud_round import (
    StudHandConfig,
    StudRound,
    StudState,
)
from app.poker.variants import all_variants


def _seven_stud():
    return next(v for v in all_variants() if v.name == "7-Card Stud")


def _razz():
    return next(v for v in all_variants() if v.name == "Razz")


class RiggedShoe:
    def __init__(self, tokens):
        self._cards = list(parse_cards(tokens))
        self.shuffles = 1
        self.spec = DeckSpec(decks=1, jokers=0)

    def next_card(self):
        return self._cards.pop(0)

    def deal(self, n):
        return [self.next_card() for _ in range(n)]

    @property
    def cards_remaining(self):
        return len(self._cards)


def _two_handed():
    return [
        Player(seat_num=1, name="Hero", stack=1000, is_human=True),
        Player(seat_num=2, name="Villain", stack=1000),
    ]


# ---- 7-Card Stud lifecycle --------------------------------------------

def test_7stud_initial_deal_is_2_down_1_up():
    rnd = StudRound(_seven_stud(), _two_handed(),
                    StudHandConfig(small_bet=5, big_bet=10), seed=1)
    rnd.start()
    for seat in (1, 2):
        slots = rnd.hands[seat]
        assert len(slots) == 3
        # Two down + one up.
        assert sum(1 for s in slots if not s.up) == 2
        assert sum(1 for s in slots if s.up) == 1


def test_7stud_state_starts_in_betting():
    rnd = StudRound(_seven_stud(), _two_handed(),
                    StudHandConfig(small_bet=5, big_bet=10), seed=2)
    rnd.start()
    assert rnd.state == StudState.BETTING
    assert rnd.street_index == 0


def test_7stud_progresses_through_5_streets_to_showdown():
    """Both players check through every street; full lifecycle reaches
    SHOWDOWN with 7 cards each."""
    rnd = StudRound(_seven_stud(), _two_handed(),
                    StudHandConfig(small_bet=5, big_bet=10), seed=3)
    rnd.start()
    # 5 betting rounds total: 3rd, 4th, 5th, 6th, 7th. Each round has 2
    # players checking (no bet to call).
    for _ in range(5):
        # First seat acts (legal: check, bet, fold, all_in).
        rnd.act(BetAction.CHECK)
        # Second seat acts.
        rnd.act(BetAction.CHECK)
    assert rnd.state == StudState.COMPLETE
    for seat in (1, 2):
        assert len(rnd.hands[seat]) == 7


def test_7stud_last_card_is_face_down():
    rnd = StudRound(_seven_stud(), _two_handed(),
                    StudHandConfig(small_bet=5, big_bet=10), seed=4)
    rnd.start()
    for _ in range(5):
        rnd.act(BetAction.CHECK)
        rnd.act(BetAction.CHECK)
    for seat in (1, 2):
        slots = rnd.hands[seat]
        # Card 7 (last) should be face-down.
        assert slots[6].up is False


def test_7stud_fold_through_settles():
    rnd = StudRound(_seven_stud(), _two_handed(),
                    StudHandConfig(small_bet=5, big_bet=10), seed=5)
    rnd.start()
    rnd.act(BetAction.FOLD)
    assert rnd.state == StudState.COMPLETE
    assert 2 in rnd.result.winner_seats


def test_7stud_showdown_picks_best_5_of_7():
    """Rig a deal where seat 1 ends with a flush and seat 2 with a pair.
    Hero should win on showdown."""
    # Deal order in start():
    # 1) hole_cards loop: each player gets cards in seat order, twice
    # 2) up_cards loop: each player gets one face-up
    # 3) For each subsequent street (4 total), each player gets one
    #    face-up card; final street is face-down.
    # So sequence per round = [seat1 card, seat2 card, ...]. Total 14 cards.
    tokens = [
        # Round 1 hole: seat1 card0, seat2 card0
        "AS", "9C",
        # Round 2 hole: seat1 card1, seat2 card1
        "KS", "9D",
        # Round 3 (initial up): seat1, seat2
        "QS", "5H",
        # 4th street up
        "JS", "8C",
        # 5th street up
        "TS", "7D",
        # 6th street up
        "2D", "6H",
        # 7th street down
        "3C", "4S",
    ]
    rnd = StudRound(_seven_stud(), _two_handed(),
                    StudHandConfig(small_bet=5, big_bet=10),
                    shoe=RiggedShoe(tokens))
    rnd.start()
    for _ in range(5):
        rnd.act(BetAction.CHECK)
        rnd.act(BetAction.CHECK)
    assert rnd.state == StudState.COMPLETE
    # Seat 1: AS,KS,QS,JS,TS,2D,3C — 5 spades A-K-Q-J-T = ROYAL FLUSH.
    # Seat 2: 9C,9D,5H,8C,7D,6H,4S — pair of 9s + 8-7-6-5-4 straight!
    # Actually seat 2: 4S,5H,6H,7D,8C = 8-high straight (better than pair).
    # Hero's straight flush > Villain's straight.
    seat1_outcome = next(o for o in rnd.result.outcomes if o.seat_num == 1)
    assert "lush" in seat1_outcome.final_hand_name.lower() or "Straight flush" in seat1_outcome.final_hand_name
    assert 1 in rnd.result.winner_seats


# ---- Razz (lo only) ---------------------------------------------------

def test_razz_showdown_uses_a5_low_evaluator():
    """Razz: lowest 5-card A-5 hand wins. Rig wheel for hero."""
    tokens = [
        # Hole 1: AS, KS
        "AS", "KS",
        # Hole 2: 2H, KH
        "2H", "KH",
        # Initial up
        "3D", "QC",
        # 4th up
        "4C", "JD",
        # 5th up
        "5S", "TC",
        # 6th up
        "9D", "8H",
        # 7th down (face-down)
        "6C", "7S",
    ]
    rnd = StudRound(_razz(), _two_handed(),
                    StudHandConfig(small_bet=5, big_bet=10),
                    shoe=RiggedShoe(tokens))
    rnd.start()
    for _ in range(5):
        rnd.act(BetAction.CHECK)
        rnd.act(BetAction.CHECK)
    assert rnd.state == StudState.COMPLETE
    # Hero has A,K,3,4,5,9,6 → best A-5 low = A-3-4-5-6 (no qualifier
    # since Razz is no-qualifier). That's a 6-high.
    # Villain has 2,K,Q,J,T,8,7 → best low ranks 2-7-8-T-J = J-high.
    # Hero wins.
    assert 1 in rnd.result.winner_seats


# ---- guard rails ------------------------------------------------------

def test_rejects_non_stud_variant():
    holdem = next(v for v in all_variants() if v.name == "Texas Hold'em")
    with pytest.raises(ValueError):
        StudRound(holdem, _two_handed(), StudHandConfig(), seed=1)
