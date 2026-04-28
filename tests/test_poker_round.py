"""Hold'em state machine tests. Drive scripted scenarios with rigged shoes
and assert state transitions, pot math, and showdown awards."""
import pytest

from app.poker.cards import parse_cards
from app.poker.deck import DeckSpec
from app.poker.pot import BetAction, Player
from app.poker.round import HandConfig, HoldemRound, RoundState
from app.poker.variants import all_variants


def _holdem():
    return next(v for v in all_variants() if v.name == "Texas Hold'em")


class RiggedShoe:
    """Reads from a fixed list of card tokens. Exhausts in order."""
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


def _two_handed(starting_stack=1000):
    return [
        Player(seat_num=1, name="Hero", stack=starting_stack, is_human=True),
        Player(seat_num=2, name="Villain", stack=starting_stack, is_human=False),
    ]


def _three_handed(starting_stack=1000):
    return [
        Player(seat_num=1, name="Hero", stack=starting_stack, is_human=True),
        Player(seat_num=2, name="V1", stack=starting_stack),
        Player(seat_num=3, name="V2", stack=starting_stack),
    ]


# ---- blinds + initial deal --------------------------------------------

def test_heads_up_dealer_posts_sb_other_posts_bb():
    players = _two_handed()
    rnd = HoldemRound(_holdem(), players, HandConfig(dealer_seat=1, small_blind=5, big_blind=10), seed=1)
    rnd.start()
    assert players[0].committed_this_round == 5
    assert players[1].committed_this_round == 10
    assert rnd.pot.total == 15
    assert rnd.state == RoundState.PRE_FLOP


def test_three_handed_dealer_plus_one_posts_sb():
    players = _three_handed()
    rnd = HoldemRound(_holdem(), players, HandConfig(dealer_seat=1, small_blind=5, big_blind=10), seed=1)
    rnd.start()
    # Dealer = 1, SB = 2, BB = 3.
    assert players[1].committed_this_round == 5
    assert players[2].committed_this_round == 10


def test_initial_hole_card_count_per_variant():
    # Hold'em deals 2 hole cards each.
    rnd = HoldemRound(_holdem(), _two_handed(), HandConfig(dealer_seat=1), seed=1)
    rnd.start()
    for seat in (1, 2):
        assert len(rnd.holes[seat]) == 2


# ---- fold-through scenario --------------------------------------------

def test_villain_folds_pre_flop_hero_wins_blinds():
    players = _two_handed()
    rnd = HoldemRound(_holdem(), players, HandConfig(dealer_seat=1), seed=1)
    rnd.start()
    # Heads-up pre-flop: SB (Hero, dealer) acts first.
    assert rnd.active_seat.seat_num == 1
    rnd.act(BetAction.CALL)  # Hero calls 5 to match the BB.
    assert rnd.active_seat.seat_num == 2
    rnd.act(BetAction.FOLD)
    assert rnd.state == RoundState.COMPLETE
    # Hero won the BB (10) — but they put in 10 themselves to match.
    # They lose 0 net; villain loses 10. Pot was 20; hero gets it all back.
    hero_outcome = next(o for o in rnd.result.outcomes if o.seat_num == 1)
    villain_outcome = next(o for o in rnd.result.outcomes if o.seat_num == 2)
    assert hero_outcome.won
    assert hero_outcome.profit == 10  # won the villain's BB
    assert villain_outcome.profit == -10


# ---- pre-flop -> flop transition --------------------------------------

def test_pre_flop_completes_when_all_active_match_bet():
    """Heads-up: Hero calls, Villain checks (BB option) -> flop."""
    players = _two_handed()
    rnd = HoldemRound(_holdem(), players, HandConfig(dealer_seat=1), seed=1)
    rnd.start()
    rnd.act(BetAction.CALL)   # Hero (SB) calls
    # Villain (BB) now has 'check' option since current_bet == their commit.
    assert BetAction.CHECK in rnd.legal_actions()
    rnd.act(BetAction.CHECK)
    assert rnd.state == RoundState.FLOP
    assert len(rnd.community) == 3


