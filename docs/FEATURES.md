# Blackjack Trainer — What It Does

A web-based blackjack trainer you can play on your phone. Built so you can
recreate the **exact** game you'd sit down to in a casino, then see —
hand by hand — how your decisions stacked up against perfect play.

Not another "level up and we'll hand you free chips" phone game. Your
bankroll is your bankroll. When you bust, you bust.

---

## Build your table

Set up the game the way the casino runs it:

- **Decks:** 1 through 8 (single-deck, double-deck, 6-deck shoe, 8-deck, etc.)
- **Shuffle style:** casino shoe with a cut-card (you pick how deep before
  reshuffle), continuous shuffler (CSM), or hand-shuffled
- **Seats at the table:** 1 to 7 — and you pick which seat you sit in
  (first base, third base, anywhere in between)
- **Dealer rules:** hits soft 17 or stands, peeks for blackjack or not,
  European no-hole-card
- **Player rules (all toggleable):**
  - Blackjack payout: 3:2, 6:5, 2:1, 1:1
  - Double down: any two cards / 9-10-11 only / 10-11 only
  - Double after split (yes/no)
  - Resplit aces (yes/no)
  - Hit split aces (yes/no)
  - Surrender: none / late / early
  - Insurance offered (yes/no)
- **Side bets, all toggleable, all with configurable payouts:**
  21+3, Perfect Pairs, Lucky Ladies, Royal Match, Match the Dealer,
  Over/Under 13, Bust It, Buster Blackjack
- **Money rules:** starting bankroll, min bet, max bet, bet increment

---

## Save your favorite setups

Spent ten minutes dialing in your home casino's exact rules? Save it as a
**template**. Next session, pick the template and you're at the table in two
taps. Built-in templates ship with the app:

- Vegas Strip — 6:5, H17
- Vegas Downtown — 3:2, S17
- Single-Deck — 3:2, H17
- European No-Hole-Card

Your custom templates sit alongside them. Edit, clone, delete any time.

---

## Other players at the table actually play

Each AI seat has its own playstyle so the table feels real and the cards
that come out of the shoe match what you'd see in a real game:

- **By the Book** — perfect basic strategy
- **Card Counter** — Hi-Lo + index plays, varies bets with the count
- **Tight** — never doubles, never splits except aces and 8s, scared of busting
- **Aggressive** — doubles everything, splits everything, lives loud
- **Mimic Dealer** — just hits to 17 like the dealer
- **Hunch** — looks human, makes occasional mistakes
- **Drunk** — book play with a configurable mistake rate
- **Superstitious** — won't hit 16 vs 10, splits 10s when "running hot"
- **Streaky** — presses bets after wins, pulls back after losses

Each AI seat also picks a **bet pattern** (flat, Martingale, Anti-Martingale,
Oscar's Grind, count-based spread, random) and starts with its own bankroll.
When they bust, they leave the table — or rebuy, your call.

---

## The coach

Toggle on the "show me the book" panel and every hand it tells you what
basic strategy says, *for the rule set you're playing*. Wrong rules = wrong
chart, so the trainer regenerates the book to match.

Counting on? You'll see your **running count** and **true count** live, plus
the standard deviation plays (Illustrious 18 + Fab 4) when the count says
you should depart from basic strategy.

Don't want hints during the hand? Hide the panel. Mistakes still get
logged silently and shown in the post-session report.

---

## Your stats, by session and lifetime

After every hand and at the end of every session:

- Your money vs. **what-if-book** money — what you'd have if you'd played
  every hand the way the book says
- Win rate, push rate, blackjack rate, bust rate
- Hands per hour
- EV (expected value) lost to mistakes — in dollars
- If counting is on: did your bets match the count? Did you make the right
  index deviations?
- Hand-by-hand history — every decision, what the book said, what you did,
  what it cost (or earned) you

---

## Sessions are real sessions

You pick a starting bankroll. That's it. No bonus chips, no "level up to
unlock $500 free." When you reload the app mid-shoe:

- **Resume exactly** — same shoe, same count, same seat, right where you
  left off
- **Reset and reshuffle** — keep your bankroll and stats, but get a fresh
  shoe (for when you want to "step away from the table" and come back fresh)

---

## Built for your phone

- Designed mobile-first — works at iPhone SE width on up
- Action buttons (hit/stand/double/split/surrender/insurance) live at the
  bottom where your thumb already is
- Install to home screen and it runs full-screen like a real app
- No double-tap-zoom traps, no hover-only menus, no bouncy scroll on the table
