"""AI personalities. Each function takes a Decision context and returns
(BetAction, amount). The action is filtered against the round's
legal_actions by the caller — a personality that suggests a 'raise'
when only check/fold are legal falls back to whichever non-fold action
is closest in spirit.

Bot vocabulary:
  - book: tight-aggressive baseline (the closest thing to 'correct' play)
  - tight: only premium hands; folds easily
  - loose: plays everything; rarely raises
  - aggressive: bets and raises a lot; doesn't fold easily
  - calling_station: calls anything; never raises
  - bluffer: occasional river bluffs and continuation bets
  - hot_cold: presses up on win streaks, tightens on loss streaks
  - drunk: book play with X% random override
  - mimic: passive — checks/calls minimum, never raises

All bots use HandStrength.score (0..1) as the input to a per-personality
threshold table that maps strength -> (fold/check/call/bet/raise).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Optional

from ..cards import Card, PokerCard
from ..pot import BetAction
from .strength import HandStrength, post_flop_strength, pre_flop_strength


@dataclass
class Decision:
    """Inputs the personality function consumes."""
    hole: list[Card]
    community: list[Card]
    pot_size: int
    to_call: int
    min_raise_to: int            # smallest legal RAISE total (post-call_amount)
    big_blind: int
    stack: int
    legal_actions: list[BetAction]
    is_pre_flop: bool
    last_results: list[int] = field(default_factory=list)  # for hot_cold / streaky
    rng: random.Random = field(default_factory=random.Random)


@dataclass
class Move:
    action: BetAction
    amount: Optional[int] = None  # for BET/RAISE; total raise-to amount


PersonalityFn = Callable[[Decision], Move]


def _strength(d: Decision) -> HandStrength:
    if d.is_pre_flop:
        return pre_flop_strength(d.hole)
    return post_flop_strength(d.hole, d.community)


def _pick(d: Decision, allowed: BetAction, fallback: BetAction) -> BetAction:
    """Return `allowed` if it's legal here, else `fallback`."""
    if allowed in d.legal_actions:
        return allowed
    if fallback in d.legal_actions:
        return fallback
    # Last resort: fold if possible, else check.
    if BetAction.FOLD in d.legal_actions:
        return BetAction.FOLD
    return d.legal_actions[0]


def _bet_size(d: Decision, fraction_of_pot: float) -> int:
    """Pot-sized bet helper. Returns a BET total (when no current bet) or
    a RAISE-to total. Clamped to [big_blind, stack-in-this-round]."""
    raw = max(d.big_blind, int(d.pot_size * fraction_of_pot))
    raw = max(raw, d.min_raise_to) if d.to_call > 0 else max(raw, d.big_blind)
    raw = min(raw, d.stack + d.to_call)
    return raw


# ---- book (tight-aggressive baseline) --------------------------------

def play_book(d: Decision) -> Move:
    s = _strength(d)
    # Pre-flop: open-raise top ~20% of hands; call the rest only with decent.
    if d.is_pre_flop:
        if s.score >= 0.65:
            if d.to_call == 0:
                return Move(_pick(d, BetAction.BET, BetAction.CHECK), amount=_bet_size(d, 1.0))
            return Move(_pick(d, BetAction.RAISE, BetAction.CALL), amount=_bet_size(d, 1.0))
        if s.score >= 0.45:
            if d.to_call == 0:
                return Move(_pick(d, BetAction.CHECK, BetAction.CALL))
            if d.to_call <= d.big_blind * 2:
                return Move(_pick(d, BetAction.CALL, BetAction.FOLD))
        # Weak -> fold to anything, check if free.
        if d.to_call == 0:
            return Move(_pick(d, BetAction.CHECK, BetAction.FOLD))
        return Move(BetAction.FOLD)

    # Post-flop: bet/raise made hands, call mediocre, fold weak.
    if s.score >= 0.7:
        if d.to_call == 0:
            return Move(_pick(d, BetAction.BET, BetAction.CHECK), amount=_bet_size(d, 0.7))
        return Move(_pick(d, BetAction.RAISE, BetAction.CALL), amount=_bet_size(d, 1.0))
    if s.score >= 0.45:
        if d.to_call == 0:
            return Move(_pick(d, BetAction.CHECK, BetAction.CALL))
        if d.to_call <= d.pot_size // 3:
            return Move(_pick(d, BetAction.CALL, BetAction.FOLD))
        return Move(BetAction.FOLD)
    if d.to_call == 0:
        return Move(_pick(d, BetAction.CHECK, BetAction.FOLD))
    return Move(BetAction.FOLD)


