"""Rules + side-bet payouts. Every casino knob lives here so a SettingsTemplate
is just a serialized Rules + SideBetConfig pair.

Payouts are stored as (numerator, denominator) tuples — i.e. "3:2" → (3, 2)
means a winning $2 bet pays $3 in addition to returning the stake.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Literal


class ShuffleMode(str, Enum):
    CASINO = "casino"   # cut-card shoe; reshuffle once penetration is reached
    CSM = "csm"         # continuous shuffler; every card returns to the shoe immediately
    HAND = "hand"       # human-style imperfect riffle/strip


class DoubleRule(str, Enum):
    ANY_TWO = "any2"
    NINE_TEN_ELEVEN = "9_10_11"
    TEN_ELEVEN = "10_11"


class SurrenderRule(str, Enum):
    NONE = "none"
    LATE = "late"      # surrender after dealer checks for blackjack
    EARLY = "early"    # surrender before dealer checks (player-favorable)


Payout = tuple[int, int]  # (numerator, denominator); 3:2 -> (3, 2)


@dataclass
class Rules:
    """Every player-visible rule knob.

    Defaults mirror "Vegas Strip 6-deck H17 6:5" since that's the most common
    rule set a casual player will encounter today. Templates override anything.
    """

    # Shoe
    decks: int = 6
    shuffle_mode: ShuffleMode = ShuffleMode.CASINO
    penetration: float = 0.75   # reshuffle when this fraction of the shoe is dealt

    # Table layout
    seats: int = 5              # 1..7 seats at the table
    player_seat: int = 3        # 1-indexed seat the human occupies

    # Dealer
    dealer_hits_soft_17: bool = True   # H17 vs S17
    dealer_peeks: bool = True          # peek for BJ on A or 10 up
    european_no_hole_card: bool = False  # ENHC: dealer takes hole only after players act

    # Payouts
    blackjack_payout: Payout = (6, 5)
    insurance_payout: Payout = (2, 1)

    # Doubling
    double_rule: DoubleRule = DoubleRule.ANY_TWO
    double_after_split: bool = True

    # Splitting
    max_splits: int = 3                # max additional splits → up to 4 hands total
    resplit_aces: bool = False
    hit_split_aces: bool = False

    # Surrender + insurance
    surrender: SurrenderRule = SurrenderRule.LATE
    insurance_offered: bool = True

    # Money
    starting_bankroll: int = 500
    min_bet: int = 5
    max_bet: int = 500
    bet_increment: int = 1

    def __post_init__(self) -> None:
        if not 1 <= self.decks <= 8:
            raise ValueError("decks must be 1..8")
        if not 1 <= self.seats <= 7:
            raise ValueError("seats must be 1..7")
        if not 1 <= self.player_seat <= self.seats:
            raise ValueError("player_seat must be within seats")
        if not 0.3 <= self.penetration <= 1.0:
            raise ValueError("penetration must be 0.3..1.0")
        if self.min_bet < 1 or self.max_bet < self.min_bet:
            raise ValueError("invalid bet limits")
        if self.bet_increment < 1:
            raise ValueError("bet_increment must be >= 1")

    def to_dict(self) -> dict:
        d = asdict(self)
        # asdict() already unwraps enums-as-strings via str-Enum mixin.
        return d


# ---- side bets ----------------------------------------------------------

@dataclass
class TwentyOnePlusThree:
    """Player two cards + dealer up. Standard ranking; payouts vary by house."""
    enabled: bool = False
    suited_three_of_a_kind: Payout = (100, 1)
    straight_flush: Payout = (40, 1)
    three_of_a_kind: Payout = (30, 1)
    straight: Payout = (10, 1)
    flush: Payout = (5, 1)


@dataclass
class PerfectPairs:
    """First two player cards form a pair."""
    enabled: bool = False
    perfect: Payout = (25, 1)   # same rank + same suit
    colored: Payout = (12, 1)   # same rank + same color, different suit
    mixed: Payout = (6, 1)      # same rank, different colors


@dataclass
class LuckyLadies:
    """Player's first two cards total 20."""
    enabled: bool = False
    queen_hearts_pair_with_dealer_bj: Payout = (1000, 1)
    queen_hearts_pair: Payout = (200, 1)
    matched_20: Payout = (25, 1)   # same rank and suit
    suited_20: Payout = (10, 1)
    any_20: Payout = (4, 1)


@dataclass
class RoyalMatch:
    """Player's first two cards same suit; royal = K+Q same suit."""
    enabled: bool = False
    royal_match: Payout = (25, 1)
    suited: Payout = (5, 2)


@dataclass
class MatchTheDealer:
    """Either player card matches dealer up-card."""
    enabled: bool = False
    suited_match: Payout = (11, 1)
    unsuited_match: Payout = (4, 1)


@dataclass
class OverUnder13:
    """Player's first two cards total over or under 13. Aces count as 1 here."""
    enabled: bool = False
    payout: Payout = (1, 1)
    # Player picks "over" or "under" at bet time; tracked at the seat level.


@dataclass
class BustIt:
    """Pays when the dealer busts; payout depends on number of cards in dealer's hand."""
    enabled: bool = False
    # Index 0 = bust on 3rd card, 1 = 4th card, ... up to 8th card.
    payouts: tuple[Payout, ...] = (
        (1, 1),     # 3 cards (rare; high pay typically reserved for suited 8-card busts)
        (2, 1),     # 4
        (4, 1),     # 5
        (15, 1),    # 6
        (50, 1),    # 7
        (200, 1),   # 8+
    )


@dataclass
class BusterBlackjack:
    """Player wins when dealer busts; payout scales with dealer card count.

    Bonus pays even more if the player has blackjack at the time of dealer bust.
    """
    enabled: bool = False
    payouts: tuple[Payout, ...] = (
        (2, 1),     # 3 cards
        (4, 1),     # 4
        (18, 1),    # 5
        (50, 1),    # 6
        (250, 1),   # 7
        (2000, 1),  # 8+
    )
    blackjack_multiplier: int = 2  # multiplied into the payout when player has BJ


@dataclass
class SideBets:
    twenty_one_plus_three: TwentyOnePlusThree = field(default_factory=TwentyOnePlusThree)
    perfect_pairs: PerfectPairs = field(default_factory=PerfectPairs)
    lucky_ladies: LuckyLadies = field(default_factory=LuckyLadies)
    royal_match: RoyalMatch = field(default_factory=RoyalMatch)
    match_the_dealer: MatchTheDealer = field(default_factory=MatchTheDealer)
    over_under_13: OverUnder13 = field(default_factory=OverUnder13)
    bust_it: BustIt = field(default_factory=BustIt)
    buster_blackjack: BusterBlackjack = field(default_factory=BusterBlackjack)

    def to_dict(self) -> dict:
        return asdict(self)


def payout_amount(stake: int, payout: Payout) -> int:
    """Profit on a winning side bet/main bet. Stake is returned separately by the caller."""
    num, den = payout
    return stake * num // den


__all__ = [
    "ShuffleMode",
    "DoubleRule",
    "SurrenderRule",
    "Payout",
    "Rules",
    "TwentyOnePlusThree",
    "PerfectPairs",
    "LuckyLadies",
    "RoyalMatch",
    "MatchTheDealer",
    "OverUnder13",
    "BustIt",
    "BusterBlackjack",
    "SideBets",
    "payout_amount",
]
