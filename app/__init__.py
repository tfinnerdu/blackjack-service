"""Application factory."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from flask import Flask, jsonify, send_from_directory
from flask_migrate import Migrate
from dotenv import load_dotenv

from .config import Config
from .db import db


SERVICE_NAME = "blackjack-service"
VERSION = "0.1.0"

# app/static/ holds the built React bundle (vite build output).
STATIC_DIR = Path(__file__).parent / "static"

# Flask-Migrate instance — registered with the app inside create_app so
# `flask db <cmd>` finds it. The migrations/ directory at the project
# root holds the alembic env + versioned scripts.
migrate = Migrate()


def create_app(config: Config | None = None) -> Flask:
    load_dotenv()

    app = Flask(
        __name__,
        static_folder=str(STATIC_DIR),
        static_url_path="",
    )
    app.config.from_object(config or Config())

    _configure_logging(app)
    db.init_app(app)

    # MIGRATING=1 tells create_app to skip the runtime bootstrap
    # (db.create_all + seed_builtin_presets) so `flask db migrate` can
    # autogenerate against a clean schema. Production / dev / test runs
    # leave it unset and bootstrap normally.
    skip_bootstrap = os.environ.get("MIGRATING") == "1"

    with app.app_context():
        # Models register on import. We let alembic handle schema in
        # production (`flask db upgrade` in the build step). Locally —
        # and as a safety net for fresh DBs that haven't been migrated
        # yet — db.create_all() + _ensure_columns() still bootstrap
        # everything. Both paths converge on the same final schema; the
        # alembic version table is created by the first `flask db
        # upgrade` if it isn't already present.
        from . import models  # noqa: F401  registers SQLAlchemy models
        if not skip_bootstrap:
            db.create_all()
            models.seed_builtin_presets()

    # Register flask-migrate with our models package as the metadata
    # source. This is what makes `flask db migrate` autogenerate
    # migrations from model changes going forward.
    migrate.init_app(app, db, directory=str(Path(__file__).parent.parent / "migrations"))

    _register_routes(app)
    _register_spa_fallback(app)

    return app


def _configure_logging(app: Flask) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            '{"timestamp":"%(asctime)s","level":"%(levelname)s",'
            f'"service":"{SERVICE_NAME}","message":"%(message)s"}}'
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO if not app.debug else logging.DEBUG)


def _register_routes(app: Flask) -> None:
    from .routes.games import bp as games_bp
    from .routes.health import bp as health_bp
    from .routes.poker import bp as poker_bp
    from .routes.sessions import bp as sessions_bp
    from .routes.strategy import bp as strategy_bp
    from .routes.templates import bp as templates_bp

    app.register_blueprint(games_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(poker_bp)
    app.register_blueprint(sessions_bp)
    app.register_blueprint(strategy_bp)
    app.register_blueprint(templates_bp)

    @app.route("/api/v1/version")
    def version():
        return jsonify(service=SERVICE_NAME, version=VERSION)


def _register_spa_fallback(app: Flask) -> None:
    """Serve the built React app for any non-API path."""

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def spa(path: str):
        if path.startswith("api/"):
            return jsonify(error="not found", code="NOT_FOUND"), 404

        target = STATIC_DIR / path
        if path and target.exists() and target.is_file():
            return send_from_directory(STATIC_DIR, path)

        index = STATIC_DIR / "index.html"
        if index.exists():
            return send_from_directory(STATIC_DIR, "index.html")

        # Pre-build dev fallback so /health still proves the server is up.
        return jsonify(
            service=SERVICE_NAME,
            version=VERSION,
            message="React bundle not built yet. Run `npm run build` in client/.",
        )
