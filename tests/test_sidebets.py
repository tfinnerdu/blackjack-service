from app.engine import sidebets as sb
from app.engine.cards import Card, Suit
from app.engine.rules import (
    BusterBlackjack,
    BustIt,
    LuckyLadies,
    MatchTheDealer,
    OverUnder13,
    PerfectPairs,
    RoyalMatch,
    TwentyOnePlusThree,
)


def C(rank: str, suit: str = "S") -> Card:
    return Card(rank, Suit(suit))


# ---- Perfect Pairs ------------------------------------------------------

def test_perfect_pairs_disabled_returns_zero():
    cfg = PerfectPairs(enabled=False)
    assert sb.evaluate_perfect_pairs(C("8", "S"), C("8", "S"), cfg, 5) == 0


def test_perfect_pair_same_suit():
    cfg = PerfectPairs(enabled=True, perfect=(25, 1))
    # 8S + 8S = perfect pair (same rank + same suit).
    assert sb.evaluate_perfect_pairs(C("8", "S"), C("8", "S"), cfg, 5) == 125


def test_colored_pair_same_color_diff_suit():
    cfg = PerfectPairs(enabled=True, colored=(12, 1))
    # 8S + 8C = both black, different suits.
    assert sb.evaluate_perfect_pairs(C("8", "S"), C("8", "C"), cfg, 5) == 60


def test_mixed_pair_diff_colors():
    cfg = PerfectPairs(enabled=True, mixed=(6, 1))
    # 8S (black) + 8H (red).
    assert sb.evaluate_perfect_pairs(C("8", "S"), C("8", "H"), cfg, 5) == 30


def test_no_pair_loses_stake():
    cfg = PerfectPairs(enabled=True)
    assert sb.evaluate_perfect_pairs(C("8", "S"), C("9", "S"), cfg, 5) == -5


# ---- 21+3 ---------------------------------------------------------------

def test_21_plus_3_suited_three_of_a_kind():
    cfg = TwentyOnePlusThree(enabled=True, suited_three_of_a_kind=(100, 1))
    # 7S + 7S + 7S — same rank + same suit.
    assert sb.evaluate_21_plus_3(C("7", "S"), C("7", "S"), C("7", "S"), cfg, 1) == 100


def test_21_plus_3_straight_flush():
    cfg = TwentyOnePlusThree(enabled=True, straight_flush=(40, 1))
    # 5H 6H 7H.
    assert sb.evaluate_21_plus_3(C("5", "H"), C("6", "H"), C("7", "H"), cfg, 1) == 40


def test_21_plus_3_three_of_a_kind():
    cfg = TwentyOnePlusThree(enabled=True, three_of_a_kind=(30, 1))
    # 9S 9H 9D.
    assert sb.evaluate_21_plus_3(C("9", "S"), C("9", "H"), C("9", "D"), cfg, 2) == 60


def test_21_plus_3_straight():
    cfg = TwentyOnePlusThree(enabled=True, straight=(10, 1))
    # 4S 5H 6D.
    assert sb.evaluate_21_plus_3(C("4", "S"), C("5", "H"), C("6", "D"), cfg, 1) == 10


def test_21_plus_3_qka_high_straight():
    cfg = TwentyOnePlusThree(enabled=True, straight=(10, 1))
    # Q K A is a straight (high A).
    assert sb.evaluate_21_plus_3(C("Q", "S"), C("K", "H"), C("A", "D"), cfg, 1) == 10


def test_21_plus_3_flush():
    cfg = TwentyOnePlusThree(enabled=True, flush=(5, 1))
    # All hearts, not consecutive, not same rank.
    assert sb.evaluate_21_plus_3(C("2", "H"), C("7", "H"), C("J", "H"), cfg, 1) == 5


def test_21_plus_3_loss():
    cfg = TwentyOnePlusThree(enabled=True)
    # No pattern: 2S 7H JD.
    assert sb.evaluate_21_plus_3(C("2", "S"), C("7", "H"), C("J", "D"), cfg, 5) == -5


# ---- Lucky Ladies -------------------------------------------------------

def test_lucky_ladies_qq_hearts_with_dealer_bj():
    cfg = LuckyLadies(enabled=True, queen_hearts_pair_with_dealer_bj=(1000, 1))
    assert sb.evaluate_lucky_ladies(
        C("Q", "H"), C("Q", "H"), cfg, 1, dealer_blackjack=True
    ) == 1000


def test_lucky_ladies_qq_hearts_alone():
    cfg = LuckyLadies(enabled=True, queen_hearts_pair=(200, 1))
    assert sb.evaluate_lucky_ladies(
        C("Q", "H"), C("Q", "H"), cfg, 1, dealer_blackjack=False
    ) == 200


def test_lucky_ladies_matched_20():
    cfg = LuckyLadies(enabled=True, matched_20=(25, 1))
    # KS + KS, total 20, same rank+suit.
    assert sb.evaluate_lucky_ladies(
        C("K", "S"), C("K", "S"), cfg, 2, dealer_blackjack=False
    ) == 50


