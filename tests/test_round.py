"""Round/settlement tests. These use a 'rigged' shoe that returns a fixed
sequence so we can assert exact outcomes without RNG dependence.
"""
from app.engine.cards import Card, Suit
from app.engine.round import Round, Seat, SideBetWagers
from app.engine.rules import (
    DoubleRule,
    Rules,
    SideBets,
    SurrenderRule,
)


def C(rank: str, suit: str = "S") -> Card:
    return Card(rank, Suit(suit))


class RiggedShoe:
    """Pops cards from a pre-set list. Tests inject the exact sequence
    they want dealt — first card is dealt first, etc.

    The deal order in Round.deal is: P1 first card, dealer up, P1 second,
    dealer hole. Then any extra cards drawn during play.
    """

    def __init__(self, cards: list[Card]):
        self._cards = list(cards)
        self.shuffles = 1
        self.mode = "casino"

    def next_card(self) -> Card:
        return self._cards.pop(0)

    def deal(self, n: int) -> list[Card]:
        return [self.next_card() for _ in range(n)]

    @property
    def needs_reshuffle(self) -> bool:
        return False


def _new_round(cards: list[Card], rules: Rules | None = None, seats: int = 1) -> Round:
    rules = rules or Rules()
    rnd = Round(rules, SideBets(), RiggedShoe(cards))
    for i in range(seats):
        rnd.add_seat(Seat(seat_num=i + 1, main_bet=10, is_human=(i == 0)))
    return rnd


def test_natural_blackjack_pays_3_to_2():
    rules = Rules(blackjack_payout=(3, 2), insurance_offered=False, dealer_peeks=False)
    # Deal: player gets A, dealer gets 9, player gets K (BJ), dealer gets 8.
    # Dealer total = 17, stands. Player wins with natural.
    cards = [C("A"), C("9"), C("K"), C("8")]
    rnd = _new_round(cards, rules)
    rnd.deal()
    # No insurance offered (rules say so).
    assert rnd.state.value == "complete"
    outcomes = rnd.result.outcomes
    assert len(outcomes) == 1
    assert outcomes[0].result == "blackjack"
    assert outcomes[0].profit == 15  # 10 * 3/2 = 15


def test_blackjack_6_to_5():
    rules = Rules(blackjack_payout=(6, 5), insurance_offered=False, dealer_peeks=False)
    cards = [C("A"), C("9"), C("K"), C("8")]
    rnd = _new_round(cards, rules)
    rnd.deal()
    assert rnd.result.outcomes[0].result == "blackjack"
    assert rnd.result.outcomes[0].profit == 12  # 10 * 6/5 = 12


def test_player_bust_is_loss():
    rules = Rules(insurance_offered=False, dealer_peeks=False)
    # Player: T, T, T (busts at 30). Dealer: 9, 8 = 17 (stands).
    cards = [C("T"), C("9"), C("T"), C("8"), C("T")]
    rnd = _new_round(cards, rules)
    rnd.deal()
    rnd.act("hit")
    # Player busted; advance auto-occurred. Dealer plays automatically.
    assert rnd.state.value == "complete"
    out = rnd.result.outcomes[0]
    assert out.result == "bust"
    assert out.profit == -10


def test_dealer_bust_pays_player():
    rules = Rules(insurance_offered=False, dealer_peeks=False)
    # Player: T,8 = 18 (stands). Dealer: 6,T = 16 (must hit), then 9 -> 25 bust.
    cards = [C("T"), C("6"), C("8"), C("T"), C("9")]
    rnd = _new_round(cards, rules)
    rnd.deal()
    rnd.act("stand")
    assert rnd.state.value == "complete"
    assert rnd.result.dealer_hand.is_bust
    assert rnd.result.outcomes[0].result == "win"
    assert rnd.result.outcomes[0].profit == 10


def test_push_on_equal_total():
    rules = Rules(insurance_offered=False, dealer_peeks=False)
    # Player: T,8 = 18. Dealer: 9,9 = 18.
    cards = [C("T"), C("9"), C("8"), C("9")]
    rnd = _new_round(cards, rules)
    rnd.deal()
    rnd.act("stand")
    assert rnd.result.outcomes[0].result == "push"
    assert rnd.result.outcomes[0].profit == 0


