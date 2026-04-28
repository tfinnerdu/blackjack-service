"""Equity calculator tests."""
import json

import pytest

from app import create_app
from app.config import Config
from app.poker.cards import parse_cards
from app.poker.equity import EquityError, monte_carlo_equity
from app.poker.variants import all_variants


def H(*tokens):
    return parse_cards(tokens)


def _holdem():
    return next(v for v in all_variants() if v.name == "Texas Hold'em")


def _omaha():
    return next(v for v in all_variants() if v.name == "Omaha")


# ---- Hold'em -----------------------------------------------------------

def test_aa_vs_one_random_opponent_is_overwhelming_favorite():
    """Pocket aces pre-flop vs one random opponent. AA wins ~85% pre-flop."""
    result = monte_carlo_equity(
        _holdem(), H("AS", "AH"), [],
        opponents=1, iterations=500, seed=42,
    )
    assert result["win_pct"] > 75  # let randomness wiggle a bit
    assert result["wins"] + result["ties"] + result["losses"] == 500


def test_quads_on_flop_beats_everything():
    """Hero has AS-AH; flop AC-AD-3C. Quad aces — hero is essentially
    unbeatable to the river."""
    result = monte_carlo_equity(
        _holdem(), H("AS", "AH"), H("AC", "AD", "3C"),
        opponents=2, iterations=300, seed=1,
    )
    assert result["win_pct"] > 95


def test_72o_vs_aa_is_underdog():
    """7-2 offsuit vs an opponent: hero loses most of the time."""
    result = monte_carlo_equity(
        _holdem(), H("7C", "2D"), [],
        opponents=1, iterations=400, seed=7,
    )
    assert result["loss_pct"] > result["win_pct"]


def test_seed_makes_results_deterministic():
    a = monte_carlo_equity(_holdem(), H("AS", "AH"), [],
                           opponents=1, iterations=200, seed=99)
    b = monte_carlo_equity(_holdem(), H("AS", "AH"), [],
                           opponents=1, iterations=200, seed=99)
    assert a["wins"] == b["wins"]
    assert a["ties"] == b["ties"]


# ---- Omaha -------------------------------------------------------------

def test_omaha_aaaa_double_suited_runs():
    """Sanity: an Omaha sim returns a valid distribution."""
    result = monte_carlo_equity(
        _omaha(),
        H("AS", "AH", "KS", "KH"),
        [],
        opponents=2, iterations=200, seed=11,
    )
    assert 0 <= result["win_pct"] <= 100
    assert result["equity_pct"] >= 30  # premium hand even with 2 villains


# ---- guard rails -------------------------------------------------------

def test_rejects_stud_variant():
    stud = next(v for v in all_variants() if v.name == "7-Card Stud")
    with pytest.raises(EquityError):
        monte_carlo_equity(stud, H("AS", "AH"), [], opponents=1, iterations=100)


def test_runs_for_wild_variant():
    """The 53-card joker variant runs through; result tuple sums correctly."""
    joker_variant = next(v for v in all_variants() if "53-card" in v.name)
    result = monte_carlo_equity(
        joker_variant, H("AS", "AH"), [],
        opponents=1, iterations=100, seed=7,
    )
    assert result["wins"] + result["ties"] + result["losses"] == 100
    assert 0 <= result["win_pct"] <= 100


def test_wild_variant_default_iterations_drops_to_500():
    """When iterations isn't passed, wild variants use a smaller default."""
    joker_variant = next(v for v in all_variants() if "53-card" in v.name)
    result = monte_carlo_equity(
        joker_variant, H("AS", "AH"), [], opponents=1, seed=7,
    )
    assert result["iterations"] == 500


def test_non_wild_variant_default_iterations_is_2000():
    result = monte_carlo_equity(
        _holdem(), H("AS", "AH"), [], opponents=1, seed=7,
    )
    assert result["iterations"] == 2000


def test_rejects_wrong_hole_count_for_omaha():
    with pytest.raises(EquityError):
        monte_carlo_equity(_omaha(), H("AS", "AH"), [],
                           opponents=1, iterations=100)


def test_rejects_too_many_iterations():
    with pytest.raises(EquityError):
        monte_carlo_equity(_holdem(), H("AS", "AH"), [],
                           opponents=1, iterations=999_999)


# ---- API endpoint ------------------------------------------------------

class _TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test"


def test_equity_endpoint_returns_json():
    client = create_app(_TestConfig()).test_client()
    r = client.post(
        "/api/v1/poker/equity",
        data=json.dumps({
            "variant": "Texas Hold'em",
            "hole": ["AS", "AH"],
            "board": [],
            "opponents": 1,
            "iterations": 200,
            "seed": 1,
        }),
        content_type="application/json",
    )
    assert r.status_code == 200
    data = r.get_json()
    assert "win_pct" in data
    assert data["wins"] + data["ties"] + data["losses"] == 200


def test_equity_endpoint_400_on_unsupported_variant():
    client = create_app(_TestConfig()).test_client()
    r = client.post(
        "/api/v1/poker/equity",
        data=json.dumps({
            "variant": "7-Card Stud",
            "hole": ["AS", "AH"],
            "board": [],
            "opponents": 1, "iterations": 200,
        }),
        content_type="application/json",
    )
    assert r.status_code == 400
