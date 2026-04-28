"""Punto Banco baccarat engine tests.

Covers:
  - Card valuation (10/J/Q/K=0; A=1; rest face)
  - Hand totals mod 10
  - Naturals halt the deal
  - Player + banker third-card draw rules
  - Pair side bets fire on first two cards only
  - Banker commission applied on banker wins
  - Empirical outcome distribution near published rates
    (Banker ≈ 45.86%, Player ≈ 44.62%, Tie ≈ 9.52%)
"""
from __future__ import annotations

from app.baccarat import (
    BaccaratRound,
    BaccaratRules,
    BaccaratShoe,
    Bet,
    BetType,
    deal_round,
    hand_total,
    rank_value,
    settle_bets,
)
from app.engine.cards import Card, Suit


def C(rank: str, suit: str = "S") -> Card:
    return Card(rank, Suit(suit))


class _RiggedShoe:
    def __init__(self, cards: list[Card]):
        self._cards = list(cards)

    def next_card(self) -> Card:
        return self._cards.pop(0)


# ---- valuation --------------------------------------------------------

def test_rank_values():
    assert rank_value("A") == 1
    for r in ("T", "J", "Q", "K"):
        assert rank_value(r) == 0
    for r in "23456789":
        assert rank_value(r) == int(r)


def test_hand_total_modulo_10():
    # 9 + 7 = 16 → 6
    assert hand_total([C("9"), C("7")]) == 6
    # K + 5 = 5
    assert hand_total([C("K"), C("5")]) == 5
    # 4 + 4 + 4 = 12 → 2
    assert hand_total([C("4"), C("4"), C("4")]) == 2


# ---- deal rules -------------------------------------------------------

def test_natural_8_stops_the_deal():
    """Player gets 6+2=8 (natural). Neither side draws."""
    cards = [C("6"), C("3"),  # P1, B1
             C("2"), C("4")]  # P2, B2 — player has 8 (natural)
    rnd = deal_round(_RiggedShoe(cards))
    assert rnd.natural is True
    assert len(rnd.player_cards) == 2
    assert len(rnd.banker_cards) == 2
    assert rnd.player_total == 8
    assert rnd.banker_total == 7
    assert rnd.outcome == "player"


def test_natural_9_beats_natural_8():
    cards = [C("9"), C("8"),
             C("T"), C("T")]  # Player 9, Banker 8 — player wins
    rnd = deal_round(_RiggedShoe(cards))
    assert rnd.natural is True
    assert rnd.outcome == "player"


def test_player_draws_on_5_or_below_stands_on_6():
    # Player 1+4=5 → must draw. Banker 7 → stands.
    cards = [C("A"), C("3"),  # P1=1, B1=3
             C("4"), C("4"),  # P2=4 → P total 5; B2=4 → B total 7
             C("9")]          # Player's 3rd: 9, P total = (5+9)%10 = 4
    rnd = deal_round(_RiggedShoe(cards))
    assert len(rnd.player_cards) == 3
    assert len(rnd.banker_cards) == 2
    assert rnd.player_total == 4
    assert rnd.banker_total == 7
    assert rnd.outcome == "banker"


def test_player_stands_on_6():
    # P 4+2=6, B 3+3=6 — both stand on 6. Tie.
    cards = [C("4"), C("3"), C("2"), C("3")]
    rnd = deal_round(_RiggedShoe(cards))
    assert len(rnd.player_cards) == 2
    assert len(rnd.banker_cards) == 2
    assert rnd.outcome == "tie"


def test_banker_draws_on_3_when_player_third_not_8():
    """Banker has 3, player drew a 5 (so banker draws per the table).
    P initial 0, B initial 3, P third = 5 → P total = 5,
    Banker total 3, P third 5 ∈ {0..7,9}-{8} → banker draws.
    Banker draws e.g. a 9 → B total = (3+9)%10 = 2. Player wins.
    """
    cards = [
        C("T"), C("3"),  # P1=0, B1=3
        C("T"), C("T"),  # P2=0, B2=0 → P total 0, B total 3
        C("5"),          # P third = 5 → P total 5
        C("9"),          # B third = 9 → B total 2
    ]
    rnd = deal_round(_RiggedShoe(cards))
    assert len(rnd.banker_cards) == 3
    assert rnd.banker_total == 2
    assert rnd.player_total == 5


