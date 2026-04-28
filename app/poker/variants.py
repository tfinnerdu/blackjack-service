"""Poker variant DSL.

A VariantSpec captures every dimension that distinguishes one poker game
from another:

  - Deck composition (cards + jokers)
  - Deal scheme (hole cards, community board layout, stud up-cards, draws)
  - Wild rules (which cards are wild, and HOW — full / SF-only / bug)
  - Hand-requirement rule (use any 5, Omaha-style 2+3, draw-only, badugi)
  - Hi/lo split + low rule + low qualifier

The library at the bottom of this file ships ~20 canonical variants. The
dealer's-choice oddballs (Anaconda, Follow the Queen, Ice Age, etc.)
extend the same dataclasses with their quirky deal/wild rules instead of
forking new types.

Triggered wilds (e.g. 'after a Queen is dealt face-up, the next card is
wild') and pass-the-trash mechanics live in `wilds.py` (extension) and
`engine.py` (deal loop) respectively — phase 4 + 6.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional

from .deck import DeckSpec
from .evaluator.low import LowRule
from .evaluator.wilds import WildMode


class HandRequirement(str, Enum):
    """How the player builds their best 5-card hand."""

    BEST_5_OF_ALL = "best_5_of_all"               # Hold'em, 7-Card Stud, draw
    OMAHA_2_HOLE_3_BOARD = "omaha_2_hole_3_board"  # Omaha (and Hi/Lo)
    EXACTLY_5_HOLE = "exactly_5_hole"             # 5-card draw / stud (5)
    BADUGI_4_OF_HOLE = "badugi_4_of_hole"         # Badugi
    EXACTLY_4_HOLE = "exactly_4_hole"             # rare home variants


class HiLoSplit(str, Enum):
    HI_ONLY = "hi_only"
    LO_ONLY = "lo_only"
    SPLIT = "split"            # pot splits if a qualifying low exists


class WildKind(str, Enum):
    JOKER = "joker"            # any joker in the deck
    RANK = "rank"              # all cards of a given rank (e.g. deuces)
    SUIT = "suit"              # all cards of a given suit (rare)
    SPECIFIC = "specific"      # one specific card token (e.g. JS)
    ONE_EYED_JACK = "one_eyed_jack"
    SUICIDE_KING = "suicide_king"
    KINGS_AND_LITTLE_ONE = "kings_and_little_one"  # kings + lowest hole card


@dataclass
class WildRule:
    kind: WildKind
    mode: WildMode = WildMode.FULLY_WILD
    rank: Optional[str] = None      # for kind=RANK (e.g. '2')
    suit: Optional[str] = None      # for kind=SUIT (e.g. 'H')
    card_token: Optional[str] = None  # for kind=SPECIFIC

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DealScheme:
    """The dealing pattern for a variant.

    - hole_cards: initial cards dealt face-down to each player
    - up_cards: initial cards dealt face-up (stud-style)
    - community_streets: list of group sizes for community cards.
      Hold'em is [3, 1, 1] (flop, turn, river). Omaha matches.
      Plain 7-stud has none (cards come from the player's own up-cards).
    - stud_streets: list of group sizes of additional UP-cards dealt to
      each player after the initial deal. 7-stud is [1, 1, 1, 1] (4th, 5th,
      6th, 7th — the last is dealt down).
    - down_streets: optional face-down cards dealt mid-hand (7-stud's 7th).
    - draws: list of draw-round descriptions; each int is the maximum
      cards each player may exchange that round.
    - stud_face_down_final: True if the last stud card is dealt face-down
      (standard 7-stud).
    """
    hole_cards: int = 0
    up_cards: int = 0
    community_streets: list[int] = field(default_factory=list)
    stud_streets: list[int] = field(default_factory=list)
    stud_face_down_final: bool = False
    draws: list[int] = field(default_factory=list)

    def total_cards_per_player(self) -> int:
        return self.hole_cards + self.up_cards + sum(self.stud_streets)


@dataclass
class VariantSpec:
    name: str
    description: str
    family: str   # 'holdem', 'omaha', 'stud', 'draw', 'badugi', 'home'
    deck: DeckSpec = field(default_factory=lambda: DeckSpec(decks=1, jokers=0))
    deal: DealScheme = field(default_factory=DealScheme)
    wilds: list[WildRule] = field(default_factory=list)
    hand: HandRequirement = HandRequirement.BEST_5_OF_ALL
    hi_lo: HiLoSplit = HiLoSplit.HI_ONLY
    lo_rule: Optional[LowRule] = None
    lo_eight_or_better: bool = False
    notes: str = ""

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "description": self.description,
            "family": self.family,
            "deck": {"decks": self.deck.decks, "jokers": self.deck.jokers},
            "deal": {
                "hole_cards": self.deal.hole_cards,
                "up_cards": self.deal.up_cards,
                "community_streets": list(self.deal.community_streets),
                "stud_streets": list(self.deal.stud_streets),
                "stud_face_down_final": self.deal.stud_face_down_final,
                "draws": list(self.deal.draws),
            },
            "wilds": [w.to_dict() for w in self.wilds],
            "hand": self.hand.value,
            "hi_lo": self.hi_lo.value,
            "lo_rule": self.lo_rule.value if self.lo_rule else None,
            "lo_eight_or_better": self.lo_eight_or_better,
            "notes": self.notes,
        }
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "VariantSpec":
        deck = DeckSpec(
            decks=int(d["deck"]["decks"]),
            jokers=int(d["deck"]["jokers"]),
        )
        deal_d = d.get("deal", {})
        deal = DealScheme(
            hole_cards=int(deal_d.get("hole_cards", 0)),
            up_cards=int(deal_d.get("up_cards", 0)),
            community_streets=list(deal_d.get("community_streets", [])),
            stud_streets=list(deal_d.get("stud_streets", [])),
            stud_face_down_final=bool(deal_d.get("stud_face_down_final", False)),
            draws=list(deal_d.get("draws", [])),
        )
        wilds = [
            WildRule(
                kind=WildKind(w["kind"]),
                mode=WildMode(w["mode"]),
                rank=w.get("rank"),
                suit=w.get("suit"),
                card_token=w.get("card_token"),
            )
            for w in d.get("wilds", [])
        ]
        lo_rule = LowRule(d["lo_rule"]) if d.get("lo_rule") else None
        return cls(
            name=d["name"],
            description=d.get("description", ""),
            family=d.get("family", "home"),
            deck=deck,
            deal=deal,
            wilds=wilds,
            hand=HandRequirement(d.get("hand", "best_5_of_all")),
            hi_lo=HiLoSplit(d.get("hi_lo", "hi_only")),
            lo_rule=lo_rule,
            lo_eight_or_better=bool(d.get("lo_eight_or_better", False)),
            notes=d.get("notes", ""),
        )


# ---- variant library ---------------------------------------------------

def _holdem() -> VariantSpec:
    return VariantSpec(
        name="Texas Hold'em",
        description="Two hole cards + five community cards. Make the best 5-card hand.",
        family="holdem",
        deal=DealScheme(hole_cards=2, community_streets=[3, 1, 1]),
        hand=HandRequirement.BEST_5_OF_ALL,
        notes="No limit, pot limit, or limit betting structures all use the same deal.",
    )


def _omaha_high() -> VariantSpec:
    return VariantSpec(
        name="Omaha",
        description="Four hole cards + five community cards. Must use exactly 2 from hole + 3 from board.",
        family="omaha",
        deal=DealScheme(hole_cards=4, community_streets=[3, 1, 1]),
        hand=HandRequirement.OMAHA_2_HOLE_3_BOARD,
    )


def _omaha_hilo() -> VariantSpec:
    return VariantSpec(
        name="Omaha Hi/Lo (8 or better)",
        description="Omaha rules; pot splits between best high and best 8-or-better low. No qualifier = high takes all.",
        family="omaha",
        deal=DealScheme(hole_cards=4, community_streets=[3, 1, 1]),
        hand=HandRequirement.OMAHA_2_HOLE_3_BOARD,
        hi_lo=HiLoSplit.SPLIT,
        lo_rule=LowRule.ACE_TO_FIVE,
        lo_eight_or_better=True,
        notes="A-5 low; pairs disqualify; you can use a different 2+3 combo for hi vs lo.",
    )


def _seven_stud() -> VariantSpec:
    return VariantSpec(
        name="7-Card Stud",
        description="Two down + 1 up to start; one up each on 4th/5th/6th; final card down. Best 5 of 7.",
        family="stud",
        deal=DealScheme(
            hole_cards=2, up_cards=1,
            stud_streets=[1, 1, 1, 1],
            stud_face_down_final=True,
        ),
        hand=HandRequirement.BEST_5_OF_ALL,
    )


def _seven_stud_hilo() -> VariantSpec:
    return VariantSpec(
        name="7-Card Stud Hi/Lo (8 or better)",
        description="7-Stud rules; pot splits between best high and best 8-or-better low.",
        family="stud",
        deal=DealScheme(
            hole_cards=2, up_cards=1,
            stud_streets=[1, 1, 1, 1],
            stud_face_down_final=True,
        ),
        hand=HandRequirement.BEST_5_OF_ALL,
        hi_lo=HiLoSplit.SPLIT,
        lo_rule=LowRule.ACE_TO_FIVE,
        lo_eight_or_better=True,
    )


def _razz() -> VariantSpec:
    return VariantSpec(
        name="Razz",
        description="7-Stud lowball: ace-to-five low only. Lowest hand wins; pairs disqualify only if they raise the high.",
        family="stud",
        deal=DealScheme(
            hole_cards=2, up_cards=1,
            stud_streets=[1, 1, 1, 1],
            stud_face_down_final=True,
        ),
        hand=HandRequirement.BEST_5_OF_ALL,
        hi_lo=HiLoSplit.LO_ONLY,
        lo_rule=LowRule.ACE_TO_FIVE,
        lo_eight_or_better=False,
    )


def _five_card_draw() -> VariantSpec:
    return VariantSpec(
        name="5-Card Draw",
        description="5 hole cards, one draw round (replace up to 5).",
        family="draw",
        deal=DealScheme(hole_cards=5, draws=[5]),
        hand=HandRequirement.EXACTLY_5_HOLE,
    )


def _two_seven_triple_draw() -> VariantSpec:
    return VariantSpec(
        name="2-7 Triple Draw",
        description="5 hole cards, three draw rounds; deuce-to-seven low (A high, straights/flushes count).",
        family="draw",
        deal=DealScheme(hole_cards=5, draws=[5, 5, 5]),
        hand=HandRequirement.EXACTLY_5_HOLE,
        hi_lo=HiLoSplit.LO_ONLY,
        lo_rule=LowRule.DEUCE_TO_SEVEN,
    )


def _badugi() -> VariantSpec:
    return VariantSpec(
        name="Badugi",
        description="4 hole cards, three draw rounds. Best 4-card badugi (distinct ranks + distinct suits) wins.",
        family="badugi",
        deal=DealScheme(hole_cards=4, draws=[4, 4, 4]),
        hand=HandRequirement.BADUGI_4_OF_HOLE,
        hi_lo=HiLoSplit.LO_ONLY,
        lo_rule=LowRule.BADUGI,
    )


def _follow_the_queen() -> VariantSpec:
    return VariantSpec(
        name="Follow the Queen",
        description="7-Stud variant. Queens are wild, and the next card dealt face-up after a Queen is also wild (until the next Queen comes out).",
        family="home",
        deal=DealScheme(
            hole_cards=2, up_cards=1,
            stud_streets=[1, 1, 1, 1],
            stud_face_down_final=True,
        ),
        wilds=[WildRule(kind=WildKind.RANK, rank="Q", mode=WildMode.FULLY_WILD)],
        hand=HandRequirement.BEST_5_OF_ALL,
        notes="The 'follow' part is a triggered wild — phase 4 wires the dynamic 'next card after Q' rule into the deal loop. v1 treats only Queens as wild.",
    )


def _baseball() -> VariantSpec:
    return VariantSpec(
        name="Baseball",
        description="7-Stud variant. 3s and 9s wild; a face-up 4 entitles the player to one extra card.",
        family="home",
        deal=DealScheme(
            hole_cards=2, up_cards=1,
            stud_streets=[1, 1, 1, 1],
            stud_face_down_final=True,
        ),
        wilds=[
            WildRule(kind=WildKind.RANK, rank="3", mode=WildMode.FULLY_WILD),
            WildRule(kind=WildKind.RANK, rank="9", mode=WildMode.FULLY_WILD),
        ],
        hand=HandRequirement.BEST_5_OF_ALL,
        notes="The bonus card on a face-up 4 is a deal-loop rule (phase 6).",
    )


def _anaconda() -> VariantSpec:
    return VariantSpec(
        name="Anaconda (Pass the Trash)",
        description="7 cards, three passing rounds (3 left, 2 right, 1 left), then declare and roll your final 5.",
        family="home",
        deal=DealScheme(hole_cards=7),
        hand=HandRequirement.BEST_5_OF_ALL,
        notes="Passing mechanics live in the deal loop (phase 6). Companion mode evaluates the chosen 5.",
    )


def _ice_age() -> VariantSpec:
    return VariantSpec(
        name="Ice Age",
        description="3s, 6s, 9s, and 12s (queens) all wild — 16 wild cards in the deck.",
        family="home",
        deal=DealScheme(hole_cards=2, community_streets=[3, 1, 1]),
        wilds=[
            WildRule(kind=WildKind.RANK, rank="3", mode=WildMode.FULLY_WILD),
            WildRule(kind=WildKind.RANK, rank="6", mode=WildMode.FULLY_WILD),
            WildRule(kind=WildKind.RANK, rank="9", mode=WildMode.FULLY_WILD),
            WildRule(kind=WildKind.RANK, rank="Q", mode=WildMode.FULLY_WILD),
        ],
        hand=HandRequirement.BEST_5_OF_ALL,
    )


def _high_chicago() -> VariantSpec:
    return VariantSpec(
        name="High Chicago",
        description="7-Stud, but the highest spade in the hole splits the pot with the high hand.",
        family="home",
        deal=DealScheme(
            hole_cards=2, up_cards=1,
            stud_streets=[1, 1, 1, 1],
            stud_face_down_final=True,
        ),
        hand=HandRequirement.BEST_5_OF_ALL,
        notes="Special-pot rule (high-spade-in-hole) is a phase-6 settlement layer.",
    )


def _low_chicago() -> VariantSpec:
    return VariantSpec(
        name="Low Chicago",
        description="7-Stud, but the lowest spade in the hole splits the pot with the high hand.",
        family="home",
        deal=DealScheme(
            hole_cards=2, up_cards=1,
            stud_streets=[1, 1, 1, 1],
            stud_face_down_final=True,
        ),
        hand=HandRequirement.BEST_5_OF_ALL,
    )


def _holdem_53_joker_sf_only() -> VariantSpec:
    """The user's home-game version of hold'em: 53-card deck where the joker
    is wild only for completing straights and flushes."""
    return VariantSpec(
        name="Hold'em (53-card, joker S/F only)",
        description="Texas Hold'em with one joker added. Joker is wild ONLY when it completes a straight, flush, or straight flush; otherwise dead.",
        family="holdem",
        deck=DeckSpec(decks=1, jokers=1),
        deal=DealScheme(hole_cards=2, community_streets=[3, 1, 1]),
        wilds=[WildRule(kind=WildKind.JOKER, mode=WildMode.STRAIGHT_FLUSH_ONLY)],
        hand=HandRequirement.BEST_5_OF_ALL,
        notes="Matches the user's home-game rule. The wild substitution is partial — see evaluator/wilds.py.",
    )


def all_variants() -> list[VariantSpec]:
    """Built-in variant library. The wild rule builder + import flow extend
    this; user-saved variants live in SettingsTemplate rows with
    game_type='poker'."""
    return [
        _holdem(),
        _holdem_53_joker_sf_only(),
        _omaha_high(),
        _omaha_hilo(),
        _seven_stud(),
        _seven_stud_hilo(),
        _razz(),
        _five_card_draw(),
        _two_seven_triple_draw(),
        _badugi(),
        _follow_the_queen(),
        _baseball(),
        _anaconda(),
        _ice_age(),
        _high_chicago(),
        _low_chicago(),
    ]


__all__ = [
    "DealScheme",
    "HandRequirement",
    "HiLoSplit",
    "VariantSpec",
    "WildKind",
    "WildRule",
    "all_variants",
]
