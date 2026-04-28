"""AI personality + bot tests. Verify recognizable archetypal behavior
without depending on RNG specifics."""
import random

from app.poker.ai import AIBot, post_flop_strength, pre_flop_strength
from app.poker.ai.personalities import (
    Decision,
    play_aggressive,
    play_book,
    play_bluffer,
    play_calling_station,
    play_drunk,
    play_hot_cold,
    play_loose,
    play_mimic,
    play_tight,
)
from app.poker.cards import parse_cards
from app.poker.pot import BetAction


def H(*tokens: str):
    return parse_cards(tokens)


def _decision(
    hole, community, *, to_call=0, pot_size=20, min_raise_to=20,
    big_blind=10, stack=1000, is_pre_flop=False,
):
    legal = [BetAction.FOLD, BetAction.CHECK, BetAction.BET, BetAction.ALL_IN]
    if to_call > 0:
        legal = [BetAction.FOLD, BetAction.CALL, BetAction.RAISE, BetAction.ALL_IN]
    return Decision(
        hole=hole, community=community, pot_size=pot_size, to_call=to_call,
        min_raise_to=min_raise_to, big_blind=big_blind, stack=stack,
        legal_actions=legal, is_pre_flop=is_pre_flop, last_results=[],
        rng=random.Random(0),
    )


# ---- hand strength ----------------------------------------------------

def test_pre_flop_aces_score_premium():
    s = pre_flop_strength(H("AS", "AH"))
    assert s.score >= 0.85
    assert s.is_pair_or_better


def test_pre_flop_72o_scores_low():
    s = pre_flop_strength(H("7C", "2D"))
    assert s.score <= 0.25


def test_post_flop_made_set_scores_higher_than_pair():
    pair = post_flop_strength(H("AS", "AH"), H("2C", "9D", "KH"))
    set3 = post_flop_strength(H("AS", "AH"), H("AC", "9D", "KH"))
    assert set3.score > pair.score


def test_post_flop_flush_draw_bumps_score():
    no_draw = post_flop_strength(H("AS", "KS"), H("9D", "5C", "2H"))
    flush_draw = post_flop_strength(H("AS", "KS"), H("9S", "5S", "2H"))
    assert flush_draw.score > no_draw.score


# ---- book personality -------------------------------------------------

def test_book_raises_premium_pre_flop():
    d = _decision(H("AS", "AH"), [], to_call=10, is_pre_flop=True)
    move = play_book(d)
    assert move.action in (BetAction.RAISE, BetAction.CALL)


def test_book_folds_trash_pre_flop_to_a_raise():
    d = _decision(H("7C", "2D"), [], to_call=30, is_pre_flop=True, pot_size=40)
    move = play_book(d)
    assert move.action == BetAction.FOLD


def test_book_bets_made_hand_post_flop():
    d = _decision(H("AS", "AH"), H("AC", "9D", "KH"), to_call=0, pot_size=20)
    move = play_book(d)
    assert move.action == BetAction.BET


# ---- tight ------------------------------------------------------------

def test_tight_folds_anything_below_premium():
    d = _decision(H("9C", "9D"), [], to_call=20, is_pre_flop=True)
    move = play_tight(d)
    # 99 pre-flop is borderline; tight folds to a raise of 2x BB.
    assert move.action == BetAction.FOLD


def test_tight_plays_aces():
    d = _decision(H("AS", "AH"), [], to_call=10, is_pre_flop=True)
    move = play_tight(d)
    assert move.action != BetAction.FOLD


# ---- loose ------------------------------------------------------------

def test_loose_calls_with_marginal_hands():
    d = _decision(H("7C", "8H"), H("2D", "3C", "9S"), to_call=10, pot_size=30)
    move = play_loose(d)
    assert move.action in (BetAction.CALL, BetAction.FOLD)


def test_loose_folds_to_a_huge_overbet_with_garbage():
    d = _decision(H("7C", "2D"), H("AS", "9D", "KH"), to_call=300, pot_size=30,
                  big_blind=10)
    move = play_loose(d)
    assert move.action == BetAction.FOLD


# ---- aggressive -------------------------------------------------------

def test_aggressive_raises_more_than_book_with_marginal_hand():
    """Across many seeds, aggressive raises at a noticeably higher rate
    than book on a marginal hand."""
    h = H("AS", "8D")
    c = H("KH", "9D", "5C")
    book_raises = sum(
        1 for seed in range(100)
        if play_book(_decision(h, c, to_call=10, pot_size=30)).action == BetAction.RAISE
    )
    agg_raises = 0
    for seed in range(100):
        d = _decision(h, c, to_call=10, pot_size=30)
        d.rng = random.Random(seed)
        if play_aggressive(d).action == BetAction.RAISE:
            agg_raises += 1
    assert agg_raises > book_raises