def test_banker_stands_on_3_when_player_third_is_8():
    cards = [
        C("T"), C("3"),
        C("T"), C("T"),  # P 0, B 3
        C("8"),          # Player draws 8 → P total 8 ... wait, 0+8=8 not natural since drawn third
    ]
    rnd = deal_round(_RiggedShoe(cards))
    # Banker on 3 stands when player's third is 8.
    assert len(rnd.banker_cards) == 2
    assert rnd.banker_total == 3
    assert rnd.player_total == 8


def test_pair_side_bets_only_fire_on_first_two_cards():
    cards = [
        C("8"), C("3"),  # P1=8, B1=3
        C("8"), C("4"),  # P2=8 → player pair! B2=4 → no pair
        # Player has natural 16→6 wait, 8+8=16%10=6, so player would draw...
        # Actually wait: 8+8=16, total=6. Banker 3+4=7. Both stand on initial?
        # Banker stands on 7 always. Player on 6 stands.
    ]
    rnd = deal_round(_RiggedShoe(cards))
    assert rnd.player_pair is True
    assert rnd.banker_pair is False


def test_banker_pair_detected():
    cards = [
        C("9"), C("Q"),  # P=9, B=Q
        C("T"), C("Q"),  # P=T, B=Q → banker pair (Q+Q)
    ]
    rnd = deal_round(_RiggedShoe(cards))
    assert rnd.banker_pair is True
    assert rnd.player_pair is False


# ---- settlement -------------------------------------------------------

def test_player_bet_pays_1_to_1():
    rnd = BaccaratRound(
        player_cards=[C("9"), C("9")], banker_cards=[C("8"), C("8")],
        player_total=8, banker_total=6, outcome="player",
    )
    out = settle_bets(rnd, [Bet(BetType.PLAYER, 100)])
    assert out == [100]


def test_banker_bet_pays_with_commission():
    rnd = BaccaratRound(
        player_cards=[], banker_cards=[],
        player_total=4, banker_total=8, outcome="banker",
    )
    rules = BaccaratRules(banker_commission=0.05)
    out = settle_bets(rnd, [Bet(BetType.BANKER, 100)], rules)
    # 100 * 0.95 = 95.
    assert out == [95]


def test_tie_pushes_player_and_banker_bets():
    rnd = BaccaratRound(player_total=5, banker_total=5, outcome="tie")
    out = settle_bets(rnd, [
        Bet(BetType.PLAYER, 50),
        Bet(BetType.BANKER, 50),
        Bet(BetType.TIE, 10),
    ])
    # Player + Banker push (0); Tie pays 8:1 = 80.
    assert out == [0, 0, 80]


def test_pair_bet_pays_11_to_1():
    rnd = BaccaratRound(player_pair=True)
    out = settle_bets(rnd, [Bet(BetType.PLAYER_PAIR, 10)])
    assert out == [110]


def test_pair_bet_loses_when_no_pair():
    rnd = BaccaratRound(player_pair=False)
    out = settle_bets(rnd, [Bet(BetType.PLAYER_PAIR, 10)])
    assert out == [-10]


# ---- distribution -----------------------------------------------------

def test_outcome_distribution_close_to_published():
    """Banker wins ≈ 45.86%, Player ≈ 44.62%, Tie ≈ 9.52% (Wizard of Odds).
    Run 5000 hands; tolerance 2%."""
    shoe = BaccaratShoe(decks=8, seed=0xCAFE)
    counts = {"player": 0, "banker": 0, "tie": 0}
    for _ in range(5000):
        if shoe.needs_reshuffle:
            shoe.shuffle()
        rnd = deal_round(shoe)
        counts[rnd.outcome] += 1
    p = counts["player"] / 5000
    b = counts["banker"] / 5000
    t = counts["tie"] / 5000
    assert abs(p - 0.4462) < 0.02, f"player rate {p:.4f}"
    assert abs(b - 0.4586) < 0.02, f"banker rate {b:.4f}"
    assert abs(t - 0.0952) < 0.02, f"tie rate {t:.4f}"
