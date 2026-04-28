from app.engine.cards import Card, Suit, hand_total, is_blackjack


def C(rank: str, suit: str = "S") -> Card:
    return Card(rank, Suit(suit))


def test_basic_totals():
    assert hand_total([C("5"), C("6")]) == (11, False)
    assert hand_total([C("T"), C("9")]) == (19, False)
    assert hand_total([C("K"), C("Q")]) == (20, False)


def test_soft_hand_demotion():
    # A,6 = soft 17.
    total, soft = hand_total([C("A"), C("6")])
    assert (total, soft) == (17, True)

    # A,6,T = hard 17 (ace forced to 1).
    total, soft = hand_total([C("A"), C("6"), C("T")])
    assert (total, soft) == (17, False)


def test_two_aces():
    # A,A = soft 12 (one ace becomes 11, other stays 1).
    total, soft = hand_total([C("A"), C("A")])
    assert (total, soft) == (12, True)
    # A,A,9 = 21 with one ace still at 11 -> soft 21.
    total, soft = hand_total([C("A"), C("A"), C("9")])
    assert (total, soft) == (21, True)
    # A,A,9,T = 21 hard (both aces forced to 1).
    total, soft = hand_total([C("A"), C("A"), C("9"), C("T")])
    assert (total, soft) == (21, False)


def test_blackjack_detection():
    assert is_blackjack([C("A"), C("K")])
    assert is_blackjack([C("J"), C("A", "H")])
    assert not is_blackjack([C("9"), C("Q")])  # 19 not 21
    # 21 from three cards is not a natural.
    assert not is_blackjack([C("7"), C("7"), C("7")])