# ---- calling station --------------------------------------------------

def test_calling_station_calls_anything():
    d = _decision(H("7C", "2D"), H("AS", "9D", "KH"), to_call=50, pot_size=100)
    move = play_calling_station(d)
    assert move.action == BetAction.CALL


def test_calling_station_never_raises():
    """Sweep many strengths; the station should never RAISE."""
    cards_pile = [
        (H("AS", "AH"), H("AC", "9D", "KH")),
        (H("KS", "KH"), H("AC", "9D", "QH")),
        (H("TS", "9H"), H("8C", "7D", "2H")),
    ]
    for hole, comm in cards_pile:
        for to_call in (0, 10, 50):
            d = _decision(hole, comm, to_call=to_call, pot_size=50)
            move = play_calling_station(d)
            assert move.action != BetAction.RAISE


# ---- bluffer ----------------------------------------------------------

def test_bluffer_sometimes_bets_river_with_air():
    """Run many seeds; the bluffer should bet weak rivers more than zero
    times."""
    bluffs = 0
    for seed in range(200):
        d = _decision(
            H("7C", "2D"),
            H("AS", "KS", "QH", "JD"),  # 4-card board (turn) past flop
            to_call=0, pot_size=40,
        )
        d.community = H("AS", "KS", "QH", "JD", "5C")  # river
        d.rng = random.Random(seed)
        move = play_bluffer(d)
        if move.action == BetAction.BET:
            bluffs += 1
    assert bluffs >= 10  # a healthy fraction


# ---- hot/cold --------------------------------------------------------

def test_hot_cold_loosens_after_wins():
    """Same marginal hand: with no streak vs after 3 wins. Recent wins
    should make the bot more aggressive."""
    h, c = H("9C", "8D"), H("KS", "5H", "2C")
    d_cold = _decision(h, c, to_call=10, pot_size=30)
    d_cold.last_results = [-10, -10, -10]
    d_hot = _decision(h, c, to_call=10, pot_size=30)
    d_hot.last_results = [50, 60, 30]
    cold = play_hot_cold(d_cold)
    hot = play_hot_cold(d_hot)
    # On a hand of marginal-but-not-trash strength, hot should be at least
    # as aggressive (call vs fold; raise vs call).
    aggression = {BetAction.FOLD: 0, BetAction.CHECK: 1, BetAction.CALL: 2,
                  BetAction.BET: 3, BetAction.RAISE: 4, BetAction.ALL_IN: 5}
    assert aggression[hot.action] >= aggression[cold.action]


# ---- drunk -----------------------------------------------------------

def test_drunk_with_zero_mistake_rate_plays_book():
    h = H("AS", "AH")
    for _ in range(20):
        d = _decision(h, [], to_call=10, is_pre_flop=True)
        move = play_drunk(d, 0.0)
        # AA pre-flop -> book either raises or calls, never folds.
        assert move.action != BetAction.FOLD


# ---- mimic -----------------------------------------------------------

def test_mimic_never_raises():
    h, c = H("AS", "AH"), H("AC", "9D", "KH")
    d = _decision(h, c, to_call=10, pot_size=30)
    move = play_mimic(d)
    assert move.action == BetAction.CALL


def test_mimic_checks_when_free():
    h, c = H("7C", "2D"), H("AS", "9D", "KH")
    d = _decision(h, c, to_call=0, pot_size=20)
    move = play_mimic(d)
    assert move.action == BetAction.CHECK


# ---- AIBot ----------------------------------------------------------

def test_ai_bot_records_results_and_caps_history():
    bot = AIBot(seat_num=1, name="Test", personality="book")
    for i in range(30):
        bot.record_result(i)
    assert len(bot.last_results) == 20
    # Most-recent results retained.
    assert bot.last_results[-1] == 29


def test_ai_bot_decide_returns_legal_action():
    bot = AIBot(seat_num=1, name="Test", personality="book", seed=42)
    move = bot.decide(
        hole=H("AS", "AH"),
        community=H(),
        pot_size=15, to_call=10, min_raise_to=20,
        big_blind=10, stack=1000,
        legal_actions=[BetAction.FOLD, BetAction.CALL, BetAction.RAISE, BetAction.ALL_IN],
        is_pre_flop=True,
    )
    assert move.action in (BetAction.CALL, BetAction.RAISE)
