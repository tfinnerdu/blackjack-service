# Notes for the next Claude Code session

State of play and the parking lot, written by Claude at the end of the
session that landed the punch-list. Read this first, then `git log
--oneline | head -25` to see what just shipped.

## Current state

- **Branch:** `main` is the only working branch. Pushes redeploy Render.
- **Tests:** 401 backend pytest, frontend typecheck + build clean.
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

### 1. End-user feedback on stats — V2 features

Quote: "I think there's more stats that you could show for a session
such as money made vs what if money playing strictly by the book vs
AI's card counting money and betting."

Three concrete tracks:
- **What-if-book bankroll**: parallel running total of "what would
  bankroll be if I'd played every hand exactly per the book?" Today
  the engine tracks book-mistakes count + a heuristic EV-lost. The
  ask is the exact replay value. Implementation: at hand settlement,
  re-deal with the same shoe state, force every player action to the
  book recommendation, settle, take the profit delta.
- **AI counter's bankroll**: spawn a virtual seat that bets the count
  + plays the book + uses Hi-Lo + Illustrious 18. Engine pieces all
  exist (`app/strategy/book.py`, `app/counting/`, `app/ai/`). Surface
  as a third bankroll line on the Stats page.
- **Time-series chart**: divergence between your bankroll, book
  bankroll, counter bankroll across the session. Frontend chart lib
  TBD — recharts is the obvious pick.

### 2. End-user "something seems off" — fairness audit

The user's friend reported a 63% win rate over 129 hands with $554
profit on a $200 buy-in, anecdotally never seeing dealer blackjacks
across many ace-up situations. Statistically that win rate is ~4σ
above expected; if real, the engine has a bias.

Concrete next steps to investigate:
- **Add a fairness audit test**: `tests/test_fairness_audit.py` that
  spins up a 6-deck H17 session and runs 10,000 hands of "always
  stand" against the engine. Asserts dealer-BJ rate ≈ 4.8%, player-BJ
  rate ≈ 4.8%, dealer-bust rate ≈ 28%, player win-rate ≈ 43%. Within
  reasonable tolerance.
- **Add a debug shoe-trace logger**: env-var-gated; writes every
  card dealt + the running count after each hand to a session debug
  file. Lets the user generate a real-session trace + mail it in for
  forensic review.
- Hot suspects to eyeball:
  - `Round.deal()` in `app/engine/round.py` — order is correct on
    inspection, but verify with a rigged shoe + known cards.
  - Dealer peek logic in `_after_insurance_decided` — both paths
    (insurance-offered and not) flow through the same peek block,
    confirmed locally.
  - Hi-Lo counter — `Counter.see_many` on every visible card from the
    round at settle time.

If the audit test stays green to within tolerance, the user's friend
hit unusual variance. If not, we have a real engine bug.

### 3. Migration switchover (when ready)

In Render's shell:
```
MIGRATING=1 FLASK_APP=wsgi.py flask db stamp head
```
Then uncomment the `flask db upgrade` line in `render.yaml`'s
buildCommand and push. Future schema changes flow through alembic.

### 4. Lower-priority parking lot

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
