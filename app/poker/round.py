"""Hold'em-style round state machine.

Walks a hand through:
  PRE_FLOP -> FLOP -> TURN -> RIVER -> SHOWDOWN -> COMPLETE

Action-driven: callers (the API for the human, the AI module for bots)
push (player, action, amount) tuples in via `act(...)`. The round doesn't
decide who acts — it just tells you whose turn it is via `active_seat`.

Limited scope (v1):
  - Single-table no-limit Hold'em with one human + N AI seats
  - Blinds posted automatically at hand start
  - Side pots handled by the pot model at showdown
  - High-only winner takes the pot (hi/lo split lands when we wire
    Omaha Hi/Lo into the simulator — phase 7+)
  - Variant.deck/wilds honored: a 53-card joker game uses the joker'd
    deck and the SF-only evaluator at showdown
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .cards import PokerCard, poker_card_to_token
from .deck import PokerShoe
from .evaluator import HandRank, classify_high
from .evaluator.high import best_high
from .evaluator.wilds import WildMode, evaluate_with_wilds
from .pot import BetAction, Player, Pot, legal_actions, min_raise_to
from .variants import HandRequirement, VariantSpec, WildKind, WildRule


class RoundState(str, Enum):
    DEALING = "dealing"
    PRE_FLOP = "pre_flop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"
    SHOWDOWN = "showdown"
    COMPLETE = "complete"


@dataclass
class HandConfig:
    small_blind: int = 5
    big_blind: int = 10
    dealer_seat: int = 1   # button position; small blind is dealer+1, big is dealer+2


@dataclass
class HandOutcome:
    seat_num: int
    profit: int        # net change to stack from this hand
    final_hand_name: str
    final_cards: list[str]
    won: bool
    reason: str        # 'showdown' | 'fold_through'


@dataclass
class RoundResult:
    outcomes: list[HandOutcome] = field(default_factory=list)
    pot_total: int = 0
    side_pots: list[dict] = field(default_factory=list)
    community: list[str] = field(default_factory=list)
    winner_seats: list[int] = field(default_factory=list)


def _is_marked_wild(card: PokerCard, rules: list[WildRule]) -> bool:
    """Cheap variant-aware 'is this card wild' check."""
    from .companion import _matches  # reuse the matcher logic in companion
    return any(_matches(card, r) for r in rules)


def _showdown_rank(cards: list[PokerCard], variant: VariantSpec) -> HandRank:
    """Best high hand for this variant respecting wild rules + must-use."""
    wild_indices_in_hand = [
        i for i, c in enumerate(cards) if _is_marked_wild(c, variant.wilds)
    ]
    if not wild_indices_in_hand:
        return best_high(cards)

    # With wilds: try every 5-card combo, evaluate with wilds when needed.
    from itertools import combinations
    mode = variant.wilds[0].mode if variant.wilds else WildMode.FULLY_WILD
    best: Optional[HandRank] = None
    for combo in combinations(cards, 5):
        wild_in_combo = [i for i, c in enumerate(combo) if _is_marked_wild(c, variant.wilds)]
        if wild_in_combo:
            rank = evaluate_with_wilds(list(combo), wild_indices=wild_in_combo, mode=mode)
        else:
            rank = classify_high(list(combo))
        if best is None or rank > best:
            best = rank
    assert best is not None
    return best


class HoldemRound:
    """One hand of community-card poker (Hold'em or its variants).

    Construct with the variant + players (in seat order) + config + shoe.
    Call `start()` to post blinds + deal hole cards. Then drive `act(...)`
    until `state == COMPLETE`.
    """

    def __init__(
        self,
        variant: VariantSpec,
        players: list[Player],
        config: HandConfig,
        shoe: Optional[PokerShoe] = None,
        seed: Optional[int] = None,
    ):
        if variant.hand not in (
            HandRequirement.BEST_5_OF_ALL,
            HandRequirement.OMAHA_2_HOLE_3_BOARD,
        ):
            raise ValueError(
                f"HoldemRound supports best_5_of_all + omaha variants only "
                f"(got {variant.hand.value}); stud / draw need their own state machines"
            )
        # Community-card variants only. Stud + draw use different deal/state.
        if variant.deal.up_cards or variant.deal.stud_streets or variant.deal.draws:
            raise ValueError(
                "HoldemRound is for community-card games only; "
                "stud (up_cards / stud_streets) and draw (draws) variants "
                "need their own state machines"
            )
        if not variant.deal.community_streets:
            raise ValueError("HoldemRound requires community_streets in the deal scheme")
        if len(players) < 2:
            raise ValueError("need at least 2 players")
        self.variant = variant
        self.players = players
        self.config = config
        self.shoe = shoe or PokerShoe(variant.deck, seed=seed)
        self.state: RoundState = RoundState.DEALING
        self.holes: dict[int, list[PokerCard]] = {p.seat_num: [] for p in players}
        self.community: list[PokerCard] = []
        self.pot = Pot()
        self.current_bet: int = 0
        self.last_raise: int = config.big_blind
        self.active_index: int = 0
        self.result: Optional[RoundResult] = None
        # Players who've already had their turn settled this street
        # (called or raised-and-call-resolved); reset per street.
        self._action_started_this_street: bool = False
        # Stacks captured BEFORE blinds + commits so profit math is honest.
        self._starting_stacks: dict[int, int] = {}

    # ---- setup ---------------------------------------------------------

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
        if self.state != RoundState.DEALING:
            raise RuntimeError("already started")
        for p in self.players:
            p.reset_for_new_hand()
        # Snapshot now so profit = final_stack - starting_stack is accurate
        # even after the player has already posted blinds.
        self._starting_stacks = {p.seat_num: p.stack for p in self.players}

        # Post blinds. With heads-up, dealer posts SB; otherwise SB is dealer+1.
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

        # Deal hole cards (per the variant's deal scheme).
        n_hole = self.variant.deal.hole_cards
        for _ in range(n_hole):
            for p in self.players:
                self.holes[p.seat_num].append(self.shoe.next_card())

        # Action begins to the left of the BB pre-flop. Heads-up: SB acts
        # first pre-flop (dealer + SB).
        if len(self.players) == 2:
            first_to_act = sb_seat
        else:
            first_to_act = self._left_of(bb_seat)
        self.active_index = self._index_of(first_to_act)
        self.state = RoundState.PRE_FLOP
        self._action_started_this_street = False

    def _by_seat(self, seat_num: int) -> Player:
        return next(p for p in self.players if p.seat_num == seat_num)

    def _index_of(self, seat_num: int) -> int:
        return next(i for i, p in enumerate(self.players) if p.seat_num == seat_num)

    def _left_of(self, seat_num: int) -> int:
        idx = self._index_of(seat_num)
        return self.players[(idx + 1) % len(self.players)].seat_num

    # ---- action dispatch -----------------------------------------------

    @property
    def active_seat(self) -> Optional[Player]:
        if self.state in (RoundState.SHOWDOWN, RoundState.COMPLETE, RoundState.DEALING):
            return None
        return self.players[self.active_index]

    def legal_actions(self) -> list[BetAction]:
        p = self.active_seat
        if p is None:
            return []
        return legal_actions(p, self.current_bet, self.last_raise, self.config.big_blind)

    def amount_to_call(self) -> int:
        p = self.active_seat
        if p is None:
            return 0
        return self.pot.amount_to_call(p, self.current_bet)

    def act(self, action: BetAction, amount: Optional[int] = None) -> None:
        p = self.active_seat
        if p is None:
            raise RuntimeError(f"no active seat in state {self.state}")
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
            # A new bet reopens action — earlier players need to act again.
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
                # All-in raise — only reopens action if it's a full raise.
                raise_size = new_total - self.current_bet
                if raise_size >= self.last_raise:
                    self.last_raise = raise_size
                    self._reopen_action(except_seat=p.seat_num)
                self.current_bet = new_total
        else:
            raise ValueError(f"unknown action {action}")

        p.has_acted_this_round = True
        self._advance()

    def _reopen_action(self, except_seat: int) -> None:
        for p in self.players:
            if p.seat_num != except_seat and p.in_hand and not p.all_in:
                p.has_acted_this_round = False

    def _everyone_else_folded(self) -> bool:
        live = [p for p in self.players if p.in_hand]
        return len(live) <= 1

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

    def _advance(self) -> None:
        if self._everyone_else_folded():
            self._fold_through_settle()
            return

        if self._street_complete():
            self._next_street()
            return

        # Move action to the next live player.
        nxt = self._next_player_index(self.active_index)
        if nxt is None:
            # Everyone remaining is all-in; deal out the rest of the board
            # without further action.
            self._next_street()
            return
        self.active_index = nxt

    def _next_street(self) -> None:
        # Reset committed_this_round and has_acted; close the street in pot.
        for p in self.players:
            p.reset_for_new_round()
        self.pot.close_street()
        self.current_bet = 0
        self.last_raise = self.config.big_blind

        if self.state == RoundState.PRE_FLOP:
            self._burn_and_deal_community(3)
            self.state = RoundState.FLOP
        elif self.state == RoundState.FLOP:
            self._burn_and_deal_community(1)
            self.state = RoundState.TURN
        elif self.state == RoundState.TURN:
            self._burn_and_deal_community(1)
            self.state = RoundState.RIVER
        elif self.state == RoundState.RIVER:
            self._showdown()
            return

        # Action starts left of the dealer post-flop.
        seats = self._ordered_seats_from(self.config.dealer_seat)
        first = next(
            (s for s in seats[1:] if self._by_seat(s).in_hand and not self._by_seat(s).all_in),
            None,
        )
        if first is None:
            # All remaining players are all-in; just deal out and showdown.
            self._next_street()
            return
        self.active_index = self._index_of(first)

    def _burn_and_deal_community(self, n: int) -> None:
        # Burn one card; classic poker tradition.
        if self.shoe.cards_remaining > 0:
            self.shoe.next_card()
        for _ in range(n):
            self.community.append(self.shoe.next_card())

    # ---- settlement ---------------------------------------------------

    def _fold_through_settle(self) -> None:
        winner = next(p for p in self.players if p.in_hand)
        self._settle_pot_to(winner.seat_num, reason="fold_through")
        self.state = RoundState.COMPLETE

    def _showdown(self) -> None:
        self.state = RoundState.SHOWDOWN
        # Build side pots.
        side_pots = self.pot.build_side_pots(self.players)
        # Evaluate each remaining player's best hand.
        live_seats = [p.seat_num for p in self.players if p.in_hand]
        ranks: dict[int, HandRank] = {}
        for seat in live_seats:
            cards = list(self.holes[seat]) + list(self.community)
            if self.variant.hand == HandRequirement.OMAHA_2_HOLE_3_BOARD:
                ranks[seat] = best_high(
                    [], must_use=2,
                    hole=self.holes[seat],
                    board=self.community,
                )
            else:
                ranks[seat] = _showdown_rank(cards, self.variant)

        # Settle each side pot to the strongest live player among the eligible.
        starting_stacks = self._starting_stacks
        outcomes_by_seat: dict[int, HandOutcome] = {}
        winner_seat_set: set[int] = set()  # seats that received any pot share

        for layer in side_pots:
            eligible = [s for s in layer.eligible_seats if s in live_seats]
            if not eligible:
                # Shouldn't happen — committed-but-folded chips are still
                # counted in eligible-seats with non-folded players. Defensive:
                # award to the last live player.
                eligible = live_seats
            best_rank = max((ranks[s] for s in eligible))
            winners = [s for s in eligible if ranks[s] == best_rank]
            share = layer.amount // len(winners)
            remainder = layer.amount - share * len(winners)
            for i, s in enumerate(winners):
                bonus = 1 if i < remainder else 0
                self._by_seat(s).stack += share + bonus
                winner_seat_set.add(s)

        # Build outcome rows per player who saw the showdown. 'won' means
        # they received at least one share — split-pot ties register as wins
        # for both seats even when net profit is zero.
        for seat in live_seats:
            rank = ranks[seat]
            stack_now = self._by_seat(seat).stack
            profit = stack_now - starting_stacks[seat]
            outcomes_by_seat[seat] = HandOutcome(
                seat_num=seat,
                profit=profit,
                final_hand_name=rank.name(),
                final_cards=[poker_card_to_token(c) for c in rank.cards],
                won=seat in winner_seat_set,
                reason="showdown",
            )

        # Folded players also get an outcome row with zero or negative profit.
        for p in self.players:
            if p.seat_num in outcomes_by_seat:
                continue
            outcomes_by_seat[p.seat_num] = HandOutcome(
                seat_num=p.seat_num,
                profit=p.stack - starting_stacks[p.seat_num],
                final_hand_name="folded",
                final_cards=[],
                won=False,
                reason="folded",
            )

        self.result = RoundResult(
            outcomes=list(outcomes_by_seat.values()),
            pot_total=self.pot.total,
            side_pots=[{"amount": l.amount, "eligible": list(l.eligible_seats)} for l in side_pots],
            community=[poker_card_to_token(c) for c in self.community],
            winner_seats=sorted(winner_seat_set),
        )
        self.state = RoundState.COMPLETE

    def _settle_pot_to(self, seat_num: int, reason: str) -> None:
        """Award the entire pot to one seat (fold-through)."""
        winner = self._by_seat(seat_num)
        starting_stacks = self._starting_stacks
        # Refund: winner gets back what's in the pot. Everyone else lost
        # what they committed.
        winner.stack += self.pot.total
        # Profits = stack delta - any chips they put in the pot themselves.
        outcomes = []
        for p in self.players:
            profit = (p.stack - starting_stacks[p.seat_num])
            outcomes.append(HandOutcome(
                seat_num=p.seat_num,
                profit=profit,
                final_hand_name="—" if p.seat_num != seat_num else "winner (fold-through)",
                final_cards=[],
                won=p.seat_num == seat_num,
                reason=reason if p.seat_num != seat_num else "fold_through",
            ))
        self.result = RoundResult(
            outcomes=outcomes,
            pot_total=self.pot.total,
            side_pots=[],
            community=[poker_card_to_token(c) for c in self.community],
            winner_seats=[seat_num],
        )


__all__ = [
    "HandConfig",
    "HandOutcome",
    "HoldemRound",
    "RoundResult",
    "RoundState",
]
