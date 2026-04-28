"""Card primitives + deck composition tests."""
from collections import Counter

from app.engine.cards import Suit
from app.poker.cards import (
    Card,
    Joker,
    is_joker,
    is_natural,
    parse_cards,
    poker_card_from_token,
    poker_card_to_token,
    stringify_cards,
)
from app.poker.deck import DeckSpec, PokerShoe, build_deck


def test_joker_token_round_trip():
    big = poker_card_from_token("JK")
    little = poker_card_from_token("jk")
    assert isinstance(big, Joker) and big.big
    assert isinstance(little, Joker) and not little.big
    assert poker_card_to_token(big) == "JK"
    assert poker_card_to_token(little) == "jk"


def test_standard_card_token_round_trip():
    c = poker_card_from_token("AS")
    assert isinstance(c, Card) and c.rank == "A" and c.suit == Suit.SPADES
    assert poker_card_to_token(c) == "AS"


def test_is_joker_helpers():
    assert is_joker(Joker(big=True))
    assert is_joker(Joker(big=False))
    assert not is_joker(poker_card_from_token("KH"))
    assert is_natural(poker_card_from_token("KH"))
    assert not is_natural(Joker())


def test_parse_and_stringify_round_trip():
    tokens = ["AS", "KH", "TC", "JK", "jk", "5D"]
    cards = parse_cards(tokens)
    assert stringify_cards(cards) == tokens


def test_deck_spec_validation():
    import pytest
    with pytest.raises(ValueError):
        DeckSpec(decks=0)
    with pytest.raises(ValueError):
        DeckSpec(jokers=3)


def test_deck_composition_52():
    spec = DeckSpec(decks=1, jokers=0)
    deck = build_deck(spec)
    assert len(deck) == 52
    assert spec.total_cards == 52


def test_deck_composition_53_with_one_joker():
    spec = DeckSpec(decks=1, jokers=1)
    deck = build_deck(spec)
    assert len(deck) == 53
    assert sum(1 for c in deck if isinstance(c, Joker)) == 1
    big = next(c for c in deck if isinstance(c, Joker))
    assert big.big


def test_deck_composition_54_two_jokers():
    spec = DeckSpec(decks=1, jokers=2)
    deck = build_deck(spec)
    assert len(deck) == 54
    jokers = [c for c in deck if isinstance(c, Joker)]
    assert len(jokers) == 2
    assert sum(1 for j in jokers if j.big) == 1
    assert sum(1 for j in jokers if not j.big) == 1


def test_two_decks_doubles_cards():
    spec = DeckSpec(decks=2, jokers=1)
    deck = build_deck(spec)
    assert len(deck) == 52 * 2 + 1


def test_shoe_deals_in_seed_order():
    a = PokerShoe(DeckSpec(jokers=1), seed=42)
    b = PokerShoe(DeckSpec(jokers=1), seed=42)
    assert a.deal(20) == b.deal(20)


def test_shoe_distribution_is_full_deck():
    shoe = PokerShoe(DeckSpec(decks=1, jokers=1), seed=7)
    counts = Counter(stringify_cards(shoe.deal(53)))
    # 52 standard cards + 1 joker, all distinct.
    assert len(counts) == 53
    assert counts["JK"] == 1


def test_shoe_reshuffles_when_drained():
    shoe = PokerShoe(DeckSpec(decks=1, jokers=0), seed=1)
    shoe.deal(52)
    assert shoe.cards_remaining == 0
    # Next deal forces a reshuffle.
    shoe.next_card()
    assert shoe.shuffles >= 2
