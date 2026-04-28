"""Round orchestrator. State machine that walks a single round through:
betting -> deal -> insurance (optional) -> player actions -> dealer -> settle.

The engine is action-driven: callers (API for the human, AI module for bots)
push actions in via `act(...)`. The engine doesn't decide who acts — it just
exposes the active (seat, hand) pair via `active_seat` / `active_hand`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Optional

from . import sidebets as sb
from .cards import Card
from .dealer import dealer_has_blackjack_potential, play_dealer
from .hand import Hand
from .rules import (
    Payout,
    Rules,
    SideBets,
    SurrenderRule,
    payout_amount,
)


Action = Literal["hit", "stand", "double", "split", "surrender"]


class RoundState(str, Enum):
    BETTING = "betting"
    DEALING = "dealing"
    INSURANCE = "insurance"
    PLAYING = "playing"
    DEALER = "dealer"
    SETTLING = "settling"
    COMPLETE = "complete"


@dataclass
class SideBetWagers:
    """Per-seat side-bet stakes. Zero means not bet."""
    twenty_one_plus_three: int = 0
    perfect_pairs: int = 0
    lucky_ladies: int = 0
    royal_match: int = 0
    match_the_dealer: int = 0
    over_under_13: int = 0
    over_under_pick: Literal["over", "under"] = "over"
    bust_it: int = 0
    buster_blackjack: int = 0


@dataclass
class Seat:
    """One spot at the table. The human's seat just has is_human=True."""
    seat_num: int
    main_bet: int
    side_bets: SideBetWagers = field(default_factory=SideBetWagers)
    is_human: bool = False
    bankroll_before: int = 0  # informational; settlement totals are per-round
    hands: list[Hand] = field(default_factory=list)
    insurance_decided: bool = False
    side_bet_results: dict = field(default_factory=dict)
    finished: bool = False  # all hands resolved


@dataclass
class HandOutcome:
    seat_num: int
    hand_index: int
    bet: int
    profit: int          # net change to bankroll (positive = won)
    result: str          # "win" | "loss" | "push" | "blackjack" | "surrender" | "bust"
    final_total: int
    final_cards: list[dict]


@dataclass
class RoundResult:
    seats: list[Seat]
    dealer_hand: Hand
    outcomes: list[HandOutcome]
    insurance_outcomes: dict[int, int]  # seat_num -> profit
    side_bet_outcomes: dict[int, dict]  # seat_num -> {bet_name: profit}
    dealer_blackjack: bool
    rounds_dealt: int = 1


