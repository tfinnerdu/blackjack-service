"""Companion mode: given a variant + the user's cards (hole / community /
up-cards / drawn), return the analysis they'd want to see at the table:

  - Best high hand (class + tie-breakers + which 5 cards used)
  - Best low hand if the variant has a low (qualifying or not) + qualifier
    explanation
  - Hi/lo split rule rendered in plain English
  - Hands-that-beat-you reference (top 3 hand classes above yours)
  - Wild-card resolution explanation if the user's hand contains wilds

This stays entirely server-side stateless: the request payload includes
the variant (or a variant_id) + the user's cards. No session needed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Optional

from .cards import Card, Joker, PokerCard, poker_card_to_token
from .evaluator import (
    HAND_CLASS_NAMES,
    HandClass,
    HandRank,
    LowRank,
    LowRule,
    WildMode,
    best_high,
    classify_high,
    evaluate_with_wilds,
)
from .evaluator.low import best_low
from .variants import (
    HandRequirement,
    HiLoSplit,
    VariantSpec,
    WildKind,
    WildRule,
)


@dataclass
class HighAnalysis:
    cls_name: str
    cls_value: int
    tiebreakers: tuple[int, ...]
    cards: list[str]   # tokens of the 5 cards used
    explanation: str


@dataclass
class LowAnalysis:
    qualifies: bool
    rule: str
    name: str
    cards: list[str]
    explanation: str


@dataclass
class CompanionAnalysis:
    variant_name: str
    user_cards: list[str]
    hi: Optional[HighAnalysis] = None
    lo: Optional[LowAnalysis] = None
    hi_lo_explanation: str = ""
    wild_resolution: Optional[str] = None
    hands_that_beat_you: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "variant_name": self.variant_name,
            "user_cards": list(self.user_cards),
            "hi": _hi_to_dict(self.hi),
            "lo": _lo_to_dict(self.lo),
            "hi_lo_explanation": self.hi_lo_explanation,
            "wild_resolution": self.wild_resolution,
            "hands_that_beat_you": list(self.hands_that_beat_you),
            "notes": list(self.notes),
        }


def _hi_to_dict(h: Optional[HighAnalysis]) -> Optional[dict]:
    if h is None:
        return None
    return {
        "cls_name": h.cls_name,
        "cls_value": h.cls_value,
        "tiebreakers": list(h.tiebreakers),
        "cards": list(h.cards),
        "explanation": h.explanation,
    }


def _lo_to_dict(l: Optional[LowAnalysis]) -> Optional[dict]:
    if l is None:
        return None
    return {
        "qualifies": l.qualifies,
        "rule": l.rule,
        "name": l.name,
        "cards": list(l.cards),
        "explanation": l.explanation,
    }


# ---- wild detection ----------------------------------------------------

def _wild_indices(cards: list[PokerCard], rules: list[WildRule]) -> tuple[list[int], WildMode, str]:
    """Return (indices, dominant_mode, explanation).

    'Dominant mode' is the strictest active mode: SF_ONLY > BUG > FULLY_WILD.
    A hand with mixed rules is rare outside designer games — for v1 we
    apply the strictest mode hand-wide and explain it in the result.
    """
    indices: list[int] = []
    explanations: list[str] = []
    modes: set[WildMode] = set()

    for i, c in enumerate(cards):
        for rule in rules:
            if _matches(c, rule):
                indices.append(i)
                modes.add(rule.mode)
                explanations.append(_describe_match(c, rule))
                break

    indices = sorted(set(indices))
    if not indices:
        return [], WildMode.FULLY_WILD, ""

    if WildMode.STRAIGHT_FLUSH_ONLY in modes:
        dominant = WildMode.STRAIGHT_FLUSH_ONLY
    elif WildMode.BUG in modes:
        dominant = WildMode.BUG
    else:
        dominant = WildMode.FULLY_WILD

    explanation = "; ".join(dict.fromkeys(explanations)) + " | " + _mode_blurb(dominant)
    return indices, dominant, explanation


def _matches(card: PokerCard, rule: WildRule) -> bool:
    if rule.kind == WildKind.JOKER:
        return isinstance(card, Joker)
    if isinstance(card, Joker):
        return False  # joker only matches WildKind.JOKER
    if rule.kind == WildKind.RANK:
        return rule.rank is not None and card.rank == rule.rank
    if rule.kind == WildKind.SUIT:
        return rule.suit is not None and card.suit.value == rule.suit
    if rule.kind == WildKind.SPECIFIC:
        return rule.card_token is not None and poker_card_to_token(card) == rule.card_token
    if rule.kind == WildKind.ONE_EYED_JACK:
        return card.rank == "J" and card.suit.value in ("H", "S")
    if rule.kind == WildKind.SUICIDE_KING:
        return card.rank == "K" and card.suit.value == "H"
    return False


def _describe_match(card: PokerCard, rule: WildRule) -> str:
    token = poker_card_to_token(card)
    if rule.kind == WildKind.JOKER:
        return f"{token} (joker)"
    if rule.kind == WildKind.RANK:
        return f"{token} (all {rule.rank}s wild)"
    if rule.kind == WildKind.SUIT:
        return f"{token} (all {rule.suit} wild)"
    if rule.kind == WildKind.SPECIFIC:
        return f"{token} (declared wild)"
    if rule.kind == WildKind.ONE_EYED_JACK:
        return f"{token} (one-eyed jack)"
    if rule.kind == WildKind.SUICIDE_KING:
        return f"{token} (suicide king)"
    return token


def _mode_blurb(mode: WildMode) -> str:
    if mode == WildMode.STRAIGHT_FLUSH_ONLY:
        return "wild only for straights/flushes; otherwise dead"
    if mode == WildMode.BUG:
        return "bug: wild for straights/flushes, otherwise plays as ace"
    return "fully wild"


# ---- hi-only / split / lo-only helpers --------------------------------

def _resolve_high(
    cards: list[PokerCard],
    variant: VariantSpec,
    *,
    hole: Optional[list[PokerCard]] = None,
    board: Optional[list[PokerCard]] = None,
) -> HighAnalysis:
    """Build the best high hand under the variant's hand-requirement rule."""
    wild_idx, mode, wild_expl = _wild_indices(cards, variant.wilds)

    # No wilds -> straight evaluator path.
    if not wild_idx:
        if variant.hand == HandRequirement.OMAHA_2_HOLE_3_BOARD and hole and board:
            rank = best_high([], must_use=2, hole=hole, board=board)
        else:
            rank = best_high(cards)
        return _high_analysis_from_rank(rank, "")

    # Wilds present. Iterate over every 5-card combo, evaluate each with
    # wilds, pick the best.
    return _resolve_high_with_wilds(cards, variant, mode, wild_expl, hole, board)


