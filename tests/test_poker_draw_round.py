"""5-Card Draw + 2-7 Triple Draw + Badugi state machine tests."""
import pytest

from app.poker.cards import parse_cards
from app.poker.deck import DeckSpec
from app.poker.draw_round import DrawHandConfig, DrawRound, DrawState
from app.poker.pot import BetAction, Player
from app.poker.variants import (
    DealScheme,
    HandRequirement,
    HiLoSplit,
    VariantSpec,
    all_variants,
)
from app.poker.evaluator.low import LowRule


def _five_card_draw():
    return next(v for v in all_variants() if v.name == "5-Card Draw")


def _two_seven():
    return next(v for v in all_variants() if v.name == "2-7 Triple Draw")


def _badugi():
    return next(v for v in all_variants() if v.name == "Badugi")


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


# ---- 5-Card Draw lifecycle --------------------------------------------

def test_5card_draw_blinds_and_initial_deal():
    """Each player gets 5 hole cards; first betting round pre-draw."""
    rnd = DrawRound(_five_card_draw(), _two_handed(),
                    DrawHandConfig(small_blind=5, big_blind=10, dealer_seat=1),
                    seed=1)
    rnd.start()
    assert rnd.state == DrawState.BETTING
    assert rnd.betting_round_index == 0
    for seat in (1, 2):
        assert len(rnd.holes[seat]) == 5


def test_5card_draw_reaches_drawing_state_after_pre_betting():
    rnd = DrawRound(_five_card_draw(), _two_handed(),
                    DrawHandConfig(small_blind=5, big_blind=10, dealer_seat=1),
                    seed=2)
    rnd.start()
    # Heads-up: SB acts first. Both check through.
    rnd.act(BetAction.CALL)
    rnd.act(BetAction.CHECK)
    assert rnd.state == DrawState.DRAWING
    assert rnd.draw_round_index == 0


def test_5card_draw_discard_replaces_chosen_indices():
    """Stand pat = 0 indices; discard 2 = those positions get replaced
    from the deck. Hand size stays at 5."""
    rnd = DrawRound(_five_card_draw(), _two_handed(),
                    DrawHandConfig(small_blind=5, big_blind=10, dealer_seat=1),
                    seed=3)
    rnd.start()
    rnd.act(BetAction.CALL)
    rnd.act(BetAction.CHECK)
    assert rnd.state == DrawState.DRAWING
    seat = rnd.active_seat.seat_num
    original = list(rnd.holes[seat])
    rnd.discard(seat, [0, 1])
    new_hole = rnd.holes[seat]
    assert len(new_hole) == 5
    # The kept positions are at the front (since we removed [0,1] then
    # appended). Original [2..4] should still be present.
    assert original[2] in new_hole
    assert original[3] in new_hole
    assert original[4] in new_hole


def test_5card_draw_full_lifecycle_to_showdown():
    rnd = DrawRound(_five_card_draw(), _two_handed(),
                    DrawHandConfig(small_blind=5, big_blind=10, dealer_seat=1),
                    seed=4)
    rnd.start()
    # Pre-draw betting.
    rnd.act(BetAction.CALL)
    rnd.act(BetAction.CHECK)
    # Drawing phase: both stand pat.
    seat_a = rnd.active_seat.seat_num
    rnd.discard(seat_a, [])
    seat_b = rnd.active_seat.seat_num
    rnd.discard(seat_b, [])
    # Post-draw betting: action begins to the left of dealer.
    assert rnd.state == DrawState.BETTING
    assert rnd.betting_round_index == 1
    rnd.act(BetAction.CHECK)
    rnd.act(BetAction.CHECK)
    assert rnd.state == DrawState.COMPLETE
    assert rnd.result is not None
    assert len(rnd.result.outcomes) == 2


def test_fold_through_in_first_betting_round_settles():
    rnd = DrawRound(_five_card_draw(), _two_handed(),
                    DrawHandConfig(small_blind=5, big_blind=10, dealer_seat=1),
                    seed=5)
    rnd.start()
    # Hero is SB; if they fold immediately, villain wins by fold-through.
    rnd.act(BetAction.FOLD)
    assert rnd.state == DrawState.COMPLETE
    assert 2 in rnd.result.winner_seats


# ---- 2-7 Triple Draw ----------------------------------------------------

def test_2_7_has_three_draw_phases():
    """2-7 Triple Draw walks through 4 betting rounds + 3 drawing rounds."""
    v = _two_seven()
    assert v.deal.draws == [5, 5, 5]
    assert v.lo_rule == LowRule.DEUCE_TO_SEVEN

    rnd = DrawRound(v, _two_handed(),
                    DrawHandConfig(small_blind=5, big_blind=10, dealer_seat=1),
                    seed=99)
    rnd.start()
    # Step through: 4 betting + 3 drawing.
    expected_drawn = 0
    for round_no in range(4):
        # Betting: both check through (or call+check on first).
        if round_no == 0:
            rnd.act(BetAction.CALL)
            rnd.act(BetAction.CHECK)
        else:
            rnd.act(BetAction.CHECK)
            rnd.act(BetAction.CHECK)
        if round_no < 3:
            # Drawing phase: both stand pat.
            assert rnd.state == DrawState.DRAWING
            seat_a = rnd.active_seat.seat_num
            rnd.discard(seat_a, [])
            seat_b = rnd.active_seat.seat_num
            rnd.discard(seat_b, [])
            expected_drawn += 1

    assert rnd.state == DrawState.COMPLETE
    assert rnd.draw_round_index == 3


# ---- Badugi --------------------------------------------------------------

def test_badugi_initial_deal_is_4_cards():
    v = _badugi()
    assert v.deal.hole_cards == 4
    rnd = DrawRound(v, _two_handed(),
                    DrawHandConfig(small_blind=5, big_blind=10, dealer_seat=1),
                    seed=42)
    rnd.start()
    for seat in (1, 2):
        assert len(rnd.holes[seat]) == 4


# ---- guard rails --------------------------------------------------------

def test_rejects_community_card_variant():
    holdem = next(v for v in all_variants() if v.name == "Texas Hold'em")
    with pytest.raises(ValueError):
        DrawRound(holdem, _two_handed(), DrawHandConfig(), seed=1)


def test_discard_too_many_rejected():
    rnd = DrawRound(_badugi(), _two_handed(),
                    DrawHandConfig(small_blind=5, big_blind=10, dealer_seat=1),
                    seed=1)
    rnd.start()
    rnd.act(BetAction.CALL)
    rnd.act(BetAction.CHECK)
    seat = rnd.active_seat.seat_num
    with pytest.raises(ValueError):
        rnd.discard(seat, [0, 1, 2, 3, 0])  # 5 indices > badugi limit of 4
