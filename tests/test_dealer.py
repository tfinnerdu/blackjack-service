from app.engine.cards import Card, Suit
from app.engine.dealer import dealer_should_hit, play_dealer
from app.engine.hand import Hand
from app.engine.rules import Rules


def C(rank: str, suit: str = "S") -> Card:
    return Card(rank, Suit(suit))


def H(*ranks: str) -> Hand:
    h = Hand()
    for r in ranks:
        h.add_card(C(r))
    return h


def test_dealer_hits_below_17():
    rules = Rules(dealer_hits_soft_17=True)
    assert dealer_should_hit(H("9", "5"), rules)
    assert dealer_should_hit(H("T", "6"), rules)


def test_dealer_stands_hard_17_plus():
    rules = Rules(dealer_hits_soft_17=True)
    assert not dealer_should_hit(H("T", "7"), rules)
    assert not dealer_should_hit(H("K", "8"), rules)


def test_h17_hits_soft_17():
    rules = Rules(dealer_hits_soft_17=True)
    assert dealer_should_hit(H("A", "6"), rules)


def test_s17_stands_soft_17():
    rules = Rules(dealer_hits_soft_17=False)
    assert not dealer_should_hit(H("A", "6"), rules)


def test_play_dealer_resolves_terminal_state():
    """Drive a real dealer turn against a fixed shoe so we don't depend on RNG."""
    from app.engine.shoe import Shoe

    rules = Rules(decks=1)
    shoe = Shoe(decks=1, seed=42)
    hand = H("9", "5")  # 14, must hit
    play_dealer(hand, shoe, rules)
    # Dealer must end >=17 (hard) or busted.
    if hand.is_bust:
        assert not hand.stood
    else:
        assert hand.total >= 17
        assert hand.stood
