"""Draw-poker round state machine (5-Card Draw, 2-7 Triple Draw, Badugi).

State flow:
  DEALING        → deal hole cards to each seat
  BETTING_*      → standard fold/check/call/bet/raise round
  DRAWING_*      → each live seat (in order from button) picks 0..N cards
                    to discard; replacements drawn from the deck
  ... repeat per draw count
  SHOWDOWN       → evaluate per the variant's hand requirement
  COMPLETE

The number of betting rounds = len(variant.deal.draws) + 1.
The number of draw phases    = len(variant.deal.draws).

5-Card Draw: draws=[5], one betting round before, one after. Showdown
on best high.
2-7 Triple Draw: draws=[5, 5, 5], 4 betting rounds. Showdown on best
2-7 low.
Badugi: draws=[4, 4, 4], same shape, evaluator is BADUGI rule.

Action-driven like HoldemRound: callers push (action, amount) for
betting rounds and (discard_indices) for draw phases.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .cards import PokerCard, poker_card_to_token
from .deck import PokerShoe
from .evaluator import HandRank, classify_high
from .evaluator.high import best_high, rank_high
from .evaluator.low import LowRank, LowRule, best_low
from .pot import BetAction, Player, Pot, legal_actions, min_raise_to
from .variants import HandRequirement, HiLoSplit, VariantSpec


class DrawState(str, Enum):
    DEALING = "dealing"
    BETTING = "betting"   # round-index implicit in betting_round_index
    DRAWING = "drawing"
    SHOWDOWN = "showdown"
    COMPLETE = "complete"


@dataclass
class DrawHandConfig:
    small_blind: int = 5
    big_blind: int = 10
    dealer_seat: int = 1


@dataclass
class DrawHandOutcome:
    seat_num: int
    profit: int
    final_hand_name: str
    final_cards: list[str]
    won: bool
    reason: str  # 'showdown' | 'fold_through' | 'folded'


@dataclass
class DrawRoundResult:
    outcomes: list[DrawHandOutcome] = field(default_factory=list)
    pot_total: int = 0
    side_pots: list[dict] = field(default_factory=list)
    winner_seats: list[int] = field(default_factory=list)


class DrawRound:
    def __init__(
        self,
        variant: VariantSpec,
        players: list[Player],
        config: DrawHandConfig,
        shoe: Optional[PokerShoe] = None,
        seed: Optional[int] = None,
    ):
        if not variant.deal.draws:
            raise ValueError(
                "DrawRound requires variant.deal.draws (use HoldemRound for "
                "community-card variants)"
            )
        if variant.deal.community_streets or variant.deal.up_cards or variant.deal.stud_streets:
            raise ValueError(
                "DrawRound is for pure-draw games; community/stud variants "
                "have their own state machines"
            )
        if len(players) < 2:
            raise ValueError("need at least 2 players")
        self.variant = variant
        self.players = players
        self.config = config
        self.shoe = shoe or PokerShoe(variant.deck, seed=seed)
        self.state: DrawState = DrawState.DEALING
        self.holes: dict[int, list[PokerCard]] = {p.seat_num: [] for p in players}
        self.pot = Pot()
        self.current_bet: int = 0
        self.last_raise: int = config.big_blind
        self.active_index: int = 0
        # Track which betting round we're in (0-indexed). Total betting
        # rounds = len(draws) + 1.
        self.betting_round_index: int = 0
        self.draw_round_index: int = 0  # 0-indexed; how many draw phases done
        self.result: Optional[DrawRoundResult] = None
        self._starting_stacks: dict[int, int] = {}
        # Track which seats have completed their discard in the current
        # DRAWING phase.
        self._discard_done_seats: set[int] = set()

    # ---- setup -----------------------------------------------------

    def _by_seat(self, seat_num: int) -> Player:
        return next(p for p in self.players if p.seat_num == seat_num)

    def _index_of(self, seat_num: int) -> int:
        return next(i for i, p in enumerate(self.players) if p.seat_num == seat_num)

    def _ordered_seats_from(self, start_seat: int) -> list[int]:
        seats = [p.seat_num for p in self.players]
        idx = seats.index(start_seat)
        return seats[idx:] + seats[:idx]

    def _next_player_index(self, from_index: int) -> Optional[int]:
        n = len(self.players)
        for i in range(1, n + 1):
            cand = self.players[(from_index + i) % n]
            if cand.in_hand and not cand.all_in:
                return (from_index + i) % n
        return None

    def start(self) -> None:
        if self.state != DrawState.DEALING:
            raise RuntimeError("already started")
        for p in self.players:
            p.reset_for_new_hand()
        self._starting_stacks = {p.seat_num: p.stack for p in self.players}

        # Post blinds. Heads-up: dealer = SB; otherwise SB = dealer+1, BB = dealer+2.
        seats = self._ordered_seats_from(self.config.dealer_seat)
        if len(self.players) == 2:
            sb_seat, bb_seat = seats[0], seats[1]
        else:
            sb_seat, bb_seat = seats[1], seats[2]

        sb = self._by_seat(sb_seat)
        bb = self._by_seat(bb_seat)
        self.pot.commit(sb, min(self.config.small_blind, sb.stack))
        self.pot.commit(bb, min(self.config.big_blind, bb.stack))
        self.current_bet = self.config.big_blind
        self.last_raise = self.config.big_blind

        n_hole = self.variant.deal.hole_cards
        for _ in range(n_hole):
            for p in self.players:
                self.holes[p.seat_num].append(self.shoe.next_card())

        # First betting round: action begins to the left of the BB
        # (or with SB heads-up).
        if len(self.players) == 2:
            first_to_act = sb_seat
        else:
            first_to_act = self._left_of(bb_seat)
        self.active_index = self._index_of(first_to_act)
        self.state = DrawState.BETTING
        self.betting_round_index = 0

    def _left_of(self, seat_num: int) -> int:
        idx = self._index_of(seat_num)
        return self.players[(idx + 1) % len(self.players)].seat_num

    # ---- betting ---------------------------------------------------

    @property
    def active_seat(self) -> Optional[Player]:
        if self.state == DrawState.BETTING:
            return self.players[self.active_index]
        if self.state == DrawState.DRAWING:
            return self.players[self.active_index]
        return None

    def legal_actions(self) -> list[BetAction]:
        """Legal betting actions for the active seat (only valid during
        BETTING state). Empty list during DRAWING — caller should call
        discard() instead."""
        if self.state != DrawState.BETTING:
            return []
        p = self.active_seat
        if p is None:
            return []
        return legal_actions(p, self.current_bet, self.last_raise, self.config.big_blind)

    def amount_to_call(self) -> int:
        if self.state != DrawState.BETTING:
            return 0
        p = self.active_seat
        if p is None:
            return 0
        return self.pot.amount_to_call(p, self.current_bet)

    def act(self, action: BetAction, amount: Optional[int] = None) -> None:
        if self.state != DrawState.BETTING:
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
                amount = self.config.big_blind
            if amount < self.config.big_blind:
                raise ValueError(f"bet must be >= {self.config.big_blind}")
            if amount > p.stack:
                raise ValueError("bet exceeds stack")
            self.pot.commit(p, amount)
            self.current_bet = p.committed_this_round
            self.last_raise = amount
            self._reopen_action(except_seat=p.seat_num)
        elif action == BetAction.RAISE:
            min_total = min_raise_to(self.current_bet, self.last_raise, self.config.big_blind)
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
        else:
            raise ValueError(f"unknown action {action}")

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
            self._next_phase_after_betting()
            return

        nxt = self._next_player_index(self.active_index)
        if nxt is None:
            self._next_phase_after_betting()
            return
        self.active_index = nxt

    def _next_phase_after_betting(self) -> None:
        # Reset round-bound flags + close street.
        for p in self.players:
            p.reset_for_new_round()
        self.pot.close_street()
        self.current_bet = 0
        self.last_raise = self.config.big_blind

        # If we still have a draw phase to do, enter DRAWING. Else go to showdown.
        if self.draw_round_index < len(self.variant.deal.draws):
            self._enter_drawing_phase()
        else:
            self._showdown()

    # ---- drawing ---------------------------------------------------

    def _enter_drawing_phase(self) -> None:
        self.state = DrawState.DRAWING
        self._discard_done_seats = set()
        # First to act in a draw phase is the seat left of the dealer
        # (skipping folded / all-in seats).
        seats = self._ordered_seats_from(self.config.dealer_seat)
        first = next(
            (s for s in seats[1:] if self._by_seat(s).in_hand and not self._by_seat(s).all_in),
            None,
        )
        if first is None:
            # Everyone all-in / folded — skip drawing and go to next phase.
            self._finish_draw_phase()
            return
        self.active_index = self._index_of(first)

    def discard(self, seat_num: int, indices: list[int]) -> None:
        """Discard the given hole-card indices for `seat_num` and replace
        from the deck. Indices are 0-based against the seat's current
        hole list."""
        if self.state != DrawState.DRAWING:
            raise RuntimeError(f"cannot discard during state {self.state.value}")
        active = self.active_seat
        if active is None or active.seat_num != seat_num:
            raise RuntimeError(f"not seat {seat_num}'s turn to discard")
        if seat_num in self._discard_done_seats:
            raise RuntimeError(f"seat {seat_num} already discarded this phase")

        max_replace = self.variant.deal.draws[self.draw_round_index]
        if len(indices) > max_replace:
            raise ValueError(f"can't discard more than {max_replace}")
        hole = self.holes[seat_num]
        for i in indices:
            if not 0 <= i < len(hole):
                raise ValueError(f"invalid discard index {i}")

        # Replace chosen indices with fresh cards.
        new_hole = list(hole)
        for i in sorted(indices, reverse=True):
            new_hole.pop(i)
        for _ in range(len(indices)):
            new_hole.append(self.shoe.next_card())
        self.holes[seat_num] = new_hole

        self._discard_done_seats.add(seat_num)
        self._advance_drawing()

    def _advance_drawing(self) -> None:
        nxt = self._next_player_index(self.active_index)
        if nxt is None:
            self._finish_draw_phase()
            return
        # Walk forward until we hit a seat that hasn't discarded yet.
        seen = 0
        while True:
            cand = self.players[nxt]
            if cand.seat_num not in self._discard_done_seats and cand.in_hand and not cand.all_in:
                self.active_index = nxt
                return
            seen += 1
            if seen >= len(self.players):
                break
            nxt = (nxt + 1) % len(self.players)
        # No seat left to discard — done.
        self._finish_draw_phase()

    def _finish_draw_phase(self) -> None:
        self.draw_round_index += 1
        self.state = DrawState.BETTING
        self.betting_round_index += 1
        # New betting round: action begins to the left of the dealer.
        seats = self._ordered_seats_from(self.config.dealer_seat)
        first = next(
            (s for s in seats[1:] if self._by_seat(s).in_hand and not self._by_seat(s).all_in),
            None,
        )
        if first is None:
            self._next_phase_after_betting()
            return
        self.active_index = self._index_of(first)

    # ---- showdown --------------------------------------------------

    def _fold_through_settle(self) -> None:
        winner = next(p for p in self.players if p.in_hand)
        starting_stacks = self._starting_stacks
        winner.stack += self.pot.total
        outcomes = []
        for p in self.players:
            profit = p.stack - starting_stacks[p.seat_num]
            outcomes.append(DrawHandOutcome(
                seat_num=p.seat_num,
                profit=profit,
                final_hand_name="winner (fold-through)" if p.seat_num == winner.seat_num else "—",
                final_cards=[],
                won=p.seat_num == winner.seat_num,
                reason="fold_through",
            ))
        self.result = DrawRoundResult(
            outcomes=outcomes,
            pot_total=self.pot.total,
            side_pots=[],
            winner_seats=[winner.seat_num],
        )
        self.state = DrawState.COMPLETE

    def _showdown(self) -> None:
        self.state = DrawState.SHOWDOWN
        side_pots = self.pot.build_side_pots(self.players)
        live_seats = [p.seat_num for p in self.players if p.in_hand]
        starting_stacks = self._starting_stacks

        is_lo_only = self.variant.hi_lo == HiLoSplit.LO_ONLY
        winner_seat_set: set[int] = set()
        outcomes_by_seat: dict[int, DrawHandOutcome] = {}

        if is_lo_only:
            self._settle_lo_only(side_pots, live_seats, winner_seat_set)
        else:
            self._settle_hi_only(side_pots, live_seats, winner_seat_set)

        for seat in live_seats:
            stack_now = self._by_seat(seat).stack
            profit = stack_now - starting_stacks[seat]
            outcomes_by_seat[seat] = DrawHandOutcome(
                seat_num=seat,
                profit=profit,
                final_hand_name=self._final_hand_label(seat),
                final_cards=[poker_card_to_token(c) for c in self.holes[seat]],
                won=seat in winner_seat_set,
                reason="showdown",
            )
        for p in self.players:
            if p.seat_num in outcomes_by_seat:
                continue
            outcomes_by_seat[p.seat_num] = DrawHandOutcome(
                seat_num=p.seat_num,
                profit=p.stack - starting_stacks[p.seat_num],
                final_hand_name="folded",
                final_cards=[],
                won=False,
                reason="folded",
            )

        self.result = DrawRoundResult(
            outcomes=list(outcomes_by_seat.values()),
            pot_total=self.pot.total,
            side_pots=[{"amount": l.amount, "eligible": list(l.eligible_seats)}
                       for l in side_pots],
            winner_seats=sorted(winner_seat_set),
        )
        self.state = DrawState.COMPLETE

    def _settle_hi_only(self, side_pots, live_seats, winner_seat_set) -> None:
        ranks: dict[int, HandRank] = {}
        for seat in live_seats:
            cards = list(self.holes[seat])
            # 5-card draw uses exactly the 5 hole cards.
            if len(cards) == 5:
                ranks[seat] = classify_high(cards)
            else:
                ranks[seat] = best_high(cards)
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
        lows: dict[int, LowRank] = {}
        for seat in live_seats:
            lows[seat] = best_low(self.holes[seat], rule,
                                  eight_or_better=self.variant.lo_eight_or_better)
        # Filter to qualifying lows when 8-or-better; fall through to all
        # live seats when no qualifier applies (every player has SOME low).
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

    def _final_hand_label(self, seat: int) -> str:
        cards = self.holes[seat]
        if self.variant.hi_lo == HiLoSplit.LO_ONLY:
            rule = self.variant.lo_rule or LowRule.ACE_TO_FIVE
            lo = best_low(cards, rule,
                          eight_or_better=self.variant.lo_eight_or_better)
            return lo.name or "no qualifying low"
        if len(cards) == 5:
            return classify_high(cards).name()
        return best_high(cards).name()


__all__ = [
    "DrawHandConfig",
    "DrawHandOutcome",
    "DrawRound",
    "DrawRoundResult",
    "DrawState",
]
