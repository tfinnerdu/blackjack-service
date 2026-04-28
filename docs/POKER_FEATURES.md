# Poker — Companion + Simulator

Two modes:

- **Companion** — at the table, with real cards. Pick a variant, tap your
  hand, see your best high + low + the hi/lo split rule + which hand
  classes still beat you. Useful in your hand when the dealer says
  "Anaconda Hi/Lo, low qualifies at 8" and you have to figure out what
  qualifies.
- **Simulator** — solo trainer. Sit down at a table with personality
  bots, real chip stacks, real blinds, and play out hands of Hold'em
  (or the home-game 53-card joker version) until you bust or quit.

Built mobile-first so your phone fits between the chips and the cards.

---

## Variants live right now (16)

**Modern table games**
- Texas Hold'em
- Texas Hold'em (53-card, joker S/F only) — the home-game version where
  the joker is wild only when it completes a straight or flush, otherwise
  dead
- Omaha
- Omaha Hi/Lo (8 or better)

**Stud family**
- 7-Card Stud
- 7-Card Stud Hi/Lo (8 or better)
- Razz (lo-only ace-to-five)

**Draw + Badugi**
- 5-Card Draw
- 2-7 Triple Draw
- Badugi

**Dealer's-choice favorites**
- Follow the Queen
- Baseball (3s + 9s wild)
- Anaconda / Pass-the-Trash
- Ice Age (3s, 6s, 9s, Qs all wild — 16 wild cards)
- High Chicago (high spade in hole)
- Low Chicago (low spade in hole)

The full variant data (deck size, deal scheme, wild rules, hand
requirement, hi/lo split, low rule) round-trips through JSON, so any
variant from your buddy's 100+ book can be added later.

---

## How the helper actually helps with hi/lo

The thing that trips people up about hi/lo isn't who *wins* — it's why
their "low" doesn't qualify. The companion calls it out plainly:

- **Ace-to-five low** (Omaha Hi/Lo, Stud Hi/Lo, Razz): aces play LOW;
  straights and flushes don't count against you; pairs disqualify. Best
  low is the wheel A-2-3-4-5.
- **Deuce-to-seven low** (2-7 Triple Draw): aces play HIGH; straights AND
  flushes count *against* you. Best low is 7-5-4-3-2 unsuited.
- **Badugi**: 4 cards across 4 different ranks AND 4 different suits.
  Pairs and matching-suit pairs each "kill" the higher of the two.

If you don't have a qualifying low, it says so and explains why.

---

## Wild rules

Your home-game rule — joker wild **only** for straights and flushes —
is built in. The evaluator tries every substitution that could complete a
straight, flush, or straight flush; if none exist, the joker goes dead
(no pair, no kicker bonus). The result panel calls out which cards in
your hand are wild and how they're being treated.

For variants with rank-based wilds (Baseball, Ice Age, Follow the Queen),
all marked cards are treated as fully wild.

## Saving custom variants

Your buddy's 100+ variant book has somewhere to live now:

- Pick any built-in variant in the companion → **Clone** → tweak the
  JSON to taste → **Save**. The new variant shows up in the picker
  alongside the built-ins for the next hand.
- **+ New** opens the editor with a blank-slate template you can paste
  a variant into.
- **Delete** removes a saved variant. Built-ins are read-only.

The JSON shape mirrors `VariantSpec` exactly — deck composition, deal
scheme (hole / community / stud / draws), wild rules, hand requirement,
hi/lo split, low rule + qualifier. Anything the engine supports is
expressible as JSON.

A friendlier form-based wild rule builder is on the list (current editor
is JSON-only, which works for a typed user but isn't tap-friendly).

---

## Simulator mode (now live)

Companion's the helper at the table. Simulator's the trainer when nobody's
around to deal you a hand.

- **Hold'em + the home-game 53-card joker variant** are playable end-to-end
  against AI opponents. Heads-up, full ring, anywhere in between.
- **9 AI personalities** — pick any combination, name each opponent
  whatever you want:

  | Personality | Behavior |
  |---|---|
  | **Book** | Tight-aggressive baseline. Folds bad, bets/raises good. |
  | **Tight** | Scared, only premium hands. Folds to pressure. |
  | **Loose** | Calls a lot. Doesn't fold to small bets. |
  | **Aggressive** | Maniac. Raises constantly. |
  | **Calling station** | Calls everything. Never raises. |
  | **Bluffer** | Book strength most of the time, ~25% river bluff frequency on weak hands. |
  | **Hot/cold** | Modulates by recent profit streak. Presses when up, tightens when down. |
  | **Drunk** | Book play with a configurable mistake rate. |
  | **Mimic** | Always check/call minimum. Never raises, rarely folds. |

- **Real chip stacks**, blinds, side pots when someone is all-in.
  No bonus chips, no level-up nonsense. When you're out of stack, you're out.

The simulator uses simple hand-strength heuristics rather than a full
equity calculator. That's by design — these bots are recognizable
archetypes (your buddy who calls everything, your buddy who bluffs every
river), not GTO solvers. You're meant to learn how to *adjust to
different player types*, not to beat a Monte Carlo simulator.

## Per-hand wild marking (now live)

Dealer at your home game says "follow the queen" or "all kings wild
this hand only"? You don't have to save a new variant.

- Tap **Mark cards wild for this hand…** in the companion
- Tap any of the chips in your hand / hole / board to toggle wild
- Hit Analyze — the helper treats those cards as wild for THIS hand
  and explains the resolution alongside any always-wild rules from the
  variant itself

## Equity (now live)

Below the analysis panel, set how many opponents you're up against and
hit Run. Monte Carlo runs 2000 simulations against random hole cards
and complete boards, returns:

- **Win %** — how often you win outright
- **Tie %** — split pots
- **Loss %** — opponent has the better hand
- **Equity %** — wins + half-ties; the standard "what's my share of
  the pot" number

Hold'em + Omaha only for now (community-card variants without wilds).
Wild variants stay in companion mode where the substitution gets the
care it needs.

## Form-based variant builder (now live)

Saved variants used to need raw JSON. Now there's a structured form:

- Identity / family
- Deck size + jokers (steppers)
- Deal scheme (hole, up, community streets, stud streets, draws)
- **Wild rules**: inline list with kind dropdown (joker / rank / suit /
  specific card / one-eyed jack / suicide king), mode dropdown (fully
  wild / S/F-only / bug), and contextual rank/suit/card pickers per
  kind
- Hand requirement, hi/lo split, low rule, 8-or-better qualifier
- Notes

Power users can flip to JSON view via the header toggle for full
control.

## What's coming next

- **Triggered wilds**: "after a Queen face-up, the next card is wild"
  type rules baked into the deal loop. The companion handles the
  static-cards-marked-wild case via tap-mark; truly dynamic rules
  baked into a saved variant are still pending.
- **Stud + draw simulators**: 7-Stud, Razz, 5-Card Draw, 2-7 Triple
  Draw. Each needs its own state machine — Hold'em's was first because
  it's the most common.
- **Per-personality stats** in the simulator: track your win rate
  against each archetype so you know which players you're crushing
  and which are crushing you.
- **Equity for stud / draw / wild variants**: the eval engine supports
  all of them; the equity sim's inner loop just needs to integrate
  evaluate_with_wilds + the relevant deal scheme.

---

## Built for the phone

- 375px floor (iPhone SE on up). Card picker uses 44px touch targets.
- No double-tap zoom traps; no hover-only menus.
- Safe-area aware so the iOS home-indicator doesn't crop the analyze button.
- Works as a PWA — install to home screen, launches full-screen.
