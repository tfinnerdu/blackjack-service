"""SQLAlchemy models. Imported by the app factory to register tables.

Phase 1: stub only. Phase 2 fills in Session, Hand, Action, AISeat,
SettingsTemplate, plus a 'is_builtin' flag so canonical presets stay read-only.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..db import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Ping(db.Model):
    """Trivial table to verify migrations + connectivity in phase 1."""
    __tablename__ = "ping"

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime(timezone=True), default=_utcnow, nullable=False)
