# Notes for the next Claude Code session

State of play and the parking lot, written by Claude at the end of the
session that landed the punch-list. Read this first, then `git log
--oneline | head -25` to see what just shipped.

## Current state

- **Branch:** `main` is the only working branch. Pushes redeploy Render.
- **Tests:** 412 backend pytest, frontend typecheck + build clean.
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

### 5. Lower-priority parking lot

- Stud bring-in mechanics (lowest up-card acts first on 3rd street;
  highest hand thereafter). Current stud round uses simplified
  first-active-seat ordering — playable but not tournament-correct.
- Stud Hi/Lo split pot. Variant exists in the library but the round
  picks one of HI_ONLY / LO_ONLY based on `variant.hi_lo`.
- Form-based blackjack template builder (current is JSON only — the
  poker side has the structured form via VariantBuilder).
- Real PWA icon set. Manifest is in place, icons array empty.

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