def _resolve_high_with_wilds(
    cards: list[PokerCard],
    variant: VariantSpec,
    mode: WildMode,
    wild_expl: str,
    hole: Optional[list[PokerCard]],
    board: Optional[list[PokerCard]],
) -> HighAnalysis:
    if variant.hand == HandRequirement.OMAHA_2_HOLE_3_BOARD and hole and board:
        candidates = []
        for h in combinations(hole, 2):
            for b in combinations(board, 3):
                candidates.append(list(h) + list(b))
    else:
        candidates = [list(c) for c in combinations(cards, 5)]

    best: Optional[HandRank] = None
    for combo in candidates:
        wild_in_combo = [i for i, x in enumerate(combo) if isinstance(x, Joker) or _is_marked_wild(x, variant.wilds)]
        if wild_in_combo:
            rank = evaluate_with_wilds(combo, wild_indices=wild_in_combo, mode=mode)
        else:
            rank = classify_high(combo)
        if best is None or rank > best:
            best = rank
    assert best is not None
    return _high_analysis_from_rank(best, wild_expl)


def _is_marked_wild(card: Card, rules: list[WildRule]) -> bool:
    return any(_matches(card, r) for r in rules)


def _high_analysis_from_rank(rank: HandRank, wild_expl: str) -> HighAnalysis:
    return HighAnalysis(
        cls_name=HAND_CLASS_NAMES[int(rank.cls)],
        cls_value=int(rank.cls),
        tiebreakers=rank.tiebreakers,
        cards=[poker_card_to_token(c) for c in rank.cards],
        explanation=_explain_high(rank, wild_expl),
    )