def test_raise_reopens_action_for_already_acted_players():
    """Three-handed: SB calls, BB raises -> SB must act again."""
    players = _three_handed()
    rnd = HoldemRound(_holdem(), players, HandConfig(dealer_seat=1), seed=2)
    rnd.start()
    # UTG (Hero seat 1, dealer button heads-up — but 3-handed, dealer=1, SB=2, BB=3).
    # First to act: seat 1 (UTG / dealer).
    assert rnd.active_seat.seat_num == 1
    rnd.act(BetAction.CALL)            # Hero calls 10
    assert rnd.active_seat.seat_num == 2
    rnd.act(BetAction.CALL)            # SB completes to 10
    # BB (seat 3) acts; they raise.
    assert rnd.active_seat.seat_num == 3
    rnd.act(BetAction.RAISE, amount=30)
    # Action returns to seat 1; they have to act again.
    assert rnd.active_seat.seat_num == 1


# ---- showdown + winner award ------------------------------------------

def test_showdown_awards_pot_to_best_hand():
    """Rig the shoe: Hero gets AS-AH, Villain gets KS-KH, board KH-2D-3C-4H-5S.
    Wait — KH already in Villain hand. Let me pick non-conflicting cards.
    Hero: AS-AH; Villain: KD-KC; board: 7H-2D-3C-4H-5S.
    Hero ends with pair of aces; Villain ends with pair of kings; Hero wins.
    """
    players = _two_handed()
    # Deal order: each player gets 1 card, then second card. Then burn + 3 flop, burn + turn, burn + river.
    # Players ordered by seat: 1 first, 2 second.
    # Round 1 hole cards: AS, KD. Round 2: AH, KC.
    # Burn before flop, then 3 flop cards. Burn before turn. Burn before river.
    tokens = [
        "AS", "KD",          # hole 1
        "AH", "KC",          # hole 2
        "2C",                # burn
        "7H", "2D", "3C",    # flop
        "4D",                # burn
        "4H",                # turn
        "5C",                # burn
        "5S",                # river
    ]
    rnd = HoldemRound(_holdem(), players, HandConfig(dealer_seat=1), shoe=RiggedShoe(tokens))
    rnd.start()
    # Heads-up pre-flop: SB (Hero) acts first.
    rnd.act(BetAction.CALL)
    rnd.act(BetAction.CHECK)
    # Flop, turn, river — both check.
    rnd.act(BetAction.CHECK)
    rnd.act(BetAction.CHECK)
    rnd.act(BetAction.CHECK)
    rnd.act(BetAction.CHECK)
    rnd.act(BetAction.CHECK)
    rnd.act(BetAction.CHECK)
    assert rnd.state == RoundState.COMPLETE
    assert rnd.result is not None
    # Hero's AA wins.
    assert 1 in rnd.result.winner_seats
    assert 2 not in rnd.result.winner_seats


def test_showdown_split_pot_on_tie():
    """Both hold AA in different suits and play out; community gives same
    five-card best to both -> split pot."""
    players = _two_handed()
    tokens = [
        "AS", "AC",          # P1 first, P2 first
        "AH", "AD",          # P1 second, P2 second
        "2C",                # burn
        "KH", "QH", "JH",    # flop (community ace... wait, can't repeat)
        # After hole cards we've dealt all 4 aces. Both players have AA;
        # the board KH-QH-JH is identical for them. Both make AA + best
        # 3 of board -> AA-K-Q-J. Tie.
        "TS",                # burn
        "TD",                # turn (changes nothing for ranks)
        "9S",                # burn
        "9C",                # river
    ]
    rnd = HoldemRound(_holdem(), players, HandConfig(dealer_seat=1), shoe=RiggedShoe(tokens))
    rnd.start()
    rnd.act(BetAction.CALL)
    rnd.act(BetAction.CHECK)
    rnd.act(BetAction.CHECK)
    rnd.act(BetAction.CHECK)
    rnd.act(BetAction.CHECK)
    rnd.act(BetAction.CHECK)
    rnd.act(BetAction.CHECK)
    rnd.act(BetAction.CHECK)
    assert rnd.state == RoundState.COMPLETE
    assert set(rnd.result.winner_seats) == {1, 2}


def test_holdem_rejects_non_supported_variant():
    """7-Stud should raise — its state machine isn't this one."""
    seven_stud = next(v for v in all_variants() if v.name == "7-Card Stud")
    with pytest.raises(ValueError):
        HoldemRound(seven_stud, _two_handed(), HandConfig(), seed=1)
