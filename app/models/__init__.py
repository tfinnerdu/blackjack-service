"""SQLAlchemy models. Imported by the app factory to register tables.

Phase 2 adds SettingsTemplate. Session/Hand/Action persistence lands in
phase 6 (where they swap localStorage for server storage).
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone

from sqlalchemy import event

from ..db import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SettingsTemplate(db.Model):
    """A named Rules + SideBets snapshot the user can apply to a new session.

    Built-in presets are seeded with `is_builtin=True` and are read-only in
    the UI (clone-to-edit). User-created templates are editable.
    """

    __tablename__ = "settings_template"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    description = db.Column(db.String(500), nullable=False, default="")
    rules_json = db.Column(db.Text, nullable=False)
    side_bets_json = db.Column(db.Text, nullable=False)
    is_builtin = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    def rules(self) -> dict:
        return json.loads(self.rules_json)

    def side_bets(self) -> dict:
        return json.loads(self.side_bets_json)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "rules": self.rules(),
            "side_bets": self.side_bets(),
            "is_builtin": self.is_builtin,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_engine(
        cls,
        name: str,
        description: str,
        rules,
        side_bets,
        is_builtin: bool = False,
    ) -> "SettingsTemplate":
        return cls(
            name=name,
            description=description,
            rules_json=json.dumps(rules.to_dict()),
            side_bets_json=json.dumps(side_bets.to_dict()),
            is_builtin=is_builtin,
        )


def seed_builtin_presets() -> None:
    """Insert canonical presets if they're missing. Safe to call repeatedly."""
    from ..engine.presets import all_presets

    existing = {t.name for t in SettingsTemplate.query.filter_by(is_builtin=True).all()}
    added = False
    for rules, side_bets, name, description in all_presets():
        if name in existing:
            continue
        db.session.add(
            SettingsTemplate.from_engine(
                name=name,
                description=description,
                rules=rules,
                side_bets=side_bets,
                is_builtin=True,
            )
        )
        added = True
    if added:
        db.session.commit()
