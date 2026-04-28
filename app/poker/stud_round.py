"""7-Card Stud / Razz state machine.

Stud variants deal 2 down + 1 up initially, then 4 more streets with a
betting round between each (one up on 4th/5th/6th, one down on 7th).
Best 5 of 7 cards at showdown.

Variants supported:
- 7-Card Stud (hi only)
- Razz (lo only, A-5)
- 7-Card Stud Hi/Lo would be a small extension (split pot at showdown);
  not wired in v1.

Action ordering simplification (v1):
- Bring-in: skipped. First-to-act each street is the lowest active
  seat number with cards. Actual stud uses lowest up-card on 3rd
  (or highest in Razz) and highest hand-so-far thereafter; not modeled
  here. Documented for later.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .cards import PokerCard, poker_card_to_token
from .deck import PokerShoe
from .evaluator import HandRank
from .evaluator.high import best_high
from .evaluator.low import LowRank, LowRule, best_low
from .pot import BetAction, Player, Pot, legal_actions, min_raise_to
from .variants import HandRequirement, HiLoSplit, VariantSpec


class StudState(str, Enum):
    DEALING = "dealing"
    BETTING = "betting"
    DEALING_STREET = "dealing_street"  # transient — deal next street's cards
    SHOWDOWN = "showdown"
    COMPLETE = "complete"


@dataclass
class StudHandConfig:
    ante: int = 0          # not implemented v1; reserved
    small_bet: int = 5      # bring-in / lower limit (stud often uses limits)
    big_bet: int = 10       # upper limit
    dealer_seat: int = 1


@dataclass
class StudCardSlot:
    """A single card with its visibility flag (up = visible to opponents)."""
    card: PokerCard
    up: bool


@dataclass
class StudHandOutcome:
    seat_num: int
    profit: int
    final_hand_name: str
    final_cards: list[str]
    won: bool
    reason: str  # 'showdown' | 'fold_through' | 'folded'


@dataclass
class StudRoundResult:
    outcomes: list[StudHandOutcome] = field(default_factory=list)
    pot_total: int = 0
    side_pots: list[dict] = field(default_factory=list)
    winner_seats: list[int] = field(default_factory=list)


class StudRound:
    def __init__(
        self,
        variant: VariantSpec,
        players: list[Player],
        config: StudHandConfig,
        shoe: Optional[PokerShoe] = None,
        seed: Optional[int] = None,
    ):
        if not variant.deal.stud_streets:
            raise ValueError("StudRound requires variant.deal.stud_streets")
        if variant.deal.community_streets or variant.deal.draws:
            raise ValueError(
                "StudRound is for stud-only variants (no community / no draws)"
            )
        if len(players) < 2:
            raise ValueError("need at least 2 players")
        self.variant = variant
        self.players = players
        self.config = config
        self.shoe = shoe or PokerShoe(variant.deck, seed=seed)
        # Each player's hand is a list of (card, up?) slots so the UI
        # can render face-up vs face-down correctly.
        self.hands: dict[int, list[StudCardSlot]] = {p.seat_num: [] for p in players}
        self.pot = Pot()
        self.current_bet: int = 0
        self.last_raise: int = config.big_bet
        self.active_index: int = 0
        self.state: StudState = StudState.DEALING
        self.street_index: int = 0  # 0 = 3rd street (initial), 1 = 4th, etc.
        self.result: Optional[StudRoundResult] = None
        self._starting_stacks: dict[int, int] = {}

    # ---- helpers ---------------------------------------------------

    def _by_seat(self, seat_num: int) -> Player:
        return next(p for p in self.players if p.seat_num == seat_num)

    def _index_of(self, seat_num: int) -> int:
        return next(i for i, p in enumerate(self.players) if p.seat_num == seat_num)

    def _next_player_index(self, from_index: int) -> Optional[int]:
        n = len(self.players)
        for i in range(1, n + 1):
            cand = self.players[(from_index + i) % n]
            if cand.in_hand and not cand.all_in:
                return (from_index + i) % n
        return None

    def _first_active_index(self) -> Optional[int]:
        for i, p in enumerate(self.players):
            if p.in_hand and not p.all_in:
                return i
        return None

    # ---- start -----------------------------------------------------

    def start(self) -> None:
        if self.state != StudState.DEALING:
            raise RuntimeError("already started")
        for p in self.players:
            p.reset_for_new_hand()
        self._starting_stacks = {p.seat_num: p.stack for p in self.players}

        # Optional ante. For v1 we don't enforce; reserved.
        # Initial deal: 2 down + 1 up to each player (per the variant DSL
        # hole_cards=2, up_cards=1).
        for _ in range(self.variant.deal.hole_cards):
            for p in self.players:
                self.hands[p.seat_num].append(StudCardSlot(self.shoe.next_card(), up=False))
        for _ in range(self.variant.deal.up_cards):
            for p in self.players:
                self.hands[p.seat_num].append(StudCardSlot(self.shoe.next_card(), up=True))

        # Action begins at the first active seat (simplified bring-in;
        # see top-of-file note).
        first = self._first_active_index()
        if first is None:
            raise RuntimeError("no active players to start")
        self.active_index = first
        self.state = StudState.BETTING
        self.street_index = 0

    # ---- betting ---------------------------------------------------

    @property
    def active_seat(self) -> Optional[Player]:
        if self.state != StudState.BETTING:
            return None
        return self.players[self.active_index]

    def legal_actions(self) -> list[BetAction]:
        if self.state != StudState.BETTING:
            return []
        p = self.active_seat
        if p is None:
            return []
        return legal_actions(p, self.current_bet, self.last_raise, self.config.small_bet)

    def amount_to_call(self) -> int:
        if self.state != StudState.BETTING:
            return 0
        p = self.active_seat
        if p is None:
            return 0
        return self.pot.amount_to_call(p, self.current_bet)

    def act(self, action: BetAction, amount: Optional[int] = None) -> None:
        if self.state != StudState.BETTING:
            raise RuntimeError(f"cannot act during state {self.state.value}")
        p = self.active_seat
        if p is None:
            raise RuntimeError("no active seat")
        legal = self.legal_actions()
        if action not in legal:
            raise ValueError(f"illegal action {action}; legal: {legal}")

        if action == BetAction.FOLD:
            p.folded = True
        elif action == BetAction.CHECK:
            pass
        elif action == BetAction.CALL:
            need = self.pot.amount_to_call(p, self.current_bet)
            self.pot.commit(p, min(need, p.stack))
        elif action == BetAction.BET:
            if amount is None:
                amount = self.config.small_bet
            self.pot.commit(p, amount)
            self.current_bet = p.committed_this_round
            self.last_raise = amount
            self._reopen_action(except_seat=p.seat_num)
        elif action == BetAction.RAISE:
            min_total = min_raise_to(self.current_bet, self.last_raise, self.config.small_bet)
            target = amount if amount is not None else min_total
            if target < min_total:
                raise ValueError(f"raise must be at least to {min_total}")
            need = target - p.committed_this_round
            if need > p.stack:
                raise ValueError("raise exceeds stack")
            self.pot.commit(p, need)
            self.last_raise = target - self.current_bet
            self.current_bet = target
            self._reopen_action(except_seat=p.seat_num)
        elif action == BetAction.ALL_IN:
            need = p.stack
            self.pot.commit(p, need)
            new_total = p.committed_this_round
            if new_total > self.current_bet:
                raise_size = new_total - self.current_bet
                if raise_size >= self.last_raise:
                    self.last_raise = raise_size
                    self._reopen_action(except_seat=p.seat_num)
                self.current_bet = new_total

        p.has_acted_this_round = True
        self._advance_betting()

    def _reopen_action(self, except_seat: int) -> None:
        for p in self.players:
            if p.seat_num != except_seat and p.in_hand and not p.all_in:
                p.has_acted_this_round = False

    def _everyone_else_folded(self) -> bool:
        return len([p for p in self.players if p.in_hand]) <= 1

    def _street_complete(self) -> bool:
        live = [p for p in self.players if p.in_hand and not p.all_in]
        if not live:
            return True
        for p in live:
            if not p.has_acted_this_round:
                return False
            if p.committed_this_round < self.current_bet:
                return False
        return True

    def _advance_betting(self) -> None:
        if self._everyone_else_folded():
            self._fold_through_settle()
            return
        if self._street_complete():
            self._next_street()
            return
        nxt = self._next_player_index(self.active_index)
        if nxt is None:
            self._next_street()
            return
        self.active_index = nxt

    def _next_street(self) -> None:
        for p in self.players:
            p.reset_for_new_round()
        self.pot.close_street()
        self.current_bet = 0
        self.last_raise = self.config.big_bet
        # Are there more stud streets to deal?
        if self.street_index < len(self.variant.deal.stud_streets):
            self._deal_next_street()
        else:
            self._showdown()

    def _deal_next_street(self) -> None:
        # Determine if the street is face-down (last street with stud_face_down_final).
        is_last = self.street_index == len(self.variant.deal.stud_streets) - 1
        face_down = is_last and self.variant.deal.stud_face_down_final
        n_cards = self.variant.deal.stud_streets[self.street_index]
        for _ in range(n_cards):
            for p in self.players:
                if not p.in_hand or p.all_in:
                    continue
                self.hands[p.seat_num].append(StudCardSlot(
                    self.shoe.next_card(), up=not face_down,
                ))
        self.street_index += 1
        # Action begins at first active seat for this street (simplified).
        first = self._first_active_index()
        if first is None:
            self._showdown()
            return
        self.active_index = first
        self.state = StudState.BETTING

    # ---- showdown --------------------------------------------------

    def _fold_through_settle(self) -> None:
        winner = next(p for p in self.players if p.in_hand)
        starting_stacks = self._starting_stacks
        winner.stack += self.pot.total
        outcomes = []
        for p in self.players:
            profit = p.stack - starting_stacks[p.seat_num]
            outcomes.append(StudHandOutcome(
                seat_num=p.seat_num,
                profit=profit,
                final_hand_name="winner (fold-through)" if p.seat_num == winner.seat_num else "—",
                final_cards=[],
                won=p.seat_num == winner.seat_num,
                reason="fold_through",
            ))
        self.result = StudRoundResult(
            outcomes=outcomes,
            pot_total=self.pot.total,
            side_pots=[],
            winner_seats=[winner.seat_num],
        )
        self.state = StudState.COMPLETE

    def _all_cards_for(self, seat: int) -> list[PokerCard]:
        return [slot.card for slot in self.hands[seat]]

    def _showdown(self) -> None:
        self.state = StudState.SHOWDOWN
        side_pots = self.pot.build_side_pots(self.players)
        live_seats = [p.seat_num for p in self.players if p.in_hand]
        starting_stacks = self._starting_stacks
        is_lo_only = self.variant.hi_lo == HiLoSplit.LO_ONLY
        winner_seat_set: set[int] = set()
        outcomes_by_seat: dict[int, StudHandOutcome] = {}

        if is_lo_only:
            self._settle_lo_only(side_pots, live_seats, winner_seat_set)
        else:
            self._settle_hi_only(side_pots, live_seats, winner_seat_set)

        for seat in live_seats:
            cards = self._all_cards_for(seat)
            stack_now = self._by_seat(seat).stack
            profit = stack_now - starting_stacks[seat]
            outcomes_by_seat[seat] = StudHandOutcome(
                seat_num=seat,
                profit=profit,
                final_hand_name=self._final_hand_label(seat, cards),
                final_cards=[poker_card_to_token(c) for c in cards],
                won=seat in winner_seat_set,
                reason="showdown",
            )
        for p in self.players:
            if p.seat_num in outcomes_by_seat:
                continue
            outcomes_by_seat[p.seat_num] = StudHandOutcome(
                seat_num=p.seat_num,
                profit=p.stack - starting_stacks[p.seat_num],
                final_hand_name="folded",
                final_cards=[],
                won=False,
                reason="folded",
            )

        self.result = StudRoundResult(
            outcomes=list(outcomes_by_seat.values()),
            pot_total=self.pot.total,
            side_pots=[{"amount": l.amount, "eligible": list(l.eligible_seats)}
                       for l in side_pots],
            winner_seats=sorted(winner_seat_set),
        )
        self.state = StudState.COMPLETE

    def _settle_hi_only(self, side_pots, live_seats, winner_seat_set) -> None:
        ranks: dict[int, HandRank] = {
            seat: best_high(self._all_cards_for(seat)) for seat in live_seats
        }
        # Always label the strongest hand(s) as winners even when the pot
        # is empty (e.g. no-ante test scenarios).
        if live_seats:
            top = max(ranks[s] for s in live_seats)
            winner_seat_set.update(s for s in live_seats if ranks[s] == top)
        for layer in side_pots:
            eligible = [s for s in layer.eligible_seats if s in live_seats]
            if not eligible:
                eligible = live_seats
            best_rank = max(ranks[s] for s in eligible)
            winners = [s for s in eligible if ranks[s] == best_rank]
            share = layer.amount // len(winners)
            remainder = layer.amount - share * len(winners)
            for i, s in enumerate(winners):
                bonus = 1 if i < remainder else 0
                self._by_seat(s).stack += share + bonus
                winner_seat_set.add(s)

    def _settle_lo_only(self, side_pots, live_seats, winner_seat_set) -> None:
        rule = self.variant.lo_rule or LowRule.ACE_TO_FIVE
        lows: dict[int, LowRank] = {
            seat: best_low(self._all_cards_for(seat), rule,
                           eight_or_better=self.variant.lo_eight_or_better)
            for seat in live_seats
        }
        # Default winner label even when the pot is empty.
        if live_seats:
            qualifying = [s for s in live_seats if lows[s].qualifies]
            pool = qualifying if qualifying else live_seats
            if pool:
                best_lo = min(lows[s].ranks for s in pool)
                winner_seat_set.update(s for s in pool if lows[s].ranks == best_lo)
        for layer in side_pots:
            eligible = [s for s in layer.eligible_seats if s in live_seats]
            if not eligible:
                eligible = live_seats
            qualifying = [s for s in eligible if lows[s].qualifies]
            pool = qualifying if qualifying else eligible
            if not pool:
                continue
            best_lo_ranks = min(lows[s].ranks for s in pool)
            winners = [s for s in pool if lows[s].ranks == best_lo_ranks]
            share = layer.amount // len(winners)
            remainder = layer.amount - share * len(winners)
            for i, s in enumerate(winners):
                bonus = 1 if i < remainder else 0
                self._by_seat(s).stack += share + bonus
                winner_seat_set.add(s)

    def _final_hand_label(self, seat: int, cards: list[PokerCard]) -> str:
        if self.variant.hi_lo == HiLoSplit.LO_ONLY:
            rule = self.variant.lo_rule or LowRule.ACE_TO_FIVE
            lo = best_low(cards, rule,
                          eight_or_better=self.variant.lo_eight_or_better)
            return lo.name or "no qualifying low"
        return best_high(cards).name()


__all__ = [
    "StudCardSlot",
    "StudHandConfig",
    "StudHandOutcome",
    "StudRound",
    "StudRoundResult",
    "StudState",
]