def _explain_high(rank: HandRank, wild_expl: str) -> str:
    base = HAND_CLASS_NAMES[int(rank.cls)]
    detail = ""
    if rank.cls == HandClass.STRAIGHT or rank.cls == HandClass.STRAIGHT_FLUSH:
        detail = f" ({_short_rank(rank.tiebreakers[0])}-high)"
    elif rank.cls == HandClass.FULL_HOUSE:
        detail = f" ({_short_rank(rank.tiebreakers[0])}s full of {_short_rank(rank.tiebreakers[1])}s)"
    elif rank.cls == HandClass.FOUR_OF_A_KIND:
        detail = f" (quad {_short_rank(rank.tiebreakers[0])}s)"
    elif rank.cls == HandClass.FIVE_OF_A_KIND:
        detail = f" ({_short_rank(rank.tiebreakers[0])}s)"
    elif rank.cls == HandClass.PAIR:
        detail = f" of {_short_rank(rank.tiebreakers[0])}s"
    elif rank.cls == HandClass.TWO_PAIR:
        detail = f" ({_short_rank(rank.tiebreakers[0])}s and {_short_rank(rank.tiebreakers[1])}s)"
    if wild_expl:
        return f"{base}{detail} | wilds: {wild_expl}"
    return f"{base}{detail}"


def _short_rank(v: int) -> str:
    if v == 14:
        return "A"
    if v == 13:
        return "K"
    if v == 12:
        return "Q"
    if v == 11:
        return "J"
    if v == 10:
        return "T"
    return str(v)


# ---- low resolution ---------------------------------------------------

def _resolve_low(
    cards: list[PokerCard],
    variant: VariantSpec,
    *,
    hole: Optional[list[PokerCard]] = None,
    board: Optional[list[PokerCard]] = None,
) -> Optional[LowAnalysis]:
    if variant.lo_rule is None:
        return None

    # Lows ignore wild substitution by convention (the variants we support
    # don't pair wilds with low evaluation). If a variant ever needs that,
    # phase 4's wild rule builder can opt into it.
    if variant.hand == HandRequirement.OMAHA_2_HOLE_3_BOARD and hole and board:
        # Best 2+3 low: try every 2-from-hole + 3-from-board combo.
        best: Optional[LowRank] = None
        for h in combinations(hole, 2):
            for b in combinations(board, 3):
                candidate = list(h) + list(b)
                lr = best_low(
                    candidate, variant.lo_rule,
                    eight_or_better=variant.lo_eight_or_better,
                )
                if lr.qualifies and (best is None or lr.ranks < best.ranks):
                    best = lr
        if best is None:
            best = LowRank(variant.lo_rule, False, ())
    else:
        best = best_low(
            cards, variant.lo_rule,
            eight_or_better=variant.lo_eight_or_better,
        )

    return LowAnalysis(
        qualifies=best.qualifies,
        rule=variant.lo_rule.value,
        name=best.name or "no qualifying low",
        cards=[poker_card_to_token(c) for c in best.cards],
        explanation=_explain_low(variant, best),
    )