# ---- tight ------------------------------------------------------------

def play_tight(d: Decision) -> Move:
    s = _strength(d)
    # Plays only premium. Folds anything below 0.7.
    threshold = 0.7
    if s.score >= 0.85:
        if d.to_call == 0:
            return Move(_pick(d, BetAction.BET, BetAction.CHECK), amount=_bet_size(d, 0.7))
        return Move(_pick(d, BetAction.RAISE, BetAction.CALL), amount=_bet_size(d, 1.0))
    if s.score >= threshold:
        if d.to_call == 0:
            return Move(_pick(d, BetAction.CHECK, BetAction.CALL))
        if d.to_call <= d.pot_size // 4:
            return Move(_pick(d, BetAction.CALL, BetAction.FOLD))
    if d.to_call == 0:
        return Move(_pick(d, BetAction.CHECK, BetAction.FOLD))
    return Move(BetAction.FOLD)


# ---- loose ------------------------------------------------------------

def play_loose(d: Decision) -> Move:
    s = _strength(d)
    # Calls almost anything; only really folds to big bets with garbage.
    if s.score >= 0.6:
        if d.to_call == 0:
            return Move(_pick(d, BetAction.BET, BetAction.CHECK), amount=_bet_size(d, 0.5))
        return Move(_pick(d, BetAction.CALL, BetAction.FOLD))
    if d.to_call == 0:
        return Move(_pick(d, BetAction.CHECK, BetAction.CALL))
    if d.to_call <= d.big_blind * 3:
        return Move(_pick(d, BetAction.CALL, BetAction.FOLD))
    return Move(BetAction.FOLD)


# ---- aggressive (maniac) ---------------------------------------------

def play_aggressive(d: Decision) -> Move:
    s = _strength(d)
    # Raises a LOT, regardless of hand strength.
    if s.score >= 0.4 or d.rng.random() < 0.30:
        if d.to_call == 0:
            return Move(_pick(d, BetAction.BET, BetAction.CHECK), amount=_bet_size(d, 1.0))
        return Move(_pick(d, BetAction.RAISE, BetAction.CALL), amount=_bet_size(d, 1.5))
    if d.to_call == 0:
        return Move(_pick(d, BetAction.CHECK, BetAction.CALL))
    if d.to_call <= d.pot_size // 2:
        return Move(_pick(d, BetAction.CALL, BetAction.FOLD))
    return Move(BetAction.FOLD)


# ---- calling station -------------------------------------------------

def play_calling_station(d: Decision) -> Move:
    # Calls everything. Never raises. Never folds unless it's overbet absurd.
    if d.to_call == 0:
        return Move(_pick(d, BetAction.CHECK, BetAction.CALL))
    if d.to_call > d.stack:
        # Can't afford full call — go all-in to call.
        return Move(_pick(d, BetAction.ALL_IN, BetAction.CALL))
    if d.to_call > d.big_blind * 30:
        # Even calling station folds to a 30bb shove with literally nothing.
        return Move(_pick(d, BetAction.CALL, BetAction.FOLD))
    return Move(BetAction.CALL)


# ---- bluffer ---------------------------------------------------------

def play_bluffer(d: Decision) -> Move:
    """Plays book strength normally, but bluffs ~25% of the time on the
    river (or whenever a check is available with a weak hand)."""
    s = _strength(d)
    is_river_or_late = len(d.community) >= 4
    can_bluff = d.to_call == 0 and is_river_or_late and s.score < 0.5
    if can_bluff and d.rng.random() < 0.25:
        return Move(_pick(d, BetAction.BET, BetAction.CHECK), amount=_bet_size(d, 0.7))
    return play_book(d)


# ---- hot/cold (streaky) ----------------------------------------------

