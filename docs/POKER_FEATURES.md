# Poker Companion — What It Does Right Now

A web companion you use **at the table** during poker night. Pick the
variant, tap your cards, and it tells you exactly where you stand:
- your best **high** hand
- your best **low** hand if the variant has one
- whether your low **qualifies** (and why, in plain English)
- how the **pot splits** (high-only / low-only / 8-or-better / etc.)
- which cards in your hand are **wild** and how
- which hand classes still **beat you**

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
all marked cards are treated as fully wild. The wild rule builder for
custom variants (triggered wilds, after-queen, declared-wild-on-the-fly)
ships next phase.

---

## What's coming next

- **Wild rule builder** UI: declare your own wilds for custom variants
- **Triggered wilds**: "after a Queen face-up, the next card is wild" type
  rules baked into the deal loop
- **Saved variants**: punch in a new variant once, save it, pick it next
  poker night
- **Simulator mode** with AI opponents: full deal/state machine + bot
  bets/folds for the variants we've shipped, so the trainer side of the
  app catches up to the helper side
- **Equity calculator**: "how often do I win this hand to the river?"
  Monte Carlo against random opponents

---

## Built for the phone

- 375px floor (iPhone SE on up). Card picker uses 44px touch targets.
- No double-tap zoom traps; no hover-only menus.
- Safe-area aware so the iOS home-indicator doesn't crop the analyze button.
- Works as a PWA — install to home screen, launches full-screen.