def _explain_low(variant: VariantSpec, low: LowRank) -> str:
    rule_blurb = {
        LowRule.ACE_TO_FIVE: (
            "Ace-to-five low. Aces play low; straights and flushes don't count; pairs disqualify."
        ),
        LowRule.DEUCE_TO_SEVEN: (
            "Deuce-to-seven low. Aces play HIGH; straights and flushes count AGAINST you."
        ),
        LowRule.BADUGI: (
            "Badugi: 4 cards of distinct ranks AND distinct suits. Pairs and matching suits 'kill' the higher card."
        ),
    }
    base = rule_blurb.get(variant.lo_rule, "Low.")
    qualifier = ""
    if variant.lo_rule == LowRule.ACE_TO_FIVE and variant.lo_eight_or_better:
        qualifier = " 8-or-better qualifier: 5 unpaired cards 8-or-below required."
    if not low.qualifies:
        return f"{base}{qualifier} You don't have a qualifying low."
    return f"{base}{qualifier} Your best: {low.name}."


# ---- hi/lo explanations ----------------------------------------------

def _hi_lo_explanation(variant: VariantSpec) -> str:
    if variant.hi_lo == HiLoSplit.HI_ONLY:
        return "High hand wins the pot."
    if variant.hi_lo == HiLoSplit.LO_ONLY:
        return "Low hand wins the pot. No high split."
    if variant.lo_rule and variant.lo_eight_or_better:
        return (
            "Pot splits between best high and best 8-or-better low. "
            "If no player makes a qualifying low, high takes all."
        )
    return "Pot splits between best high and best low (no qualifier — there will always be a low)."


def _hands_that_beat(rank: HandRank) -> list[str]:
    return [
        HAND_CLASS_NAMES[int(c)]
        for c in HandClass
        if int(c) > int(rank.cls)
    ]


# ---- public entry point ----------------------------------------------

def analyze(
    variant: VariantSpec,
    cards: list[PokerCard],
    *,
    hole: Optional[list[PokerCard]] = None,
    board: Optional[list[PokerCard]] = None,
) -> CompanionAnalysis:
    """Build a companion-mode analysis for the user's hand under `variant`.

    For Omaha-style 2+3 variants, pass `hole` and `board` separately. For
    every other variant, just pass `cards` (a flat list of everything the
    player can see).
    """
    if variant.hand == HandRequirement.OMAHA_2_HOLE_3_BOARD:
        if hole is None or board is None:
            raise ValueError("Omaha-style variants require hole + board")
        all_cards = list(hole) + list(board)
    else:
        all_cards = list(cards)

    notes: list[str] = []
    hi_a: Optional[HighAnalysis] = None
    lo_a: Optional[LowAnalysis] = None
    wild_resolution: Optional[str] = None

    if variant.hi_lo != HiLoSplit.LO_ONLY:
        hi_a = _resolve_high(all_cards, variant, hole=hole, board=board)
        if hi_a.explanation and "wilds:" in hi_a.explanation:
            wild_resolution = hi_a.explanation.split("wilds:", 1)[1].strip()

    if variant.hi_lo in (HiLoSplit.LO_ONLY, HiLoSplit.SPLIT) and variant.lo_rule:
        lo_a = _resolve_low(all_cards, variant, hole=hole, board=board)

    hands_that_beat: list[str] = []
    if hi_a is not None:
        hands_that_beat = [n for n in _hands_that_beat(_synthetic_rank(hi_a.cls_value))]

    if variant.notes:
        notes.append(variant.notes)

    return CompanionAnalysis(
        variant_name=variant.name,
        user_cards=[poker_card_to_token(c) for c in all_cards],
        hi=hi_a,
        lo=lo_a,
        hi_lo_explanation=_hi_lo_explanation(variant),
        wild_resolution=wild_resolution,
        hands_that_beat_you=hands_that_beat,
        notes=notes,
    )


def _synthetic_rank(cls_value: int) -> HandRank:
    return HandRank(HandClass(cls_value), (), ())
