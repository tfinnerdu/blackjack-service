# Notes for the next Claude Code session

State of play and the parking lot, written by Claude at the end of the
session that landed the punch-list. Read this first, then `git log
--oneline | head -25` to see what just shipped.

## Current state

- **Branch:** `main` is the only working branch. Pushes redeploy Render.
- **Tests:** 534 backend pytest, frontend typecheck + build clean.
- **Render:** live at the user's blackjack-service URL. gthread workers,
  Postgres free tier. Health = `/health`.
- **Local dev ports:** Flask `5050`, Vite `5174` (project-specific
  exception to the 5800-5899 side-projects range — documented in this
  project, not in `claude.md`).
- **Hostname plumbing:** `start-local.ps1` shows Local / By name /
  Network per the standard; Vite has explicit `allowedHosts`.
- **Migrations:** Flask-Migrate scaffolded with a baseline migration.
  `flask db upgrade` is **commented out** in `render.yaml`'s
  buildCommand. Switching prod to alembic needs the one-time
  `flask db stamp head` step (see `docs/MIGRATIONS.md`).

## Open items the user is aware of (in order)

### 1. ✅ V2 stats features — landed this session

Quote: "I think there's more stats that you could show for a session
such as money made vs what if money playing strictly by the book vs
AI's card counting money and betting."

What shipped:
- **What-if-book bankroll** (`book_bankroll`): every settled round
  re-runs the same shoe state with the human seat playing perfect
  basic strategy. Profit delta accumulates into `book_bankroll`.
  Implementation: `_replay_human_profit` in `app/services/games.py`.
- **AI counter bankroll** (`counter_bankroll`): same replay but with
  Hi-Lo / Illustrious 18 deviations enabled and a count-spread bet
  pattern sized off the human's actual base bet.
- **Time-series chart**: lightweight inline SVG sparkline on the Stats
  page (no new chart-lib dependency). Three lines: you / book /
  counter, anchored by a dashed buy-in line.
- **Persistence**: new `book_bankroll`, `counter_bankroll`,
  `bankroll_history_json` columns on `game_session` with both a
  Flask-Migrate-compatible model definition and a
  `_ensure_columns` shim entry that backfills legacy rows from
  `starting_bankroll`.
- **API**: `/sessions/me/stats` returns `bankrolls.{actual,book,counter,starting}`
  and `bankroll_history` (last 1000 hands).

Tests: `tests/test_bankroll_replay.py` covers initial state, one entry
per hand, exact equality between actual and book when the player
follows book, and that the endpoint surfaces both fields.

Possible follow-ups if asked:
- The replay always uses a 1× spread base equal to the human's bet for
  that hand — if the human is varying their bet wildly, the counter
  comparison is still bet-for-bet. A fairer comparison would use a
  fixed unit. Easy knob.
- AI seats in the replay still play their normal playstyle (random
  RNG fresh per replay). Their actions diverge from the actual round
  but only the human's profit is summed, so this is tolerated noise.

### 2. ✅ Fairness audit — clean

`tests/test_fairness_audit.py` spins up a 6-deck H17 shoe and runs
10,000 always-stand rounds against the engine. Asserts:
  - player BJ rate ≈ 4.75% ± 1%
  - dealer BJ rate ≈ 4.75% ± 1%
  - dealer bust rate ≈ 28.4% ± 2.5%
  - dealer BJ rate when up-card is an Ace ≈ 30.8% ± 5%

Both tests pass — the engine is fair within tolerance. The friend's
63% / 129-hand streak was variance, not bias. Re-run this test if a
similar complaint comes in.

### 3. ✅ Shoe-trace debug logger — landed

`BLACKJACK_SHOE_TRACE=/path/to/trace.jsonl` enables a per-round JSON
Lines append. Each line records the cards dealt to every seat and
the dealer, the running count after the round, the session id, the
shoe seed, and the player outcome. Off by default = zero overhead.
Tests in `tests/test_shoe_trace.py` cover the gate, multi-round
appending, and IO error suppression. To pull a trace from prod: set
the env var on the Render service, ask the user to play, then
download the file.

### 4. Migration switchover (when ready)

In Render's shell:
```
MIGRATING=1 FLASK_APP=wsgi.py flask db stamp head
```
Then uncomment the `flask db upgrade` line in `render.yaml`'s
buildCommand and push. Future schema changes flow through alembic.

### 5. ✅ Form-based blackjack template builder — landed

`client/src/components/BlackjackTemplateBuilder.tsx` mirrors the poker
side's `VariantBuilder`: structured controls for shoe, dealer rules,
payouts, double / split / surrender, money limits, and side-bet
toggles. JSON view stays available via the header toggle. Setup.tsx
passes a draft object to the new editor; the legacy JSON-only sheet is
gone.

