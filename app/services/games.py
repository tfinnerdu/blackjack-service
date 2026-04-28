"""Round orchestration on top of a GameSession.

Responsibilities:
- start_round: pull rules + side bets + shoe state from the session,
  build engine.Round, deal, auto-play any AI seats up to the human's
  turn (or to settlement if the human has no live action), persist
  active_round_json + cards-consumed counter.
- take_insurance: apply human's insurance decision (AI seats decline by
  default unless they're a counter at TC>=+3), close insurance, peek
  if rules say so, AI auto-play to next stop.
- act: apply a human action, AI auto-play forward, persist or settle.

Settlement updates session.bankroll, per-AI bankrolls, last_results,
counter, cards_dealt, hands_played, and book_mistakes.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Optional

from ..ai.seat import AISeat
from ..counting import Counter
from ..counting.indices import insurance_correct
from ..db import db
from ..engine.cards import Card
from ..engine.hand import Hand
from ..engine.round import (
    Action,
    Round,
    RoundState,
    Seat,
    SideBetWagers,
)
from ..engine.rules import Rules, SideBets
from ..engine.shoe import Shoe
from ..models import GameSession
from ..strategy import Capabilities, basic_strategy
from ..strategy.book import book
from . import shoe_trace
from .round_state import round_from_json, round_to_json
from .sessions import (
    rules_from_dict,
    shoe_from_session,
    side_bets_from_dict,
)


# ---- public errors -----------------------------------------------------

class GameError(Exception):
    """Caller-visible problem (bad input, illegal action, no round, etc.).
    Routes turn this into 400/409 responses."""


# ---- helpers -----------------------------------------------------------

def _rules(sess: GameSession) -> Rules:
    return rules_from_dict(json.loads(sess.rules_json))


def _side_bets(sess: GameSession) -> SideBets:
    return side_bets_from_dict(json.loads(sess.side_bets_json))


def _ai_seats(sess: GameSession) -> dict[int, AISeat]:
    """Reconstruct AI seats keyed by seat_num. Bankrolls come straight off
    the persisted dict so per-seat busts persist across rounds."""
    rows = json.loads(sess.ai_seats_json)
    seats: dict[int, AISeat] = {}
    for row in rows:
        seat = AISeat(
            seat_num=row["seat_num"],
            playstyle=row.get("playstyle", "book"),
            bet_pattern=row.get("bet_pattern", "flat"),
            base_bet=row.get("base_bet", 10),
            bankroll=row.get("bankroll", 200),
            rebuy_on_bust=row.get("rebuy_on_bust", False),
            rebuy_amount=row.get("rebuy_amount", 200),
            drunk_mistake_rate=row.get("drunk_mistake_rate", 0.20),
            seed=row.get("seed"),
        )
        # Restore per-seat history if it was persisted (helps streak-aware
        # bet patterns stay consistent across rounds).
        seat.last_results = list(row.get("last_results", []))
        seats[seat.seat_num] = seat
    return seats


def _persist_ai_seats(sess: GameSession, ai: dict[int, AISeat]) -> None:
    rows = []
    for seat in sorted(ai.values(), key=lambda s: s.seat_num):
        d = seat.to_dict()
        d["last_results"] = list(seat.last_results)
        rows.append(d)
    sess.ai_seats_json = json.dumps(rows)


# Heuristic EV-loss table when the human deviates from book. Values are
# fractions of the hand's main bet, returned in cents to avoid float
# accumulation in the running session counter. NOT a true Monte Carlo EV
# calculation — these are coarse magnitudes that give directional
# feedback ('mistakes are costing you ~$50 over this session') without
# the per-action sim cost. UI labels this an estimate.
_EV_LOSS_FRACTION: dict[tuple[str, str], float] = {
    # (player_did, book_said) -> fraction of bet lost
    ("hit", "stand"): 0.30,         # busts or worsens a made hand
    ("stand", "hit"): 0.25,         # gives up easy improvement
    ("hit", "double"): 0.30,        # missed the double bonus on top of suboptimal play
    ("stand", "double"): 0.30,      # missed the double bonus
    ("double", "hit"): 0.25,        # over-committed; might have hit anyway
    ("double", "stand"): 0.50,      # double on a bad spot
    ("split", "hit"): 0.30,
    ("split", "stand"): 0.40,
    ("hit", "split"): 0.20,
    ("stand", "split"): 0.20,
    ("surrender", "hit"): 0.25,     # took half-loss vs likely positive EV
    ("surrender", "stand"): 0.40,   # took half-loss on a stand spot
    ("surrender", "double"): 0.50,
    ("hit", "surrender"): 0.25,
    ("stand", "surrender"): 0.25,
    ("double", "surrender"): 0.50,
    ("split", "surrender"): 0.30,
}


def _ev_loss_cents(player_action: str, book_action: str, bet_dollars: int) -> int:
    """Heuristic dollar EV lost on this single action. Returned in cents."""
    if player_action == book_action:
        return 0
    fraction = _EV_LOSS_FRACTION.get((player_action, book_action), 0.20)
    return int(round(bet_dollars * fraction * 100))


def _capabilities_from_legal(legal: list[Action]) -> Capabilities:
    return Capabilities(
        can_double="double" in legal,
        can_split="split" in legal,
        can_surrender="surrender" in legal,
    )


def _count_cards_in_round(rnd: Round) -> int:
    """Number of cards visible in a round so far (dealer + every hand).
    Used to advance session.cards_dealt + counter at round end."""
    n = len(rnd.dealer.cards)
    for s in rnd.seats:
        for h in s.hands:
            n += len(h.cards)
    return n


def _all_cards_in_round(rnd: Round) -> list[Card]:
    cards = list(rnd.dealer.cards)
    for s in rnd.seats:
        for h in s.hands:
            cards.extend(h.cards)
    return cards


# ---- AI auto-play ------------------------------------------------------

def _auto_play_until_human_or_done(
    rnd: Round,
    rules: Rules,
    ai_seats: dict[int, AISeat],
    true_count: Optional[float],
) -> None:
    """Walk forward through the round, letting AI seats play their hands.
    Stops when a human seat is up to act, when insurance is owed, or when
    the round is complete."""
    while rnd.state == RoundState.PLAYING:
        seat = rnd.active_seat
        if seat is None:
            return
        if seat.is_human:
            return
        ai = ai_seats.get(seat.seat_num)
        if ai is None:
            # Should not happen in a well-formed session, but bail safely
            # rather than spinning if it does.
            rnd.act("stand")
            continue
        hand = rnd.active_hand
        if hand is None:
            return
        legal = rnd.legal_actions()
        caps = _capabilities_from_legal(legal)
        action = ai.pick_action(hand, rnd.dealer.cards[0], rules, caps, true_count)
        if action not in legal:
            # The playstyle suggested something illegal here (e.g. double
            # on 3-card hand). Fall back to stand which is always legal
            # while playing.
            action = "stand" if "stand" in legal else legal[0]
        rnd.act(action)


def _auto_decide_ai_insurance(
    rnd: Round,
    ai_seats: dict[int, AISeat],
    true_count: Optional[float],
) -> None:
    """AI seats accept insurance only if they're a counter at TC>=+3.
    Everyone else declines."""
    if rnd.state != RoundState.INSURANCE:
        return
    for seat in rnd.seats:
        if seat.is_human:
            continue
        ai = ai_seats.get(seat.seat_num)
        accept = (
            ai is not None
            and ai.playstyle == "counter"
            and true_count is not None
            and insurance_correct(true_count)
        )
        rnd.offer_insurance(seat.seat_num, accept=accept)


# ---- public API --------------------------------------------------------

@dataclass
class RoundView:
    """JSON-friendly view of the current round + human-relevant guidance.
    Returned from start_round / take_action / take_insurance."""
    state: str
    seats: list[dict]
    dealer: dict
    active_seat_num: Optional[int]
    active_hand_index: Optional[int]
    legal_actions: list[str]
    insurance_offered: bool
    book: Optional[dict]   # recommended action + deviation source
    result: Optional[dict] # populated only when state == complete

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "seats": self.seats,
            "dealer": self.dealer,
            "active_seat_num": self.active_seat_num,
            "active_hand_index": self.active_hand_index,
            "legal_actions": self.legal_actions,
            "insurance_offered": self.insurance_offered,
            "book": self.book,
            "result": self.result,
        }


def _build_view(rnd: Round, rules: Rules, true_count: Optional[float]) -> RoundView:
    """Snapshot the round into a JSON-friendly view + the book's recommendation
    for whichever hand is active."""
    seats = []
    for seat in rnd.seats:
        seats.append({
            "seat_num": seat.seat_num,
            "main_bet": seat.main_bet,
            "is_human": seat.is_human,
            "bankroll_before": seat.bankroll_before,
            "side_bet_results": dict(seat.side_bet_results),
            "finished": seat.finished,
            "hands": [h.to_dict() for h in seat.hands],
        })
    dealer = {
        "cards": [c.to_dict() for c in rnd.dealer.cards],
        "total": rnd.dealer.total,
        "blackjack": rnd.dealer.is_blackjack,
        "bust": rnd.dealer.is_bust,
        "finished": rnd.dealer.finished,
    }

    book_payload: Optional[dict] = None
    legal: list[str] = []
    active_seat_num: Optional[int] = None
    active_hand_index: Optional[int] = None
    if rnd.state == RoundState.PLAYING:
        seat = rnd.active_seat
        hand = rnd.active_hand
        if seat is not None and hand is not None:
            active_seat_num = seat.seat_num
            active_hand_index = rnd._active_hand_idx
            legal = list(rnd.legal_actions())
            if seat.is_human:
                caps = _capabilities_from_legal(legal)
                call = book(hand, rnd.dealer.cards[0], rules, caps, true_count=true_count)
                basic = basic_strategy(hand, rnd.dealer.cards[0], rules, caps)
                book_payload = {
                    "action": call.action,
                    "source": call.source,
                    "deviation": call.deviation,
                    "basic_action": basic,
                }

    result: Optional[dict] = None
    if rnd.state == RoundState.COMPLETE and rnd.result is not None:
        result = {
            "outcomes": [
                {
                    "seat_num": o.seat_num,
                    "hand_index": o.hand_index,
                    "bet": o.bet,
                    "profit": o.profit,
                    "result": o.result,
                    "final_total": o.final_total,
                    "final_cards": o.final_cards,
                }
                for o in rnd.result.outcomes
            ],
            "insurance_outcomes": dict(rnd.result.insurance_outcomes),
            "side_bet_outcomes": dict(rnd.result.side_bet_outcomes),
            "dealer_blackjack": rnd.result.dealer_blackjack,
        }

    return RoundView(
        state=rnd.state.value,
        seats=seats,
        dealer=dealer,
        active_seat_num=active_seat_num,
        active_hand_index=active_hand_index,
        legal_actions=legal,
        insurance_offered=(rnd.state == RoundState.INSURANCE),
        book=book_payload,
        result=result,
    )


def _persist_round(sess: GameSession, rnd: Round, *, started_at_dealt: int) -> None:
    """Persist (or clear) the in-flight round on the session row.

    On COMPLETE we don't store the round; instead, the caller has already
    settled stats and bumped session.cards_dealt + counter, so the row goes
    back to "no round" state.
    """
    if rnd.state == RoundState.COMPLETE:
        sess.active_round_json = None
    else:
        consumed = _count_cards_in_round(rnd)
        sess.active_round_json = round_to_json(
            rnd, cards_dealt_at_start=started_at_dealt, cards_consumed=consumed
        )


# ---- parallel-replay bankrolls -----------------------------------------

def _replay_human_profit(
    sess: GameSession,
    rules: Rules,
    side_bets_cfg: SideBets,
    started_at_dealt: int,
    actual_seats: list[Seat],
    ai_seats: dict[int, AISeat],
    true_count_pre_deal: Optional[float],
    *,
    use_indices: bool,
    bet_with_count: bool,
) -> int:
    """Replay the round at the same shoe-state and return the human seat's
    profit under a counterfactual strategy.

    `use_indices=True` plays Hi-Lo / Illustrious 18 deviations (the count
    influences action selection). `bet_with_count=True` sizes the human's
    bet via the count-spread pattern using the human's actual bet as the
    base unit. Both off → "what if I'd just played perfect basic strategy."

    AI seats replay with their own playstyle. Their actions can diverge
    from the actual round (different cards arrive after the human's
    different choices), which is fine — we only sum the human's profit.
    """
    # Rebuild a fresh shoe at the same point the actual round started from.
    # Same shuffle-counter logic as shoe_from_session — replay needs to
    # land on the current permutation, not the initial one.
    shoe = Shoe(
        decks=rules.decks,
        mode=rules.shuffle_mode,
        penetration=rules.penetration,
        seed=sess.shoe_seed,
    )
    needed_shuffles = max(1, int(sess.shoe_shuffles or 1))
    for _ in range(needed_shuffles - 1):
        shoe.shuffle()
    if rules.shuffle_mode != ShuffleMode.CSM:
        for _ in range(started_at_dealt):
            shoe.next_card()

    # Replicate the seat configuration of the actual round, with the
    # optional bet override on the human seat.
    rnd = Round(rules, side_bets_cfg, shoe)
    human_seat_num = sess.player_seat
    human_main_bet = next(
        (s.main_bet for s in actual_seats if s.is_human), 0
    )
    if human_main_bet <= 0:
        return 0

    if bet_with_count:
        from ..ai.bet_patterns import bet_count_spread
        rng = random.Random(0)  # not used by bet_count_spread
        human_bet = bet_count_spread(
            sess.bankroll, human_main_bet, [], rules,
            true_count_pre_deal, rng,
        )
    else:
        human_bet = human_main_bet

    for s in actual_seats:
        rnd.add_seat(Seat(
            seat_num=s.seat_num,
            main_bet=human_bet if s.is_human else s.main_bet,
            is_human=s.is_human,
        ))

    rnd.deal()

    if rnd.state == RoundState.INSURANCE:
        for seat in rnd.seats:
            if seat.is_human:
                from ..strategy.book import book_insurance
                ins = book_insurance(true_count_pre_deal if use_indices else None)
                accept = ins.note == "take insurance"
                rnd.offer_insurance(seat.seat_num, accept=accept)
            else:
                ai = ai_seats.get(seat.seat_num)
                accept = (
                    ai is not None
                    and ai.playstyle == "counter"
                    and true_count_pre_deal is not None
                    and insurance_correct(true_count_pre_deal)
                )
                rnd.offer_insurance(seat.seat_num, accept=accept)
        rnd.close_insurance()

    while rnd.state == RoundState.PLAYING:
        seat = rnd.active_seat
        hand = rnd.active_hand
        if seat is None or hand is None:
            break
        legal = rnd.legal_actions()
        caps = _capabilities_from_legal(legal)

        if seat.is_human:
            tc_for_book = true_count_pre_deal if use_indices else None
            action = book(
                hand, rnd.dealer.cards[0], rules, caps,
                true_count=tc_for_book,
            ).action
        else:
            ai = ai_seats.get(seat.seat_num)
            if ai is not None:
                action = ai.pick_action(
                    hand, rnd.dealer.cards[0], rules, caps,
                    true_count_pre_deal,
                )
            else:
                action = "stand"

        if action not in legal:
            action = "stand" if "stand" in legal else legal[0]
        rnd.act(action)

    if rnd.state != RoundState.COMPLETE or rnd.result is None:
        return 0

    profit = sum(
        o.profit for o in rnd.result.outcomes if o.seat_num == human_seat_num
    )
    profit += rnd.result.insurance_outcomes.get(human_seat_num, 0)
    profit += sum(rnd.result.side_bet_outcomes.get(human_seat_num, {}).values())
    return profit


def _settle_into_session(sess: GameSession, rnd: Round) -> None:
    """Fold a completed round into the session: bankroll, AI bankrolls,
    counter, cards_dealt, hands_played, last_results, book_mistakes."""
    if rnd.state != RoundState.COMPLETE or rnd.result is None:
        return

    rules = _rules(sess)
    side_bets_cfg = _side_bets(sess)
    # Snapshot for parallel replay before we advance the shoe + counter.
    replay_started_at = sess.cards_dealt
    replay_seats = [
        Seat(seat_num=s.seat_num, main_bet=s.main_bet, is_human=s.is_human)
        for s in rnd.seats
    ]
    replay_ai = _ai_seats(sess)
    replay_true_count: Optional[float] = None
    if sess.counter_cards_seen and rules.shuffle_mode != ShuffleMode.CSM:
        decks_remaining = max(0.5, (rules.decks * 52 - sess.counter_cards_seen) / 52.0)
        replay_true_count = sess.running_count / decks_remaining

    # Counter + cards-dealt update from every visible card.
    counter = Counter(decks=rules.decks)
    counter.running_count = sess.running_count
    counter.cards_seen = sess.counter_cards_seen
    counter.see_many(_all_cards_in_round(rnd))
    sess.running_count = counter.running_count
    sess.counter_cards_seen = counter.cards_seen
    sess.cards_dealt += _count_cards_in_round(rnd)

    # Player bankroll + history.
    last_results: list[int] = json.loads(sess.last_results_json)
    player_seat_outcomes = [
        o for o in rnd.result.outcomes if o.seat_num == sess.player_seat
    ]
    profit = sum(o.profit for o in player_seat_outcomes)
    profit += rnd.result.insurance_outcomes.get(sess.player_seat, 0)
    profit += sum(rnd.result.side_bet_outcomes.get(sess.player_seat, {}).values())
    sess.bankroll += profit
    sess.actual_profit += profit
    last_results.append(profit)
    if len(last_results) > 200:
        last_results = last_results[-200:]
    sess.last_results_json = json.dumps(last_results)
    sess.hands_played += len(player_seat_outcomes)
    # Result-type counters — split hands count separately so the totals
    # add up to hands_played.
    for o in player_seat_outcomes:
        if o.result == "win":
            sess.wins += 1
        elif o.result == "blackjack":
            sess.wins += 1
            sess.player_blackjacks += 1
        elif o.result == "loss":
            sess.losses += 1
        elif o.result == "bust":
            sess.losses += 1
            sess.busts += 1
        elif o.result == "push":
            sess.pushes += 1
        elif o.result == "surrender":
            sess.losses += 1
            sess.surrenders += 1

    # AI bankrolls: settle each AI seat from its outcomes + side bets.
    ai = _ai_seats(sess)
    for seat in rnd.seats:
        if seat.is_human:
            continue
        ai_seat = ai.get(seat.seat_num)
        if ai_seat is None:
            continue
        seat_profit = sum(
            o.profit for o in rnd.result.outcomes if o.seat_num == seat.seat_num
        )
        seat_profit += rnd.result.insurance_outcomes.get(seat.seat_num, 0)
        seat_profit += sum(
            rnd.result.side_bet_outcomes.get(seat.seat_num, {}).values()
        )
        ai_seat.record_result(seat_profit)
    _persist_ai_seats(sess, ai)

    # Parallel-replay bankrolls. Two counterfactuals per round: human seat
    # plays book, and human seat plays book + count-aware bet sizing.
    # Failures here must not break settlement — they're an extra read-only
    # stat, not a hard correctness guarantee.
    try:
        book_profit = _replay_human_profit(
            sess, rules, side_bets_cfg, replay_started_at, replay_seats,
            replay_ai, replay_true_count,
            use_indices=False, bet_with_count=False,
        )
        counter_profit = _replay_human_profit(
            sess, rules, side_bets_cfg, replay_started_at, replay_seats,
            replay_ai, replay_true_count,
            use_indices=True, bet_with_count=True,
        )
    except Exception:
        book_profit = 0
        counter_profit = 0
    sess.book_bankroll = (sess.book_bankroll or 0) + book_profit
    sess.counter_bankroll = (sess.counter_bankroll or 0) + counter_profit

    history: list = json.loads(sess.bankroll_history_json or "[]")
    history.append({
        "hand": sess.hands_played,
        "actual": sess.bankroll,
        "book": sess.book_bankroll,
        "counter": sess.counter_bankroll,
    })
    if len(history) > 1000:
        history = history[-1000:]
    sess.bankroll_history_json = json.dumps(history)

    if shoe_trace.is_enabled():
        shoe_trace.trace_round(
            sess, rnd,
            running_count_after=sess.running_count,
            cards_seen_after=sess.counter_cards_seen,
        )


# ---- start_round -------------------------------------------------------

@dataclass
class StartRoundRequest:
    """All the inputs to start a round. Side bets are dict[bet_name, amount].
    over_under_pick stays inside that dict ('over' or 'under') if used."""
    main_bet: int
    side_bets: Optional[dict] = None  # raw dict from the request body


def start_round(sess: GameSession, req: StartRoundRequest) -> RoundView:
    if sess.active_round_json:
        raise GameError("a round is already in flight; finish it or reset the shoe")
    if req.main_bet <= 0:
        raise GameError("main_bet must be > 0")

    rules = _rules(sess)
    side_bets_cfg = _side_bets(sess)

    # Bankroll check for the human seat — main + total side-bet stakes.
    sb = req.side_bets or {}
    total_human_stake = req.main_bet + sum(
        v for k, v in sb.items() if isinstance(v, (int, float)) and k != "over_under_pick"
    )
    if total_human_stake > sess.bankroll:
        raise GameError("insufficient bankroll for this stake")
    if not (rules.min_bet <= req.main_bet <= rules.max_bet):
        raise GameError(f"main_bet must be {rules.min_bet}..{rules.max_bet}")

    # Build the shoe at the recorded position. Reshuffle if we hit penetration.
    shoe = shoe_from_session(sess)
    if shoe.needs_reshuffle:
        shoe.shuffle()
        # Bump the persisted shuffle counter so the next page-load
        # rebuilds the shoe at the same NEW permutation. Without this,
        # rebuilding from (seed, cards_dealt) alone rewinds to the
        # initial permutation — i.e. the user sees the same hands
        # again after a reshuffle.
        sess.shoe_shuffles = (sess.shoe_shuffles or 1) + 1
        sess.cards_dealt = 0
        sess.running_count = 0
        sess.counter_cards_seen = 0

    rnd = Round(rules, side_bets_cfg, shoe)

    # AI seats first (lower seat numbers can act before the human if seated
    # earlier; we add in seat-num order so the engine plays them in order).
    ai_seats = _ai_seats(sess)
    true_count_now: Optional[float] = None
    if sess.counter_cards_seen and rules.shuffle_mode != ShuffleMode.CSM:
        # Compute pre-deal true count for AI bet sizing + insurance.
        decks_remaining = max(0.5, (rules.decks * 52 - sess.counter_cards_seen) / 52.0)
        true_count_now = sess.running_count / decks_remaining

    claimed_seats = json.loads(sess.seat_tokens_json or "{}")
    claimed_seat_nums = {int(k) for k in claimed_seats.keys()}

    for seat_num in sorted(set(list(ai_seats.keys()) + [sess.player_seat])):
        if seat_num == sess.player_seat:
            sb_wagers = _side_bet_wagers_from_dict(sb)
            rnd.add_seat(Seat(
                seat_num=seat_num,
                main_bet=req.main_bet,
                side_bets=sb_wagers,
                is_human=True,
                bankroll_before=sess.bankroll,
            ))
            continue
        ai = ai_seats[seat_num]
        # A guest claim converts an AI seat to human-controlled. The
        # bot's `base_bet` is used as the table bet; per-guest bet
        # control is a future enhancement.
        if seat_num in claimed_seat_nums:
            bet = max(rules.min_bet, min(ai.base_bet, ai.bankroll, rules.max_bet))
            if bet <= 0 or ai.bankroll < rules.min_bet:
                continue  # claimed but bust — sits out this round
            rnd.add_seat(Seat(
                seat_num=seat_num,
                main_bet=bet,
                is_human=True,
                bankroll_before=ai.bankroll,
            ))
            continue
        bet = ai.pick_bet(rules, true_count_now)
        if bet <= 0:
            continue  # bust seat sits this round out
        rnd.add_seat(Seat(
            seat_num=seat_num,
            main_bet=bet,
            is_human=False,
            bankroll_before=ai.bankroll,
        ))

    started_at_dealt = sess.cards_dealt
    rnd.deal()

    # Round may already be complete (everyone got a natural and dealer pushed,
    # or dealer peeked into BJ). If insurance is owed, AI seats decide first
    # and we return the human's prompt.
    if rnd.state == RoundState.INSURANCE:
        _auto_decide_ai_insurance(rnd, ai_seats, true_count_now)
        # Don't close insurance yet — the human still has to choose.
    else:
        _auto_play_until_human_or_done(rnd, rules, ai_seats, true_count_now)

    if rnd.state == RoundState.COMPLETE:
        _settle_into_session(sess, rnd)
    _persist_round(sess, rnd, started_at_dealt=started_at_dealt)
    db.session.commit()
    return _build_view(rnd, rules, true_count_now)


def _side_bet_wagers_from_dict(d: dict) -> SideBetWagers:
    return SideBetWagers(
        twenty_one_plus_three=int(d.get("twenty_one_plus_three", 0) or 0),
        perfect_pairs=int(d.get("perfect_pairs", 0) or 0),
        lucky_ladies=int(d.get("lucky_ladies", 0) or 0),
        royal_match=int(d.get("royal_match", 0) or 0),
        match_the_dealer=int(d.get("match_the_dealer", 0) or 0),
        over_under_13=int(d.get("over_under_13", 0) or 0),
        over_under_pick=d.get("over_under_pick", "over"),
        bust_it=int(d.get("bust_it", 0) or 0),
        buster_blackjack=int(d.get("buster_blackjack", 0) or 0),
    )


# Re-imported here so start_round can introspect the shuffle mode without
# pulling the engine namespace into the module-level imports above.
from ..engine.rules import ShuffleMode  # noqa: E402


# ---- restore in-flight round from session -----------------------------

def _load_active_round(sess: GameSession) -> tuple[Round, int, dict[int, AISeat], Optional[float]]:
    """Reconstruct (round, cards_dealt_at_start, ai_seats, true_count_now).

    The shoe is rebuilt from the session's seed and burned forward to
    cards_dealt_at_start + cards_consumed so the next deal returns the
    correct card.
    """
    if not sess.active_round_json:
        raise GameError("no round in flight")

    payload = json.loads(sess.active_round_json)
    rules = _rules(sess)
    side_bets_cfg = _side_bets(sess)

    started_at = int(payload["cards_dealt_at_start"])
    consumed = int(payload["cards_consumed"])

    shoe = Shoe(
        decks=rules.decks,
        mode=rules.shuffle_mode,
        penetration=rules.penetration,
        seed=sess.shoe_seed,
    )
    needed_shuffles = max(1, int(sess.shoe_shuffles or 1))
    for _ in range(needed_shuffles - 1):
        shoe.shuffle()
    if rules.shuffle_mode != ShuffleMode.CSM:
        for _ in range(started_at + consumed):
            shoe.next_card()

    rnd = round_from_json(json.dumps(payload), rules, side_bets_cfg, shoe)
    ai = _ai_seats(sess)

    # True count at the moment the round started (pre-deal). For mid-round
    # AI decisions we keep the same TC since AI plays don't recompute mid-deal.
    true_count_now: Optional[float] = None
    if sess.counter_cards_seen and rules.shuffle_mode != ShuffleMode.CSM:
        decks_remaining = max(0.5, (rules.decks * 52 - sess.counter_cards_seen) / 52.0)
        true_count_now = sess.running_count / decks_remaining

    return rnd, started_at, ai, true_count_now


# ---- take_insurance ---------------------------------------------------

def take_insurance(
    sess: GameSession,
    accept: bool,
    amount: Optional[int] = None,
    *,
    seat_num: Optional[int] = None,
) -> RoundView:
    rnd, started_at_dealt, ai, true_count_now = _load_active_round(sess)
    rules = _rules(sess)

    if rnd.state != RoundState.INSURANCE:
        raise GameError("not in insurance state")

    target_seat = seat_num if seat_num is not None else sess.player_seat
    rnd.offer_insurance(seat_num=target_seat, accept=accept, amount=amount)
    # Only close insurance once every human seat has decided. AI seats
    # decide via _auto_decide_ai_insurance up-front; if more humans
    # remain, leave the round in INSURANCE state.
    pending = [
        s for s in rnd.seats
        if s.is_human and not s.insurance_decided
    ]
    if not pending:
        rnd.close_insurance()
        if rnd.state == RoundState.PLAYING:
            _auto_play_until_human_or_done(rnd, rules, ai, true_count_now)

    if rnd.state == RoundState.COMPLETE:
        _settle_into_session(sess, rnd)
    _persist_round(sess, rnd, started_at_dealt=started_at_dealt)
    db.session.commit()
    return _build_view(rnd, rules, true_count_now)


# ---- take_action ------------------------------------------------------

def take_action(
    sess: GameSession,
    action: Action,
    *,
    seat_num: Optional[int] = None,
) -> RoundView:
    rnd, started_at_dealt, ai, true_count_now = _load_active_round(sess)
    rules = _rules(sess)

    if rnd.state != RoundState.PLAYING:
        raise GameError(f"can't act in state {rnd.state.value}")
    seat = rnd.active_seat
    if seat is None or not seat.is_human:
        raise GameError("it's not the human's turn")
    if seat_num is not None and seat.seat_num != seat_num:
        raise GameError(
            f"not your turn — seat {seat.seat_num} is acting, "
            f"caller's seat is {seat_num}"
        )

    legal = rnd.legal_actions()
    if action not in legal:
        raise GameError(f"illegal action; legal: {legal}")

    # Bookkeeping: record book vs actual for the hand BEFORE we mutate it.
    # A "mistake" is any time the host's action differs from the book;
    # guest seats don't accrue book-mistakes since they're not the user
    # whose stats this session tracks.
    is_host_seat = seat.seat_num == sess.player_seat
    hand = rnd.active_hand
    if hand is not None and is_host_seat:
        caps = _capabilities_from_legal(legal)
        recommended = book(hand, rnd.dealer.cards[0], rules, caps, true_count=true_count_now).action
        if action != recommended:
            sess.book_mistakes += 1
            sess.ev_lost_cents += _ev_loss_cents(action, recommended, hand.bet)

    # Doubling/splitting requires another bet unit. Check against the
    # right bankroll: host pulls from sess.bankroll; a guest seat pulls
    # from the AI config row's bankroll (which the guest inherited).
    available_bankroll = (
        sess.bankroll if is_host_seat
        else (ai.get(seat.seat_num).bankroll if ai.get(seat.seat_num) else 0)
    )
    if action == "double":
        if hand is None:
            raise GameError("no active hand")
        if hand.bet > available_bankroll:
            raise GameError("insufficient bankroll to double")
    if action == "split":
        if seat.main_bet > available_bankroll:
            raise GameError("insufficient bankroll to split")

    rnd.act(action)
    _auto_play_until_human_or_done(rnd, rules, ai, true_count_now)

    if rnd.state == RoundState.COMPLETE:
        _settle_into_session(sess, rnd)
    _persist_round(sess, rnd, started_at_dealt=started_at_dealt)
    db.session.commit()
    return _build_view(rnd, rules, true_count_now)


# ---- view-only fetch (page reload) ------------------------------------

def get_active_round_view(sess: GameSession) -> Optional[RoundView]:
    """Return the current in-flight round view, or None if no round."""
    if not sess.active_round_json:
        return None
    rnd, _, _, true_count_now = _load_active_round(sess)
    rules = _rules(sess)
    return _build_view(rnd, rules, true_count_now)

