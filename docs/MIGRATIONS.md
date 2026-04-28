# Database migrations

## Status

Flask-Migrate scaffolding is in place. `migrations/` holds the alembic
config + a baseline migration that captures every table we have. The
`flask db <cmd>` CLI works in this project.

The existing Render Postgres deployment was bootstrapped via
`db.create_all()` + the inline `_ensure_columns` shim. It has all the
tables but no `alembic_version` row. **One manual step is needed
before alembic can take over.**

## One-time: stamp the existing Render DB

In the Render dashboard → service → **Shell** tab:

```bash
MIGRATING=1 FLASK_APP=wsgi.py flask db stamp head
```

This writes the alembic_version table marking the DB at the baseline
without trying to re-create the existing tables.

After that's done, you can:

1. Uncomment the `flask db upgrade` line in `render.yaml`'s
   `buildCommand`
2. Push — future deploys auto-apply pending migrations

## Workflow going forward

```bash
# 1. Make a model change in app/models/__init__.py.
# 2. Generate the migration:
MIGRATING=1 FLASK_APP=wsgi.py flask db migrate -m "describe change"

# 3. Open the new file in migrations/versions/, eyeball it, edit if
#    auto-detection got something subtle wrong (autogenerate often
#    misses constraint renames + index-only changes).

# 4. Apply locally:
MIGRATING=1 FLASK_APP=wsgi.py flask db upgrade

# 5. Commit the new migration alongside the model change. Push.
#    Render's build runs `flask db upgrade` and applies the new
#    revision automatically (once the buildCommand is uncommented).
```

The `MIGRATING=1` env var tells `create_app` to skip its bootstrap
(`db.create_all` + `seed_builtin_presets`) so alembic sees a clean
schema for autogen + applies migrations to the actual target DB.

## Why we still have `_ensure_columns`

The inline shim in `app/models/__init__.py` is a safety net for
SQLite local-dev databases that haven't been migrated. It's a no-op
once a column already exists. After the Render stamp + auto-upgrade
flip, you can delete it — production will be on alembic and local
dev can use `flask db upgrade` too.

Until then: it's defensive code that costs nothing.

## Common operations

```bash
# History of applied + pending migrations:
MIGRATING=1 FLASK_APP=wsgi.py flask db history

# Roll back one revision:
MIGRATING=1 FLASK_APP=wsgi.py flask db downgrade -1

# Show current revision:
MIGRATING=1 FLASK_APP=wsgi.py flask db current
```
