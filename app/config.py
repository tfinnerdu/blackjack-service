"""Runtime config. Reads from env, sensible local-dev defaults."""
from __future__ import annotations

import os
from pathlib import Path


class Config:
    SERVICE_NAME = "blackjack-service"

    # SQLite for zero-setup local dev; Render injects DATABASE_URL for Postgres.
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{Path(__file__).parent.parent / 'blackjack.db'}",
    )

    # Render's DATABASE_URL uses the postgres:// scheme; SQLAlchemy 2.x wants postgresql://.
    if SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace(
            "postgres://", "postgresql://", 1
        )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-do-not-use-in-prod")

    # Anonymous session cookie name. Swap to JWT later when accounts land.
    SESSION_COOKIE_NAME = "bj_session"
