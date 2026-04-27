"""Application factory."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from flask import Flask, jsonify, send_from_directory
from dotenv import load_dotenv

from .config import Config
from .db import db


SERVICE_NAME = "blackjack-service"
VERSION = "0.1.0"

# app/static/ holds the built React bundle (vite build output).
STATIC_DIR = Path(__file__).parent / "static"


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

    with app.app_context():
        # Models register on import. create_all is idempotent and good enough
        # for v0 — alembic migrations land when persistence gets real (phase 6).
        from . import models
        db.create_all()
        models.seed_builtin_presets()

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
    from .routes.health import bp as health_bp
    from .routes.sessions import bp as sessions_bp
    from .routes.strategy import bp as strategy_bp
    from .routes.templates import bp as templates_bp

    app.register_blueprint(health_bp)
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
