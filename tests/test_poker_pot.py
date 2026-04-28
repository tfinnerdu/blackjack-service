"""Pot + betting model tests."""
import pytest

from app.poker.pot import (
    BetAction,
    Player,
    Pot,
    legal_actions,
    min_raise_to,
)


def _player(seat: int, stack: int = 1000, name: str = "P") -> Player:
    return Player(seat_num=seat, name=name, stack=stack)


def test_commit_decrements_stack_and_increases_pot():
    p = _player(1, 1000)
    pot = Pot()
    pot.commit(p, 50)
    assert p.stack == 950
    assert p.committed_this_round == 50
    assert p.committed_total == 50
    assert pot.total == 50


def test_committing_full_stack_marks_all_in():
    p = _player(1, 200)
    pot = Pot()
    pot.commit(p, 200)
    assert p.all_in
    assert p.stack == 0


def test_overcommit_raises():
    p = _player(1, 100)
    pot = Pot()
    with pytest.raises(ValueError):
        pot.commit(p, 200)


def test_amount_to_call_subtracts_already_committed():
    p = _player(1, 1000)
    pot = Pot()
    pot.commit(p, 25)
    assert pot.amount_to_call(p, current_bet=25) == 0
    assert pot.amount_to_call(p, current_bet=50) == 25
    # Committed more than current bet (shouldn't normally happen): clamp to 0.
    assert pot.amount_to_call(p, current_bet=10) == 0


def test_close_street_clears_street_total():
    p = _player(1, 1000)
    pot = Pot()
    pot.commit(p, 100)
    pot.close_street()
    assert pot.current_street_total == 0
    assert pot.total == 100  # running total persists across streets


def test_legal_actions_with_no_bet_in_play():
    p = _player(1, 1000)
    actions = legal_actions(p, current_bet=0, last_raise=0, min_bet=10)
    assert BetAction.CHECK in actions
    assert BetAction.BET in actions
    assert BetAction.FOLD in actions
    assert BetAction.CALL not in actions


def test_legal_actions_with_bet_in_play():
    p = _player(1, 1000)
    actions = legal_actions(p, current_bet=50, last_raise=50, min_bet=10)
    assert BetAction.FOLD in actions
    assert BetAction.CALL in actions
    assert BetAction.RAISE in actions
    assert BetAction.CHECK not in actions


def test_legal_actions_short_stack_cannot_raise_when_lt_call():
    """If player can't afford even the call, CALL is still listed because
    they can call all-in for less; RAISE is not listed."""
    p = _player(1, 30)
    actions = legal_actions(p, current_bet=50, last_raise=50, min_bet=10)
    assert BetAction.CALL in actions
    assert BetAction.RAISE not in actions
    assert BetAction.ALL_IN in actions


def test_legal_actions_folded_or_all_in_returns_empty():
    folded = _player(1, 100)
    folded.folded = True
    assert legal_actions(folded, 0, 0, 10) == []
    allin = _player(2, 0)
    allin.all_in = True
    assert legal_actions(allin, 50, 50, 10) == []


def test_min_raise_to_uses_max_of_last_raise_and_min_bet():
    assert min_raise_to(current_bet=50, last_raise=20, min_bet=10) == 70
    assert min_raise_to(current_bet=50, last_raise=5, min_bet=10) == 60


# ---- side pots ---------------------------------------------------------

def test_side_pots_simple_three_handed_no_all_in():
    """All three commit equally; one main pot only."""
    p1 = _player(1, 1000); p2 = _player(2, 1000); p3 = _player(3, 1000)
    pot = Pot()
    for p in (p1, p2, p3):
        pot.commit(p, 100)
    layers = pot.build_side_pots([p1, p2, p3])
    assert len(layers) == 1
    assert layers[0].amount == 300
    assert set(layers[0].eligible_seats) == {1, 2, 3}


def test_side_pots_with_one_short_all_in():
    """p1 all-in for 50; p2 + p3 commit 200. Two layers:
    - main pot: 50 * 3 = 150 split among all three
    - side pot: (200-50) * 2 = 300 between p2 + p3 only
    """
    p1 = _player(1, 50); p2 = _player(2, 1000); p3 = _player(3, 1000)
    pot = Pot()
    pot.commit(p1, 50)
    pot.commit(p2, 200)
    pot.commit(p3, 200)
    layers = pot.build_side_pots([p1, p2, p3])
    assert [l.amount for l in layers] == [150, 300]
    assert set(layers[0].eligible_seats) == {1, 2, 3}
    assert set(layers[1].eligible_seats) == {2, 3}


def test_side_pots_excludes_folded_players_from_eligibility():
    """p3 folds. p1 commits 100, p2 commits 100, p3 had committed 30 then folded.
    Single layer of 230 split between p1 and p2 only."""
    p1 = _player(1, 1000); p2 = _player(2, 1000); p3 = _player(3, 1000)
    pot = Pot()
    pot.commit(p3, 30)
    p3.folded = True
    pot.commit(p1, 100)
    pot.commit(p2, 100)
    layers = pot.build_side_pots([p1, p2, p3])
    # Layered at p3's 30 cap and p1/p2's 100 cap.
    # First layer: 30*3 = 90, eligible {1,2} (p3 folded).
    # Second layer: (100-30)*2 = 140, eligible {1,2}.
    amounts = [l.amount for l in layers]
    assert sum(amounts) == 90 + 140
    for layer in layers:
        assert 3 not in layer.eligible_seats