class Round:
    """A single round of blackjack across one or more seats."""

    def __init__(self, rules: Rules, side_bets: SideBets, shoe):
        self.rules = rules
        self.side_bets_cfg = side_bets
        self.shoe = shoe
        self.seats: list[Seat] = []
        self.dealer = Hand()
        self.state: RoundState = RoundState.BETTING
        self._active_seat_idx: int = 0
        self._active_hand_idx: int = 0
        self._split_count_per_seat: dict[int, int] = {}  # seat_num -> split count
        self.result: Optional[RoundResult] = None

    # ---- setup ---------------------------------------------------------

    def add_seat(self, seat: Seat) -> None:
        if self.state != RoundState.BETTING:
            raise RuntimeError("can't add seats after dealing has started")
        seat.bankroll_before = seat.bankroll_before or 0
        seat.hands = [Hand(bet=seat.main_bet)]
        self.seats.append(seat)
        self._split_count_per_seat[seat.seat_num] = 0

    # ---- deal + insurance ---------------------------------------------

    def deal(self) -> None:
        if self.state != RoundState.BETTING:
            raise RuntimeError(f"can't deal from state {self.state}")
        if not self.seats:
            raise RuntimeError("no seats")

        self.state = RoundState.DEALING
        # Two-pass deal: each seat gets one card, then the dealer (face-up),
        # then each seat gets a second card, then the dealer hole card.
        for seat in self.seats:
            seat.hands[0].add_card(self.shoe.next_card())
        self.dealer.add_card(self.shoe.next_card())
        for seat in self.seats:
            seat.hands[0].add_card(self.shoe.next_card())
        if not self.rules.european_no_hole_card:
            self.dealer.add_card(self.shoe.next_card())

        # Naturals don't get to act — flag them finished so the play loop
        # falls through correctly.
        for seat in self.seats:
            if seat.hands[0].is_blackjack:
                seat.hands[0].finished = True

        self._evaluate_pre_play_side_bets()

        if (
            self.rules.insurance_offered
            and self.dealer.cards[0].rank == "A"
        ):
            self.state = RoundState.INSURANCE
            return

        self._after_insurance_decided()

    def offer_insurance(self, seat_num: int, accept: bool, amount: Optional[int] = None) -> None:
        if self.state != RoundState.INSURANCE:
            raise RuntimeError("not in insurance state")
        seat = self._seat_by_num(seat_num)
        if seat.insurance_decided:
            raise RuntimeError("insurance already decided for this seat")
        if accept:
            # Standard rule: insurance is up to half the main bet.
            stake = amount if amount is not None else seat.main_bet // 2
            stake = min(stake, seat.main_bet // 2)
            seat.hands[0].insurance_bet = stake
        seat.insurance_decided = True

    def close_insurance(self) -> None:
        """All insurance decisions are in; peek (if rules) and advance."""
        if self.state != RoundState.INSURANCE:
            raise RuntimeError("not in insurance state")
        for seat in self.seats:
            seat.insurance_decided = True  # implicit decline if not set
        self._after_insurance_decided()

    def _after_insurance_decided(self) -> None:
        # Peek for blackjack on A or 10 up if rules say so.
        if (
            self.rules.dealer_peeks
            and not self.rules.european_no_hole_card
            and len(self.dealer.cards) >= 2
            and dealer_has_blackjack_potential(self.dealer.cards[0].rank)
            and self.dealer.is_blackjack
        ):
            self.dealer.finished = True
            self._settle()
            return

        self.state = RoundState.PLAYING
        self._advance_to_next_active_hand()

    # ---- player action -------------------------------------------------

    @property
    def active_seat(self) -> Optional[Seat]:
        if self.state != RoundState.PLAYING:
            return None
        if self._active_seat_idx >= len(self.seats):
            return None
        return self.seats[self._active_seat_idx]

    @property
    def active_hand(self) -> Optional[Hand]:
        seat = self.active_seat
        if not seat:
            return None
        if self._active_hand_idx >= len(seat.hands):
            return None
        return seat.hands[self._active_hand_idx]

    def legal_actions(self) -> list[Action]:
        seat = self.active_seat
        hand = self.active_hand
        if not seat or not hand:
            return []
        actions: list[Action] = []
        if hand.can_hit(self.rules):
            actions.append("hit")
        if not hand.finished:
            actions.append("stand")
        if hand.can_double(self.rules) and seat.main_bet * 2 >= 0:
            # main_bet>=0 is trivially true; the bankroll check belongs in the
            # caller (we don't track bankroll in the engine).
            actions.append("double")
        split_count = self._split_count_per_seat[seat.seat_num]
        if hand.can_split(self.rules, split_count):
            actions.append("split")
        if hand.can_surrender(self.rules):
            actions.append("surrender")
        return actions

    def act(self, action: Action) -> None:
        if self.state != RoundState.PLAYING:
            raise RuntimeError(f"can't act in state {self.state}")
        seat = self.active_seat
        hand = self.active_hand
        if not seat or not hand:
            raise RuntimeError("no active hand")
        if action not in self.legal_actions():
            raise ValueError(f"illegal action {action}; legal: {self.legal_actions()}")

        if action == "hit":
            hand.add_card(self.shoe.next_card())
            if hand.is_bust:
                hand.finished = True
                self._advance_to_next_active_hand()
        elif action == "stand":
            hand.stood = True
            hand.finished = True
            self._advance_to_next_active_hand()
        elif action == "double":
            hand.bet *= 2
            hand.doubled = True
            hand.add_card(self.shoe.next_card())
            hand.finished = True
            self._advance_to_next_active_hand()
        elif action == "surrender":
            hand.surrendered = True
            hand.finished = True
            self._advance_to_next_active_hand()
        elif action == "split":
            self._do_split(seat, hand)
        else:
            raise ValueError(f"unknown action {action}")

    def _do_split(self, seat: Seat, hand: Hand) -> None:
        if len(hand.cards) != 2:
            raise RuntimeError("split requires exactly 2 cards")
        a, b = hand.cards
        is_aces = a.rank == "A"

        # Replace current hand with one of the cards + draw, then create
        # a new hand from the other card + draw.
        new_hand = Hand(
            bet=seat.main_bet,
            is_split_hand=True,
            from_split_aces=is_aces,
        )
        new_hand.add_card(b)
        hand.cards = [a]
        hand.is_split_hand = True
        hand.from_split_aces = is_aces
        hand.bet = seat.main_bet  # each split hand carries the original stake

        # Draw one card to each split hand.
        hand.add_card(self.shoe.next_card())
        new_hand.add_card(self.shoe.next_card())

        seat.hands.insert(self._active_hand_idx + 1, new_hand)
        self._split_count_per_seat[seat.seat_num] += 1

        # Split-aces typically auto-stand (one card only) unless rules allow hit.
        if is_aces and not self.rules.hit_split_aces:
            hand.finished = True
            new_hand.finished = True
            self._advance_to_next_active_hand()

    def _advance_to_next_active_hand(self) -> None:
        """Move forward through (seat, hand) tuples until one is unfinished
        or we run out — at which point we hand off to the dealer."""
        while self._active_seat_idx < len(self.seats):
            seat = self.seats[self._active_seat_idx]
            while self._active_hand_idx < len(seat.hands):
                hand = seat.hands[self._active_hand_idx]
                if not hand.finished:
                    return
                self._active_hand_idx += 1
            seat.finished = True
            self._active_seat_idx += 1
            self._active_hand_idx = 0

        # No more hands to play -> dealer's turn.
        self._play_dealer_and_settle()

    def _play_dealer_and_settle(self) -> None:
        self.state = RoundState.DEALER
        # If ENHC, deal the dealer's hole card now.
        if self.rules.european_no_hole_card and len(self.dealer.cards) == 1:
            self.dealer.add_card(self.shoe.next_card())

        # Skip dealer hits if every player hand is settled-without-need-for-dealer.
        any_live = any(
            (not h.surrendered) and (not h.is_bust)
            for s in self.seats
            for h in s.hands
        )
        if any_live:
            play_dealer(self.dealer, self.shoe, self.rules)
        else:
            self.dealer.finished = True
        self._settle()

    # ---- settlement ----------------------------------------------------

    def _evaluate_pre_play_side_bets(self) -> None:
        """Side bets that resolve from initial deal + dealer up-card.

        Bust-It and Buster Blackjack resolve later (need final dealer hand).
        Lucky Ladies needs dealer-blackjack flag, also resolved later.
        """
        cfg = self.side_bets_cfg
        dealer_up = self.dealer.cards[0]
        for seat in self.seats:
            p1, p2 = seat.hands[0].cards
            results: dict[str, int] = {}
            sw = seat.side_bets
            if sw.twenty_one_plus_three:
                results["twenty_one_plus_three"] = sb.evaluate_21_plus_3(
                    p1, p2, dealer_up, cfg.twenty_one_plus_three, sw.twenty_one_plus_three
                )
            if sw.perfect_pairs:
                results["perfect_pairs"] = sb.evaluate_perfect_pairs(
                    p1, p2, cfg.perfect_pairs, sw.perfect_pairs
                )
            if sw.royal_match:
                results["royal_match"] = sb.evaluate_royal_match(
                    p1, p2, cfg.royal_match, sw.royal_match
                )
            if sw.match_the_dealer:
                results["match_the_dealer"] = sb.evaluate_match_the_dealer(
                    p1, p2, dealer_up, cfg.match_the_dealer, sw.match_the_dealer
                )
            if sw.over_under_13:
                results["over_under_13"] = sb.evaluate_over_under_13(
                    p1, p2, cfg.over_under_13, sw.over_under_13, sw.over_under_pick
                )
            seat.side_bet_results = results

    def _settle(self) -> None:
        self.state = RoundState.SETTLING
        outcomes: list[HandOutcome] = []
        insurance_outcomes: dict[int, int] = {}
        side_bet_outcomes: dict[int, dict] = {}

        dealer_total = self.dealer.total
        dealer_bust = self.dealer.is_bust
        dealer_bj = self.dealer.is_blackjack

        for seat in self.seats:
            # Insurance settles independently of the main bet.
            ins = seat.hands[0].insurance_bet
            if ins:
                if dealer_bj:
                    insurance_outcomes[seat.seat_num] = payout_amount(
                        ins, self.rules.insurance_payout
                    )
                else:
                    insurance_outcomes[seat.seat_num] = -ins

            # Main hands.
            for idx, hand in enumerate(seat.hands):
                profit = 0
                result = "loss"
                if hand.surrendered:
                    profit = -(hand.bet // 2)
                    result = "surrender"
                elif hand.is_blackjack and not dealer_bj:
                    profit = payout_amount(hand.bet, self.rules.blackjack_payout)
                    result = "blackjack"
                elif hand.is_blackjack and dealer_bj:
                    profit = 0
                    result = "push"
                elif hand.is_bust:
                    profit = -hand.bet
                    result = "bust"
                elif dealer_bj:
                    profit = -hand.bet
                    result = "loss"
                elif dealer_bust:
                    profit = hand.bet
                    result = "win"
                elif hand.total > dealer_total:
                    profit = hand.bet
                    result = "win"
                elif hand.total < dealer_total:
                    profit = -hand.bet
                    result = "loss"
                else:
                    profit = 0
                    result = "push"

                outcomes.append(
                    HandOutcome(
                        seat_num=seat.seat_num,
                        hand_index=idx,
                        bet=hand.bet,
                        profit=profit,
                        result=result,
                        final_total=hand.total,
                        final_cards=[c.to_dict() for c in hand.cards],
                    )
                )

            # Late side bets that need final dealer state.
            cfg = self.side_bets_cfg
            sw = seat.side_bets
            late: dict[str, int] = {}
            if sw.lucky_ladies:
                p1, p2 = seat.hands[0].cards[:2]
                late["lucky_ladies"] = sb.evaluate_lucky_ladies(
                    p1, p2, cfg.lucky_ladies, sw.lucky_ladies, dealer_bj
                )
            if sw.bust_it:
                late["bust_it"] = sb.evaluate_bust_it(
                    self.dealer.cards, cfg.bust_it, sw.bust_it
                )
            if sw.buster_blackjack:
                player_bj = any(h.is_blackjack for h in seat.hands)
                late["buster_blackjack"] = sb.evaluate_buster_blackjack(
                    self.dealer.cards, cfg.buster_blackjack, sw.buster_blackjack, player_bj
                )
            seat.side_bet_results.update(late)
            side_bet_outcomes[seat.seat_num] = dict(seat.side_bet_results)

        self.result = RoundResult(
            seats=self.seats,
            dealer_hand=self.dealer,
            outcomes=outcomes,
            insurance_outcomes=insurance_outcomes,
            side_bet_outcomes=side_bet_outcomes,
            dealer_blackjack=dealer_bj,
        )
        self.state = RoundState.COMPLETE

    # ---- helpers -------------------------------------------------------

    def _seat_by_num(self, seat_num: int) -> Seat:
        for s in self.seats:
            if s.seat_num == seat_num:
                return s
        raise KeyError(f"no seat {seat_num}")