### 6. ✅ Room codes + multi-seat — landed (MVP)

Each new session gets a 6-character `room_code` (Crockford-ish
alphabet, no 0/O/1/I/L). The host can share the code or a
`/join/:code` link; visitors see a lobby of bot seats and can claim
any one. Claiming returns a guest token (cookie-set) and converts
that AI seat to a human-controlled seat for the round.

Backend pieces:
- `room_code` + `seat_tokens_json` columns on game_session
- `resolve_seat_for_token` maps any token (host or guest) to (session,
  seat_num). Round-API endpoints route through this so each token can
  only act on its own seat (`take_action` raises if the active seat
  doesn't match).
- `GET /api/v1/sessions/by-code/:code` lobby view
- `POST /api/v1/sessions/by-code/:code/seats/:n/claim` issues a guest
  token + sets the cookie
- `POST /api/v1/sessions/by-code/:code/seats/:n/release` drops a claim
- `/sessions/me` resolves guest tokens too and returns
  `caller_seat` + `caller_is_host` so the UI knows which seat is yours

Frontend pieces:
- `Stats` page shows the room code with copy-code / copy-link buttons
- New `/join` and `/join/:code` routes (the bare `/join` accepts manual
  code entry)
- `Play` page polls `/sessions/me` every 4s and surfaces a toast on
  any seat-token diff (join / leave)
- `Seat` component shows a colored presence dot + Host / Player / Bot
  label per seat; the polling refresh keeps the on-table indicators
  live for everyone at the table.

Open knobs the user might want next:
- Per-guest bet sizing (right now claimed seats use the bot's
  `base_bet`). Add a "your bet" widget to the guest's pre-deal view.
- Last-seen heartbeat per guest so a closed-tab guest's seat shows
  "idle" and the host can kick them.
- WebSockets / SSE for sub-second multi-player updates instead of the
  4-second poll.

### 7. ✅ Casino expansion + fairness fixes — landed

Three new game families and a critical shoe-replay bug fix:

- **Roulette** (`app/roulette/`, `app/services/roulette.py`,
  `app/routes/roulette.py`, `client/src/pages/Roulette.tsx`).
  American + European wheels, full bet table (straight / split /
  street / corner / six-line / dozen / column / red-black / even-odd /
  low-high). 17 engine tests including an empirical 5.26% house-edge
  convergence over 10k spins.
- **Baccarat** (`app/baccarat/`, `app/services/baccarat.py`,
  `app/routes/baccarat.py`, `client/src/pages/Baccarat.tsx`). Punto
  Banco rules with the standard third-card draw table. 16 tests
  including the published 45.86% / 44.62% / 9.52% outcome
  distribution.
- **Craps** (`app/craps/`, `app/services/craps.py`,
  `app/routes/craps.py`, `client/src/pages/Craps.tsx`). Pass /
  Don't Pass + odds + Come / Don't Come + Place + Field + Any-7 /
  Any-Craps + Hardways. 22 tests; pass-line win rate empirically
  matches the 49.29% theoretical figure.
- **Shared `CasinoSession` model**: one row per session, with
  `game_type` discriminator, `state_json` for game-specific state,
  `room_code` for guest invites. Lives in `app/casino/`.

Plus the fairness fixes the user surfaced this session:

- **Shoe-replay bug** — *the* big one. Sessions persisted shoe state as
  `(seed, cards_dealt)` only, so any rebuild *after the first
  reshuffle* rewound the shoe to the initial permutation. Players
  reported "the same hands repeating after a reshuffle." Fixed by
  adding a `shoe_shuffles` counter (incremented when the engine
  reshuffles) and applying that many shuffles to a fresh shoe before
  burning forward. Same fix replicated in the parallel-replay path
  (book/counter bankrolls), the active-round reload path, and
  Baccarat's shoe rebuild. Regression test in
  `tests/test_shoe_persistence.py`.
- **Cut-card jitter** — `Shoe.shuffle()` now picks the cut-card
  position uniformly in `[penetration ± 4%]` so successive shoes
  don't reshuffle at the same physical spot. CSM / hand-shuffle modes
  unaffected.
- **Cut-card / decks display** — Play page header shows `6D` and
  `X to cut` so the player can see how close to a reshuffle they are.

Tests: 496 backend pytest passing (was 428). Frontend typecheck +
build clean. The fairness audit (now 9 tests) covers multi-seed,
single-deck, book-play, rank uniformity, deal order, counter math,
and per-up-card dealer bust rates.

### 8. ✅ Multi-player rooms for casino games + per-guest bets — landed

**Casino multi-player.** `CasinoSession` now stores per-guest state
inside `guest_tokens_json` — each guest has their own bankroll,
pending bets, and history. The host's pending bets live in
`state_json.host_bets`. New helpers in `app/casino/session.py`:
`participants(sess)`, `get_caller_bankroll`, `get_caller_bets`,
`set_caller_bets`, `apply_round_to_participant`.

Each game now uses a stage-then-trigger flow:
- `POST /sessions/me/bets` (anyone): the caller stages their pending
  bets. Validated against the caller's bankroll.
- `POST /sessions/me/spin|play|roll` (host only): resolves every
  participant's pending bets against the same outcome and updates
  each bankroll independently.

Each game's setup screen includes a "Join with code" input so a
guest can drop in via the URL or a typed code. Play pages show a
participants list (with presence dots + per-player bankroll), poll
every 4s for live updates, and gate the trigger button (Spin / Deal
/ Roll) to the host only.

10 backend tests in `tests/test_casino_multiplayer.py` cover join +
seeding, per-participant bet validation, simultaneous settlement,
host-only triggers, and per-guest book persistence in craps.

**Blackjack per-guest bets.** `seat_tokens_json` now stores
`{seat: {token, bet}}` (still backwards-compatible with the legacy
plain-token shape). New endpoint `POST /sessions/me/seat/bet` lets
a guest set their preferred bet for the next round; `start_round`
honors it and falls back to the bot's `base_bet` when unset. Play
page renders a guest-only bet picker for non-host callers.

3 new room-code tests in `tests/test_room_code.py` cover the new
endpoint (set / view / table-limit validation).

### 9. ✅ Sports betting simulator — landed (paper trading)

Paper-trade single bets and parlays against a daily slate of NBA /
NFL / MLB / NHL events. The tool deliberately runs on local
fixtures (no API keys, no rate limits, no scoring delays) so a user
can iterate quickly: place slips, hit "advance day", see how their
strategy actually performed.

**Backend** (`app/sportsbook/`, `app/services/sportsbook.py`,
`app/routes/sportsbook.py`):
- 4 new tables: `SportsbookSession`, `SportsEvent`, `BettingMarket`,
  `BettingSlip`. Events are global by `day` so multiple sessions can
  bet against the same slate.
- `app/sportsbook/odds.py`: American↔decimal conversion, parlay
  decimal-odds product, `settle_slip` with the proper push-leg drop
  semantics (a parlay leg that pushes shrinks the parlay rather
  than killing it; all-push refunds stake).
- `app/sportsbook/fixtures.py`: deterministic slate generator. Picks
  teams from per-sport pools, draws moneyline/spread/total odds in
  realistic ranges, simulates final scores so the markets resolve
  in believable ways.
- `advance_day` resolves every still-scheduled event at `day < new_day`
  and settles every pending slip whose legs are now fully resolved.
  Tops up the future slate so the user always has lookahead games.
- `session_analytics` returns: bankroll / ROI / win rate, per-market-
  type hit rate, single-vs-parlay split, current streak, and a
  "surprising losses" cut (legs at +200 or longer that didn't hit).

**API**:
- `POST /api/v1/sportsbook/sessions` — create + seed a 3-day slate
- `GET /sessions/me` — session view + analytics summary
- `GET /sessions/me/events` — open events + markets
- `GET /sessions/me/slips` — caller's slips (pending + settled)
- `POST /sessions/me/slips` — place single or parlay
- `POST /sessions/me/advance` — bump day, settle, top up slate
- `GET /sessions/me/analytics` — full analytics breakdown

**Frontend** (`client/src/pages/Sportsbook.tsx`): tabbed UI —
Events / Slips / Analytics. Event cards show all three markets with
a tappable selection; tapping toggles a leg in the slip builder.
The slip builder previews combined odds, stake stepper, and
"to win" calculation. Slips tab shows pending + settled with
per-leg outcomes (won/lost/push dot indicators). Analytics tab
shows ROI, hit rate, by-market breakdown, single vs parlay, current
streak, and a surprising-losses list.

**Tests**: 25 in `tests/test_sportsbook.py` covering odds math,
parlay edge cases (loss kills slip, push drops from product, all-push
refund, pending leg keeps slip pending), fixture determinism, end-
to-end advance-day settlement, parlay-same-market guard, and
analytics rollup.

**Future work** (not in scope for this session):
- Wire a real odds-feed (The Odds API has a 500/month free tier).
  Each market already has an `external_id` slot; a thin client
  in `app/sportsbook/feed.py` is the next step.
- Live scores polling instead of pre-rolled fixture scores.
- Prop-bet markets (player points, etc.) — needs a richer market
  schema.

### 10. ✅ Casino visuals — dice, wheel, craps layout, felt tables

Frontend polish that gives each casino game its own physical-feel
visual:

- **`Dice.tsx`** — two SVG dice with proper pip layouts for 1-6.
  When `rolling=true` the displayed values cycle every 100ms and a
  CSS keyframe (`die-tumble` in `index.css`) tumbles each die
  through 2.5 turns over 1s before snapping to the engine's actual
  result.
- **`RouletteWheel.tsx`** — 37/38 colored pocket segments arranged
  in a circle in the canonical casino sequence (not numerical).
  Pockets render correctly red/black/green per the standard table.
  The wheel rotates CSS-transition-style 5+ turns to land with the
  winning pocket at 12 o'clock under a fixed pointer; the ball
  spins the opposite direction at 4 turns.
- **`CrapsTable.tsx`** — felt-styled grid layout: Come (full width),
  Place numbers row (4-10), Field bar, Hardways row, Pass / Don't
  Pass split, Any 7 / Any Craps props. Each zone is a tappable bet
  region that shows a chip stack when occupied; the chip color
  reflects amount (sky for $1, rose for $5, emerald for $25, black
  for $100+ — casino convention). ✕ on each zone cancels the most-
  recent bet there.
- **`TableSurface.tsx`** — shared felt wrapper used by Play.tsx
  (blackjack) and PokerTable.tsx (poker simulator). Wood-tone rail
  ring + green felt with a radial vignette so the center reads
  brighter than the edges.

Wired to use the engines' actual results: dice values, wheel
pocket, and craps phase / book all flow from the API; the UI just
animates and lays them out.

### 11. Lower-priority parking lot — three of four landed earlier

- **✅ Stud bring-in mechanics**: 3rd-street lowest up-card brings in
  (highest in Razz), suit tie-break C < D < H < S. 4th-street onward
  uses a `_showing_score` helper — pair count, top pair rank, sorted
  ranks — to pick the strongest visible hand. Razz inverts the
  comparison so the weakest visible hand acts first (a pair is a
  liability in lowball). Tests in `tests/test_poker_stud_round.py`
  cover lowest-card, suit tiebreak, Razz reversal, and the
  4th-street pair-of-aces transfer of action.
- **✅ Stud Hi/Lo split pot**: `_settle_split` halves each side pot
  between the high winner(s) and the qualifying low winner(s); when
  no low qualifies, high scoops. Odd-dollar remainder goes to high
  per card-room convention.
- **✅ Real PWA icon set**: SVG + 192/512/512-maskable/180/32 PNGs
  generated from `client/scripts/build-icons.py`. Manifest references
  all four sizes; index.html links favicon + apple-touch-icon. The
  raster step uses Pillow (one-time helper, not a build dependency).
- **Form-based blackjack template builder** (open): current template
  editor is JSON-only. Poker has VariantBuilder with structured
  controls; need a similar form for blackjack (rule toggles,
  side-bet payouts, etc.). Largest remaining UI piece.

## Things that bit me this session worth remembering

- **`$Host` is reserved in PowerShell.** Using it for a custom value
  technically silently shadows the host program. Use `$MachineName`
  or similar.
- **Vite 5+ rejects unknown Host headers.** `host: true` alone isn't
  enough for hostname-based access — `allowedHosts` must whitelist
  the names. `'allowedHosts': true` disables the check entirely;
  acceptable only for purely-local dev, never for shared.
- **Eventlet + SQLAlchemy** = the lock-state mismatch that took the
  first deploy down. We use gthread now. Don't reintroduce eventlet
  unless paired with `psycogreen` and a hard look at the connection
  pool.
- **`app.py` next to `app/` package** = silent breakage. Python's
  import machinery prefers the package. Entry point lives in
  `wsgi.py` for this exact reason.
- **`db.create_all()` is idempotent** but doesn't add columns to
  existing tables. The `_ensure_columns` shim handles that until
  alembic takes over fully.
- **Tracked node_modules / .venv / *.pyc** balloons every diff. The
  cleanup commit ripped 7000+ files out of git tracking; don't
  re-stage those paths.

## How to pick up

```bash
cd /home/user/blackjack-service   # or wherever the repo lives
git pull
git log --oneline | head -25      # see the last session's commits
cat docs/NEXT_SESSION.md          # this file

# If venv was rebuilt:
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install pytest

# Smoke test:
.venv/bin/python -m pytest tests/
cd client && npm install && npm run typecheck && npm run build
```

Good luck — Claude (handing off)
