"""Player/dealer hand. Tracks cards plus the per-hand state needed for
correct rule enforcement (was-doubled, was-split, came-from-split-aces, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .cards import Card, hand_total, is_blackjack
from .rules import DoubleRule, Rules


@dataclass
class Hand:
    cards: list[Card] = field(default_factory=list)
    bet: int = 0
    doubled: bool = False
    surrendered: bool = False
    is_split_hand: bool = False           # this hand was created by splitting
    from_split_aces: bool = False         # extra restrictions apply
    insurance_bet: int = 0                # 0 if not taken
    stood: bool = False
    finished: bool = False                # busted, doubled-and-drawn, surrendered, or stood

    def add_card(self, card: Card) -> None:
        self.cards.append(card)

    @property
    def total(self) -> int:
        t, _ = hand_total(self.cards)
        return t

    @property
    def is_soft(self) -> bool:
        _, soft = hand_total(self.cards)
        return soft

    @property
    def is_bust(self) -> bool:
        return self.total > 21

    @property
    def is_blackjack(self) -> bool:
        # Split hands cannot be a "natural" even if they total 21.
        return not self.is_split_hand and is_blackjack(self.cards)

    @property
    def is_pair(self) -> bool:
        # A pair for splitting purposes: same rank. House rules occasionally
        # allow splitting any 10-valued combo (KQ, JT) — we follow that
        # convention since most casinos do.
        if len(self.cards) != 2:
            return False
        a, b = self.cards
        if a.rank == b.rank:
            return True
        return a.value == 10 and b.value == 10

    def can_double(self, rules: Rules) -> bool:
        if len(self.cards) != 2 or self.doubled or self.finished:
            return False
        if self.is_split_hand and not rules.double_after_split:
            return False
        if self.from_split_aces:
            return False  # split-aces hands get exactly one card and stand
        total = self.total
        if rules.double_rule == DoubleRule.ANY_TWO:
            return True
        if rules.double_rule == DoubleRule.NINE_TEN_ELEVEN:
            return 9 <= total <= 11 and not self.is_soft
        if rules.double_rule == DoubleRule.TEN_ELEVEN:
            return 10 <= total <= 11 and not self.is_soft
        return False

    def can_split(self, rules: Rules, current_split_count: int) -> bool:
        if not self.is_pair or self.finished:
            return False
        if current_split_count >= rules.max_splits:
            return False
        if self.cards[0].rank == "A" and current_split_count > 0 and not rules.resplit_aces:
            return False
        return True

    def can_hit(self, rules: Rules) -> bool:
        if self.finished or self.is_bust or self.doubled or self.surrendered or self.stood:
            return False
        if self.from_split_aces and not rules.hit_split_aces:
            return False
        return True

    def can_surrender(self, rules: Rules) -> bool:
        from .rules import SurrenderRule
        if rules.surrender == SurrenderRule.NONE:
            return False
        if len(self.cards) != 2 or self.is_split_hand or self.finished:
            return False
        return True

    def to_dict(self) -> dict:
        return {
            "cards": [c.to_dict() for c in self.cards],
            "total": self.total,
            "soft": self.is_soft,
            "bust": self.is_bust,
            "blackjack": self.is_blackjack,
            "bet": self.bet,
            "doubled": self.doubled,
            "surrendered": self.surrendered,
            "from_split": self.is_split_hand,
            "from_split_aces": self.from_split_aces,
            "insurance_bet": self.insurance_bet,
            "stood": self.stood,
            "finished": self.finished,
        }