def play_hot_cold(d: Decision) -> Move:
    """Modulates book by recent profit streak. Up the last 3 hands ->
    presses; down -> tightens."""
    streak = sum(1 for r in d.last_results[-3:] if r > 0) - sum(
        1 for r in d.last_results[-3:] if r < 0
    )
    s = _strength(d)
    pressed = s.score + 0.10 * streak     # +.10 per net winning hand recent
    pressed = max(0.0, min(1.0, pressed))
    # Reuse book logic with the modulated score.
    fake_d = Decision(
        hole=d.hole, community=d.community, pot_size=d.pot_size,
        to_call=d.to_call, min_raise_to=d.min_raise_to,
        big_blind=d.big_blind, stack=d.stack,
        legal_actions=d.legal_actions, is_pre_flop=d.is_pre_flop,
        last_results=d.last_results, rng=d.rng,
    )
    # Inject the modulated score by overriding _strength inline:
    return _book_with_score(fake_d, pressed)


def _book_with_score(d: Decision, score: float) -> Move:
    """Book logic but using a caller-supplied score — used by hot_cold."""
    if d.is_pre_flop:
        if score >= 0.65:
            if d.to_call == 0:
                return Move(_pick(d, BetAction.BET, BetAction.CHECK), amount=_bet_size(d, 1.0))
            return Move(_pick(d, BetAction.RAISE, BetAction.CALL), amount=_bet_size(d, 1.0))
        if score >= 0.45:
            if d.to_call == 0:
                return Move(_pick(d, BetAction.CHECK, BetAction.CALL))
            if d.to_call <= d.big_blind * 2:
                return Move(_pick(d, BetAction.CALL, BetAction.FOLD))
        if d.to_call == 0:
            return Move(_pick(d, BetAction.CHECK, BetAction.FOLD))
        return Move(BetAction.FOLD)
    if score >= 0.7:
        if d.to_call == 0:
            return Move(_pick(d, BetAction.BET, BetAction.CHECK), amount=_bet_size(d, 0.7))
        return Move(_pick(d, BetAction.RAISE, BetAction.CALL), amount=_bet_size(d, 1.0))
    if score >= 0.45:
        if d.to_call == 0:
            return Move(_pick(d, BetAction.CHECK, BetAction.CALL))
        if d.to_call <= d.pot_size // 3:
            return Move(_pick(d, BetAction.CALL, BetAction.FOLD))
        return Move(BetAction.FOLD)
    if d.to_call == 0:
        return Move(_pick(d, BetAction.CHECK, BetAction.FOLD))
    return Move(BetAction.FOLD)


# ---- drunk -----------------------------------------------------------

def play_drunk(d: Decision, mistake_rate: float = 0.30) -> Move:
    """Plays book most of the time; randomly does something else otherwise.
    The 'something else' is bounded to a legal action so we don't fall
    out of the state machine."""
    if d.rng.random() >= mistake_rate:
        return play_book(d)
    # Random legal action with a default bet sizing.
    pool = [a for a in d.legal_actions if a != BetAction.FOLD]
    if not pool:
        return Move(BetAction.FOLD)
    a = d.rng.choice(pool)
    if a in (BetAction.BET, BetAction.RAISE):
        return Move(a, amount=_bet_size(d, d.rng.choice([0.3, 0.5, 0.7, 1.0])))
    return Move(a)


# ---- mimic ----------------------------------------------------------

def play_mimic(d: Decision) -> Move:
    """Always check/call the minimum. Never raises, never folds unless they
    can't afford the call and stack is gone."""
    if d.to_call == 0:
        return Move(_pick(d, BetAction.CHECK, BetAction.CALL))
    if d.stack == 0:
        return Move(BetAction.FOLD)
    if d.to_call >= d.stack:
        return Move(_pick(d, BetAction.ALL_IN, BetAction.CALL))
    return Move(BetAction.CALL)


# ---- registry --------------------------------------------------------

PERSONALITIES: dict[str, PersonalityFn] = {
    "book": play_book,
    "tight": play_tight,
    "loose": play_loose,
    "aggressive": play_aggressive,
    "calling_station": play_calling_station,
    "bluffer": play_bluffer,
    "hot_cold": play_hot_cold,
    "drunk": play_drunk,
    "mimic": play_mimic,
}


def get_personality(name: str) -> PersonalityFn:
    if name not in PERSONALITIES:
        raise KeyError(f"unknown personality: {name!r}; choose from {sorted(PERSONALITIES)}")
    return PERSONALITIES[name]


def all_personalities() -> list[str]:
    return list(PERSONALITIES.keys())