def test_lucky_ladies_suited_20():
    cfg = LuckyLadies(enabled=True, suited_20=(10, 1))
    # KS + JS, total 20, suited but unmatched rank.
    assert sb.evaluate_lucky_ladies(
        C("K", "S"), C("J", "S"), cfg, 2, dealer_blackjack=False
    ) == 20


def test_lucky_ladies_any_20():
    cfg = LuckyLadies(enabled=True, any_20=(4, 1))
    # KS + JH = 20, off-suit.
    assert sb.evaluate_lucky_ladies(
        C("K", "S"), C("J", "H"), cfg, 5, dealer_blackjack=False
    ) == 20


def test_lucky_ladies_not_20():
    cfg = LuckyLadies(enabled=True)
    assert sb.evaluate_lucky_ladies(
        C("9", "S"), C("J", "H"), cfg, 5, dealer_blackjack=False
    ) == -5


# ---- Royal Match --------------------------------------------------------

def test_royal_match_kq_suited():
    cfg = RoyalMatch(enabled=True, royal_match=(25, 1))
    assert sb.evaluate_royal_match(C("K", "H"), C("Q", "H"), cfg, 4) == 100


def test_royal_match_suited_only():
    cfg = RoyalMatch(enabled=True, suited=(5, 2))
    # 5:2 on stake 4 → 4*5//2 = 10
    assert sb.evaluate_royal_match(C("5", "H"), C("9", "H"), cfg, 4) == 10


def test_royal_match_offsuit_loses():
    cfg = RoyalMatch(enabled=True)
    assert sb.evaluate_royal_match(C("K", "H"), C("Q", "S"), cfg, 4) == -4


# ---- Match the Dealer ---------------------------------------------------

def test_match_the_dealer_one_suited_one_unsuited():
    cfg = MatchTheDealer(enabled=True, suited_match=(11, 1), unsuited_match=(4, 1))
    # Dealer up is 7H. Player: 7H (suited match) + 7S (unsuited match) = 11 + 4 = 15
    assert sb.evaluate_match_the_dealer(
        C("7", "H"), C("7", "S"), C("7", "H"), cfg, 1
    ) == 15


def test_match_the_dealer_no_match_loses():
    cfg = MatchTheDealer(enabled=True)
    assert sb.evaluate_match_the_dealer(
        C("3", "S"), C("9", "C"), C("7", "H"), cfg, 5
    ) == -5


# ---- Over/Under 13 ------------------------------------------------------

def test_over_13_wins_when_total_over():
    cfg = OverUnder13(enabled=True, payout=(1, 1))
    assert sb.evaluate_over_under_13(C("T"), C("9"), cfg, 5, "over") == 5


def test_over_13_loses_when_total_under():
    cfg = OverUnder13(enabled=True)
    assert sb.evaluate_over_under_13(C("4"), C("5"), cfg, 5, "over") == -5


def test_exactly_13_loses():
    cfg = OverUnder13(enabled=True)
    assert sb.evaluate_over_under_13(C("8"), C("5"), cfg, 5, "over") == -5
    assert sb.evaluate_over_under_13(C("8"), C("5"), cfg, 5, "under") == -5


def test_aces_count_as_one_in_over_under():
    cfg = OverUnder13(enabled=True, payout=(1, 1))
    # A + J = 1 + 10 = 11, under 13.
    assert sb.evaluate_over_under_13(C("A"), C("J"), cfg, 5, "under") == 5


# ---- Bust It ------------------------------------------------------------

def test_bust_it_no_bust_loses():
    cfg = BustIt(enabled=True)
    # Final dealer hand totals 18 (no bust).
    assert sb.evaluate_bust_it([C("T"), C("8")], cfg, 5) == -5


def test_bust_it_bust_pays_per_card_count():
    cfg = BustIt(enabled=True, payouts=((1, 1), (2, 1), (4, 1)))
    # 4-card bust: T,5,4,K = 29. Index = 4-3 = 1 → (2,1) → 5*2=10.
    assert sb.evaluate_bust_it([C("T"), C("5"), C("4"), C("K")], cfg, 5) == 10


# ---- Buster Blackjack ---------------------------------------------------

def test_buster_blackjack_player_bj_multiplier():
    cfg = BusterBlackjack(enabled=True, payouts=((2, 1),), blackjack_multiplier=2)
    # 3-card bust = index 0, (2,1) on stake 5 = 10. Player BJ doubles to 20.
    assert sb.evaluate_buster_blackjack(
        [C("T"), C("5"), C("K")], cfg, 5, player_has_blackjack=True
    ) == 20


def test_buster_blackjack_no_bust_loses():
    cfg = BusterBlackjack(enabled=True)
    assert sb.evaluate_buster_blackjack(
        [C("T"), C("8")], cfg, 5, player_has_blackjack=False
    ) == -5