def test_double_doubles_bet_and_takes_one_card():
    rules = Rules(
        insurance_offered=False, dealer_peeks=False, double_rule=DoubleRule.ANY_TWO
    )
    # Player: 5,6 = 11 → double. Dealer: 9, T = 19. Player gets T = 21.
    cards = [C("5"), C("9"), C("6"), C("T"), C("T")]
    rnd = _new_round(cards, rules)
    rnd.deal()
    assert "double" in rnd.legal_actions()
    rnd.act("double")
    assert rnd.state.value == "complete"
    out = rnd.result.outcomes[0]
    assert out.bet == 20  # doubled from 10
    assert out.result == "win"
    assert out.profit == 20


def test_late_surrender_loses_half():
    rules = Rules(
        insurance_offered=False,
        dealer_peeks=False,
        surrender=SurrenderRule.LATE,
    )
    # Player: T,6 = 16 vs dealer T-up. Surrender.
    cards = [C("T"), C("T"), C("6"), C("8")]
    rnd = _new_round(cards, rules)
    rnd.deal()
    assert "surrender" in rnd.legal_actions()
    rnd.act("surrender")
    out = rnd.result.outcomes[0]
    assert out.result == "surrender"
    assert out.profit == -5  # half of 10


def test_split_creates_two_hands_each_carrying_full_bet():
    rules = Rules(insurance_offered=False, dealer_peeks=False)
    # Player: 8,8. Dealer 6 up. Split.
    # After split: hand1 gets a 5 (8+5=13), hand2 gets a 4 (8+4=12).
    # Player stands both. Dealer: 6, T = 16, hits 7 -> 23 bust.
    cards = [
        C("8", "S"), C("6"),  # P1 first, dealer up
        C("8", "H"), C("T"),  # P1 second, dealer hole
        C("5"), C("4"),       # split draws (h1, h2)
        C("7"),               # dealer hit
    ]
    rnd = _new_round(cards, rules)
    rnd.deal()
    assert "split" in rnd.legal_actions()
    rnd.act("split")
    rnd.act("stand")  # hand 1
    rnd.act("stand")  # hand 2
    assert rnd.state.value == "complete"
    outs = rnd.result.outcomes
    assert len(outs) == 2
    assert outs[0].bet == 10 and outs[1].bet == 10
    assert outs[0].result == "win" and outs[1].result == "win"


def test_split_aces_one_card_each_no_blackjack_pay():
    rules = Rules(
        insurance_offered=False,
        dealer_peeks=False,
        hit_split_aces=False,
        blackjack_payout=(3, 2),
    )
    # Player A,A. Dealer: 9,8 = 17. Split aces; each gets one card: T and T.
    # Each split hand is 21 but NOT a natural — pays 1:1 not 3:2.
    cards = [
        C("A", "S"), C("9"),
        C("A", "H"), C("8"),
        C("T"), C("T"),
    ]
    rnd = _new_round(cards, rules)
    rnd.deal()
    assert "split" in rnd.legal_actions()
    rnd.act("split")
    # No further actions: split aces auto-stand.
    assert rnd.state.value == "complete"
    outs = rnd.result.outcomes
    assert len(outs) == 2
    for out in outs:
        assert out.result == "win"
        assert out.profit == 10  # 1:1, not 15


def test_insurance_pays_2_to_1_on_dealer_blackjack():
    rules = Rules(insurance_offered=True, dealer_peeks=True)
    # Player: T,9 = 19. Dealer: A,T = blackjack.
    cards = [C("T"), C("A"), C("9"), C("T")]
    rnd = _new_round(cards, rules)
    rnd.deal()
    # Insurance is offered.
    assert rnd.state.value == "insurance"
    rnd.offer_insurance(seat_num=1, accept=True, amount=5)
    rnd.close_insurance()
    # Dealer peek triggers immediate settle.
    assert rnd.state.value == "complete"
    out = rnd.result.outcomes[0]
    assert out.result == "loss"
    assert out.profit == -10
    assert rnd.result.insurance_outcomes[1] == 10  # 5 * 2/1
    assert rnd.result.dealer_blackjack


def test_insurance_loses_when_dealer_no_blackjack():
    rules = Rules(insurance_offered=True, dealer_peeks=True)
    # Player: T,T = 20. Dealer: A,9 = 20 (no BJ). Player stands; push.
    cards = [C("T"), C("A"), C("T"), C("9")]
    rnd = _new_round(cards, rules)
    rnd.deal()
    rnd.offer_insurance(seat_num=1, accept=True, amount=5)
    rnd.close_insurance()
    # Not BJ -> proceed to play.
    assert rnd.state.value == "playing"
    rnd.act("stand")
    assert rnd.state.value == "complete"
    assert rnd.result.outcomes[0].result == "push"
    assert rnd.result.insurance_outcomes[1] == -5
