# Deploying to Render

Two paths. Pick one.

---

## Option A — Blueprint (recommended)

Render reads `render.yaml` and creates the web service + Postgres database
in one click.

1. Push this repo to GitHub (you already have it on
   `tfinnerdu/blackjack-service`).
2. In Render dashboard: **New → Blueprint**.
3. Pick `tfinnerdu/blackjack-service`. Render will detect `render.yaml`,
   show you the resources it's about to create (one web service named
   `blackjack-service`, one Postgres database named `blackjack-db`),
   and ask you to confirm.
4. Confirm. Build runs:
   ```
   pip install -r requirements.txt
   cd client && npm ci && npm run build
   ```
   Then it boots gunicorn:
   ```
   gunicorn -k eventlet -w 1 -b 0.0.0.0:$PORT app:app
   ```
5. First boot creates the SQLite-or-Postgres tables and seeds the four
   built-in templates (Vegas Strip, Vegas Downtown, Single-Deck,
   European No-Hole).
6. Visit the service URL. Healthcheck path is `/health`.

That's it. Subsequent pushes to the connected branch trigger redeploys
automatically.

---

## Option B — Manual ("New Web Service")

Use this if Blueprint isn't an option (e.g. you want manual control over
the database).

1. Render dashboard → **New → PostgreSQL**. Free tier, same region you
   plan to use for the web service. Note the **Internal Database URL**.
2. Render dashboard → **New → Web Service**. Connect this repo.
3. Fill in:
   - **Name**: `blackjack-service`
   - **Language**: Python 3
   - **Branch**: whatever you're deploying from (`main` once merged)
   - **Region**: same as the database
   - **Build Command**:
     ```
     pip install -r requirements.txt && cd client && npm ci && npm run build
     ```
   - **Start Command**:
     ```
     gunicorn -k eventlet -w 1 -b 0.0.0.0:$PORT app:app
     ```
   - **Instance Type**: Free (works fine for a personal trainer)
4. Environment variables (add each):
   - `PYTHON_VERSION` = `3.11.9`
   - `NODE_VERSION` = `20.18.0`
   - `SECRET_KEY` = click **Generate**
   - `DATABASE_URL` = paste the Internal Database URL from step 1
5. Advanced → **Health Check Path**: `/health`
6. Deploy.

---

## After deploy

- Healthcheck: `https://<service>.onrender.com/health` → `{ "status": "ok" }`
- App: `https://<service>.onrender.com/` — should load the React bundle.
- Templates list: `GET /api/v1/templates` should return four built-ins.

## Troubleshooting

- **`/health` 502 on first hit** — Render free tier sleeps after 15 min
  of inactivity. The first request wakes it; takes ~30s. Subsequent
  requests are normal.
- **Bundle missing / "React bundle not built yet"** — the build step
  failed. Check the deploy logs for `npm run build` errors.
- **`DATABASE_URL` errors** — Render sometimes hands out
  `postgres://...` while SQLAlchemy 2.x wants `postgresql://...`. The
  app auto-rewrites this in `app/config.py`, so if you still see the
  error, double-check the env var didn't get pasted with extra
  whitespace.
- **Sessions vanish across deploys** — they shouldn't. Anonymous tokens
  live in Postgres + a 60-day cookie. If they do, check the Render free
  tier database hasn't been suspended for inactivity.
