"""Punto Banco baccarat round: deal two cards each to Player + Banker,
apply the standard third-card table, settle.

The card valuation is:
  A=1, 2-9 face value, 10/J/Q/K=0
  Hand total = sum mod 10 (so 9 + 7 = 16 → 6)

Naturals: an 8 or 9 on the first two cards stops the deal — neither side
draws.

Player rule: Player draws on totals 0-5, stands on 6-7.

Banker rule (only relevant when Player stood, or a more complex table
when Player drew):
  Banker stands on 7. On 0-2 always draws.
  Otherwise depends on Player's third card (the standard table). The
  table is a closed-form rule — implemented below in `_banker_should_draw`.

Reference: Wizard of Odds Baccarat strategy chart.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Literal, Optional

from ..engine.cards import Card, RANKS, Suit


# ---- card valuation ---------------------------------------------------

def rank_value(rank: str) -> int:
    """Baccarat card value: A=1, 2-9 face, 10/J/Q/K=0."""
    if rank == "A":
        return 1
    if rank in ("T", "J", "Q", "K"):
        return 0
    return int(rank)


def hand_total(cards: Iterable[Card]) -> int:
    return sum(rank_value(c.rank) for c in cards) % 10


# ---- shoe -------------------------------------------------------------

class BaccaratShoe:
    """8-deck shoe by tradition; configurable. Reshuffles when penetration
    threshold is hit. Same seed-based determinism as the blackjack shoe."""

    def __init__(self, decks: int = 8, penetration: float = 0.85,
                 seed: Optional[int] = None):
        if decks < 1:
            raise ValueError("decks must be >= 1")
        if not 0.3 <= penetration <= 1.0:
            raise ValueError("penetration must be 0.3..1.0")
        self.decks = decks
        self.penetration = penetration
        self._rng = random.Random(seed)
        self._cards: list[Card] = []
        self._dealt = 0
        self._cut_index = 0
        self.shuffle()

    def shuffle(self) -> None:
        deck: list[Card] = []
        for _ in range(self.decks):
            for s in Suit:
                for r in RANKS:
                    deck.append(Card(r, s))
        self._rng.shuffle(deck)
        self._cards = deck
        self._dealt = 0
        self._cut_index = int(self.decks * 52 * self.penetration)

    @property
    def needs_reshuffle(self) -> bool:
        return self._dealt >= self._cut_index

    def next_card(self) -> Card:
        if not self._cards:
            self.shuffle()
        c = self._cards.pop(0)
        self._dealt += 1
        return c


# ---- rules + bet model -----------------------------------------------

@dataclass
class BaccaratRules:
    decks: int = 8
    penetration: float = 0.85
    banker_commission: float = 0.05  # 5% standard
    tie_pays: tuple[int, int] = (8, 1)
    pair_pays: tuple[int, int] = (11, 1)
    min_bet: int = 1
    max_bet: int = 500

    def to_dict(self) -> dict:
        return {
            "decks": self.decks,
            "penetration": self.penetration,
            "banker_commission": self.banker_commission,
            "tie_pays": list(self.tie_pays),
            "pair_pays": list(self.pair_pays),
            "min_bet": self.min_bet,
            "max_bet": self.max_bet,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BaccaratRules":
        return cls(
            decks=int(d.get("decks", 8)),
            penetration=float(d.get("penetration", 0.85)),
            banker_commission=float(d.get("banker_commission", 0.05)),
            tie_pays=tuple(d.get("tie_pays", (8, 1))),
            pair_pays=tuple(d.get("pair_pays", (11, 1))),
            min_bet=int(d.get("min_bet", 1)),
            max_bet=int(d.get("max_bet", 500)),
        )


class BetType(str, Enum):
    PLAYER = "player"
    BANKER = "banker"
    TIE = "tie"
    PLAYER_PAIR = "player_pair"
    BANKER_PAIR = "banker_pair"


@dataclass
class Bet:
    bet_type: BetType
    stake: int

    def to_dict(self) -> dict:
        return {"bet_type": self.bet_type.value, "stake": self.stake}

    @classmethod
    def from_dict(cls, d: dict) -> "Bet":
        return cls(bet_type=BetType(d["bet_type"]), stake=int(d["stake"]))


# ---- round ------------------------------------------------------------

@dataclass
class BaccaratRound:
    player_cards: list[Card] = field(default_factory=list)
    banker_cards: list[Card] = field(default_factory=list)
    player_total: int = 0
    banker_total: int = 0
    outcome: Literal["player", "banker", "tie"] = "tie"
    natural: bool = False
    player_pair: bool = False
    banker_pair: bool = False

    def to_dict(self) -> dict:
        return {
            "player_cards": [c.to_dict() for c in self.player_cards],
            "banker_cards": [c.to_dict() for c in self.banker_cards],
            "player_total": self.player_total,
            "banker_total": self.banker_total,
            "outcome": self.outcome,
            "natural": self.natural,
            "player_pair": self.player_pair,
            "banker_pair": self.banker_pair,
        }


def _banker_should_draw(banker_total: int, player_third_value: Optional[int]) -> bool:
    """Standard banker draw table.

    If Player stood (no third card), banker draws on 0-5, stands on 6-7.
    If Player drew, banker's draw decision depends on player's third
    card according to the long table.
    """
    if player_third_value is None:
        return banker_total <= 5

    if banker_total <= 2:
        return True
    if banker_total == 3:
        return player_third_value != 8
    if banker_total == 4:
        return player_third_value in (2, 3, 4, 5, 6, 7)
    if banker_total == 5:
        return player_third_value in (4, 5, 6, 7)
    if banker_total == 6:
        return player_third_value in (6, 7)
    return False


def deal_round(shoe: BaccaratShoe) -> BaccaratRound:
    rnd = BaccaratRound()
    # Initial deal: alternating P, B, P, B.
    rnd.player_cards.append(shoe.next_card())
    rnd.banker_cards.append(shoe.next_card())
    rnd.player_cards.append(shoe.next_card())
    rnd.banker_cards.append(shoe.next_card())

    rnd.player_pair = rnd.player_cards[0].rank == rnd.player_cards[1].rank
    rnd.banker_pair = rnd.banker_cards[0].rank == rnd.banker_cards[1].rank

    p_total = hand_total(rnd.player_cards)
    b_total = hand_total(rnd.banker_cards)

    # Naturals: 8 or 9 on either side stops the deal.
    if p_total >= 8 or b_total >= 8:
        rnd.natural = True
    else:
        # Player draws on 0-5, stands on 6-7.
        player_third_value: Optional[int] = None
        if p_total <= 5:
            third = shoe.next_card()
            rnd.player_cards.append(third)
            player_third_value = rank_value(third.rank)
            p_total = hand_total(rnd.player_cards)

        if _banker_should_draw(b_total, player_third_value):
            rnd.banker_cards.append(shoe.next_card())
            b_total = hand_total(rnd.banker_cards)

    rnd.player_total = p_total
    rnd.banker_total = b_total
    if p_total > b_total:
        rnd.outcome = "player"
    elif b_total > p_total:
        rnd.outcome = "banker"
    else:
        rnd.outcome = "tie"
    return rnd


# ---- settlement -------------------------------------------------------

def _profit_player_bet(stake: int, outcome: str) -> int:
    if outcome == "player":
        return stake  # 1:1
    if outcome == "tie":
        return 0  # push on tie
    return -stake


def _profit_banker_bet(stake: int, outcome: str, commission: float) -> int:
    if outcome == "banker":
        # 1:1 minus commission, rounded down to int.
        gross = stake
        return gross - int(round(gross * commission))
    if outcome == "tie":
        return 0
    return -stake


def _profit_tie_bet(stake: int, outcome: str, payout: tuple[int, int]) -> int:
    if outcome == "tie":
        num, den = payout
        return stake * num // den
    return -stake


def _profit_pair_bet(stake: int, hit: bool, payout: tuple[int, int]) -> int:
    if hit:
        num, den = payout
        return stake * num // den
    return -stake


def settle_bets(rnd: BaccaratRound, bets: Iterable[Bet],
                rules: Optional[BaccaratRules] = None) -> list[int]:
    """Per-bet profit (positive = win, negative = lose, 0 = push).
    Tie pushes Player and Banker bets per Punto Banco; only the TIE
    bet wins on a tie."""
    rules = rules or BaccaratRules()
    out: list[int] = []
    for b in bets:
        if b.stake <= 0:
            out.append(0)
            continue
        if b.bet_type == BetType.PLAYER:
            out.append(_profit_player_bet(b.stake, rnd.outcome))
        elif b.bet_type == BetType.BANKER:
            out.append(_profit_banker_bet(b.stake, rnd.outcome, rules.banker_commission))
        elif b.bet_type == BetType.TIE:
            out.append(_profit_tie_bet(b.stake, rnd.outcome, rules.tie_pays))
        elif b.bet_type == BetType.PLAYER_PAIR:
            out.append(_profit_pair_bet(b.stake, rnd.player_pair, rules.pair_pays))
        elif b.bet_type == BetType.BANKER_PAIR:
            out.append(_profit_pair_bet(b.stake, rnd.banker_pair, rules.pair_pays))
        else:
            out.append(0)
    return out
