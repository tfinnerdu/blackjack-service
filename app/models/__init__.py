"""SQLAlchemy models. Imported by the app factory to register tables.

Phase 2 added SettingsTemplate. Phase 5 adds GameSession (bankroll,
shoe state, AI seats, counter snapshot). Round-in-flight state is
stored on the GameSession as JSON until phase 6's round API persists it.
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone

from ..db import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_token() -> str:
    """URL-safe anonymous session token. ~256 bits of entropy."""
    return secrets.token_urlsafe(32)


class SettingsTemplate(db.Model):
    """A named rules + side-bets snapshot the user can apply to a new session.

    `game_type` discriminates between game families ('blackjack', 'poker', ...).
    Built-in presets are seeded with `is_builtin=True` and are read-only in
    the UI (clone-to-edit). User-created templates are editable.
    """

    __tablename__ = "settings_template"

    id = db.Column(db.Integer, primary_key=True)
    game_type = db.Column(db.String(32), nullable=False, default="blackjack", index=True)
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
            "game_type": self.game_type,
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
        game_type: str = "blackjack",
    ) -> "SettingsTemplate":
        return cls(
            game_type=game_type,
            name=name,
            description=description,
            rules_json=json.dumps(rules.to_dict()),
            side_bets_json=json.dumps(side_bets.to_dict()),
            is_builtin=is_builtin,
        )


class GameSession(db.Model):
    """One play session. Owns bankroll, shoe seed + cards-dealt counter,
    AI seat configs, and a Hi-Lo running snapshot.

    Auth is anonymous: a random `token` lives in a cookie + URL; whoever
    has the token has the session. When we add real accounts later, a
    nullable `user_id` FK gets added and the same lookup helper consults it
    first.
    """

    __tablename__ = "game_session"

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), nullable=False, unique=True, default=_new_token)
    # Short shareable code for invite-by-link / verbal-share. Six chars from
    # an unambiguous alphabet (no 0/O/1/I). Multiple guests can use it to
    # claim a bot seat at the table.
    room_code = db.Column(db.String(8), nullable=True, unique=True, index=True)
    # JSON map {seat_num: token} of seats that have been claimed by a
    # guest. The original `token` column above continues to authorize
    # the host's seat (player_seat). NULL/empty means no guests yet.
    seat_tokens_json = db.Column(db.Text, nullable=True, default="{}")

    # Rule snapshot at session start. The template can be edited later but
    # mid-session rules don't change.
    template_id = db.Column(
        db.Integer,
        db.ForeignKey("settings_template.id", ondelete="SET NULL"),
        nullable=True,
    )
    rules_json = db.Column(db.Text, nullable=False)
    side_bets_json = db.Column(db.Text, nullable=False)

    # Money + history
    starting_bankroll = db.Column(db.Integer, nullable=False)
    bankroll = db.Column(db.Integer, nullable=False)
    last_results_json = db.Column(db.Text, nullable=False, default="[]")

    # Shoe + counter snapshot. Re-deal the shoe by seeding, advancing
    # the RNG by `shoe_shuffles - 1` extra shuffles to land on the
    # current permutation, then discarding `cards_dealt` cards to reach
    # the same position. Without `shoe_shuffles`, every page reload
    # after the first reshuffle would put the shoe back into the
    # initial permutation — visibly the same hands repeating.
    shoe_seed = db.Column(db.Integer, nullable=False)
    shoe_shuffles = db.Column(db.Integer, nullable=False, default=1)
    cards_dealt = db.Column(db.Integer, nullable=False, default=0)
    running_count = db.Column(db.Integer, nullable=False, default=0)
    counter_cards_seen = db.Column(db.Integer, nullable=False, default=0)

    # Seats
    player_seat = db.Column(db.Integer, nullable=False)
    ai_seats_json = db.Column(db.Text, nullable=False, default="[]")

    # Round-in-flight (JSON snapshot of the orchestrator state). Null when
    # no round is active. Phase 6 reads/writes this during play.
    active_round_json = db.Column(db.Text, nullable=True)

    # Aggregate stats so we don't recompute on every dashboard hit.
    hands_played = db.Column(db.Integer, nullable=False, default=0)
    book_profit = db.Column(db.Integer, nullable=False, default=0)
    actual_profit = db.Column(db.Integer, nullable=False, default=0)
    book_mistakes = db.Column(db.Integer, nullable=False, default=0)
    # Parallel-replay bankrolls for "what-if" stats. Each round we replay
    # the same shoe state with two virtual strategies and accumulate their
    # profit deltas:
    #   book_bankroll: human seat played to perfect basic-strategy book.
    #   counter_bankroll: human seat played book + Hi-Lo indices and used
    #     a count-spread bet pattern (so high counts get bigger bets).
    # Initialized to starting_bankroll on session create; advances per round.
    book_bankroll = db.Column(db.Integer, nullable=False, default=0)
    counter_bankroll = db.Column(db.Integer, nullable=False, default=0)
    # Time series of (hand, actual, book, counter) tuples for the chart.
    # Capped to last 1000 hands to keep the row size reasonable.
    bankroll_history_json = db.Column(db.Text, nullable=False, default="[]")
    # Heuristic EV-lost-to-mistakes (cents to avoid float). Each time the
    # human's action diverges from book, an action-specific fraction of
    # the bet is added here. Approximation, not a Monte Carlo EV — useful
    # for direction, not absolute accuracy.
    ev_lost_cents = db.Column(db.Integer, nullable=False, default=0)
    # Per-result counters (player perspective, all hands across splits).
    wins = db.Column(db.Integer, nullable=False, default=0)
    losses = db.Column(db.Integer, nullable=False, default=0)
    pushes = db.Column(db.Integer, nullable=False, default=0)
    player_blackjacks = db.Column(db.Integer, nullable=False, default=0)
    busts = db.Column(db.Integer, nullable=False, default=0)
    surrenders = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )
    last_activity_at = db.Column(
        db.DateTime(timezone=True), default=_utcnow, nullable=False
    )

    template = db.relationship("SettingsTemplate", lazy="joined")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "token": self.token,
            "room_code": self.room_code,
            "seat_tokens": json.loads(self.seat_tokens_json or "{}"),
            "template_id": self.template_id,
            "template_name": self.template.name if self.template else None,
            "rules": json.loads(self.rules_json),
            "side_bets": json.loads(self.side_bets_json),
            "starting_bankroll": self.starting_bankroll,
            "bankroll": self.bankroll,
            "shoe": {
                "seed": self.shoe_seed,
                "cards_dealt": self.cards_dealt,
                "shuffles": self.shoe_shuffles or 1,
            },
            "counter": {
                "running_count": self.running_count,
                "cards_seen": self.counter_cards_seen,
            },
            "player_seat": self.player_seat,
            "ai_seats": json.loads(self.ai_seats_json),
            "stats": {
                "hands_played": self.hands_played,
                "actual_profit": self.actual_profit,
                "book_profit": self.book_profit,
                "book_mistakes": self.book_mistakes,
                "ev_lost_cents": self.ev_lost_cents,
                "wins": self.wins,
                "losses": self.losses,
                "pushes": self.pushes,
                "player_blackjacks": self.player_blackjacks,
                "busts": self.busts,
                "surrenders": self.surrenders,
                "book_bankroll": self.book_bankroll,
                "counter_bankroll": self.counter_bankroll,
            },
            "active_round": (
                json.loads(self.active_round_json) if self.active_round_json else None
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class PokerSession(db.Model):
    """One ongoing poker simulator table. Holds the variant + bot configs +
    chip stacks; the in-flight hand state lives in active_hand_json (set
    while a hand is being played, cleared when it settles).

    Anonymous-token auth same as GameSession (blackjack). A user can have
    one of each kind in their cookie via separate token columns later;
    for now poker uses a separate cookie.
    """
    __tablename__ = "poker_session"

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), nullable=False, unique=True, default=_new_token)

    template_id = db.Column(
        db.Integer,
        db.ForeignKey("settings_template.id", ondelete="SET NULL"),
        nullable=True,
    )
    variant_json = db.Column(db.Text, nullable=False)
    config_json = db.Column(db.Text, nullable=False)   # blinds + initial stacks
    seats_json = db.Column(db.Text, nullable=False)    # players + bots + stacks
    dealer_seat = db.Column(db.Integer, nullable=False, default=1)
    active_hand_json = db.Column(db.Text, nullable=True)
    hands_played = db.Column(db.Integer, nullable=False, default=0)
    starting_bankroll = db.Column(db.Integer, nullable=False)

    created_at = db.Column(db.DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "token": self.token,
            "template_id": self.template_id,
            "variant": json.loads(self.variant_json),
            "config": json.loads(self.config_json),
            "seats": json.loads(self.seats_json),
            "dealer_seat": self.dealer_seat,
            "active_hand": json.loads(self.active_hand_json) if self.active_hand_json else None,
            "hands_played": self.hands_played,
            "starting_bankroll": self.starting_bankroll,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class CasinoSession(db.Model):
    """Generic casino-game session. Used by Roulette, Baccarat, Craps —
    games with simple state and a per-spin / per-roll resolution model.

    Blackjack and Poker keep their own tables because they have rich
    in-flight state (round-state machines, AI seats, counters).

    The `state_json` column holds game-specific state — for Roulette
    that's the most-recent spin + bets; for Craps it's the point + bet
    book; for Baccarat the most-recent shoe + dealt cards. The
    `history_json` column holds a capped time-series the Stats UI can
    plot without a separate query.
    """
    __tablename__ = "casino_session"

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), nullable=False, unique=True, default=_new_token)
    # Game family discriminator: "roulette" | "baccarat" | "craps".
    game_type = db.Column(db.String(32), nullable=False, index=True)
    # Short shareable code so a host can invite friends to bet alongside
    # them. Same alphabet as blackjack; resolved by the same helper.
    room_code = db.Column(db.String(8), nullable=True, unique=True, index=True)
    # Guest tokens scoped to this casino session — used for multi-player
    # betting on the same wheel/roll. Map-of-guest-tokens; the host's
    # own token always works.
    guest_tokens_json = db.Column(db.Text, nullable=True, default="{}")

    # Money + history.
    starting_bankroll = db.Column(db.Integer, nullable=False)
    bankroll = db.Column(db.Integer, nullable=False)
    rounds_played = db.Column(db.Integer, nullable=False, default=0)

    # Game-specific state + history.
    rules_json = db.Column(db.Text, nullable=False, default="{}")
    state_json = db.Column(db.Text, nullable=False, default="{}")
    history_json = db.Column(db.Text, nullable=False, default="[]")

    created_at = db.Column(db.DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "token": self.token,
            "game_type": self.game_type,
            "room_code": self.room_code,
            "guest_tokens": json.loads(self.guest_tokens_json or "{}"),
            "starting_bankroll": self.starting_bankroll,
            "bankroll": self.bankroll,
            "rounds_played": self.rounds_played,
            "rules": json.loads(self.rules_json or "{}"),
            "state": json.loads(self.state_json or "{}"),
            "history": json.loads(self.history_json or "[]"),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SportsbookSession(db.Model):
    """Paper-trading sports-betting session. The user places single
    bets and parlays against `SportsEvent` markets; we settle them
    once the events resolve and track ROI / win-rate / streaks.

    Demo mode loads a rotating fixture of plausible events; future
    work can wire in a real odds-feed without changing the rest of
    the schema (markets carry an `external_id` slot for that).
    """
    __tablename__ = "sportsbook_session"

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), nullable=False, unique=True, default=_new_token)
    starting_bankroll = db.Column(db.Integer, nullable=False)
    bankroll = db.Column(db.Integer, nullable=False)
    # `current_day` is a synthetic day cursor used by the settlement
    # button: each "advance day" flips events scheduled for today
    # into final results and settles all pending slips that referenced
    # them. Lets a user iterate quickly without waiting for real life.
    current_day = db.Column(db.Integer, nullable=False, default=0)
    # Cached counters so analytics queries don't have to scan slips.
    slips_placed = db.Column(db.Integer, nullable=False, default=0)
    slips_won = db.Column(db.Integer, nullable=False, default=0)
    slips_lost = db.Column(db.Integer, nullable=False, default=0)
    slips_pushed = db.Column(db.Integer, nullable=False, default=0)
    total_staked = db.Column(db.Integer, nullable=False, default=0)
    total_returned = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False,
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "token": self.token,
            "starting_bankroll": self.starting_bankroll,
            "bankroll": self.bankroll,
            "current_day": self.current_day,
            "slips_placed": self.slips_placed,
            "slips_won": self.slips_won,
            "slips_lost": self.slips_lost,
            "slips_pushed": self.slips_pushed,
            "total_staked": self.total_staked,
            "total_returned": self.total_returned,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SportsEvent(db.Model):
    """A single sporting event (e.g. 'Lakers @ Celtics'). Sessions
    don't own events — events are global and scoped by `day` so
    multiple sessions can bet against the same fixture set."""
    __tablename__ = "sports_event"

    id = db.Column(db.Integer, primary_key=True)
    sport = db.Column(db.String(32), nullable=False, index=True)
    league = db.Column(db.String(32), nullable=False)
    home_team = db.Column(db.String(80), nullable=False)
    away_team = db.Column(db.String(80), nullable=False)
    # Day cursor (0, 1, 2, ...). Resolved when the host of a
    # SportsbookSession advances past it.
    day = db.Column(db.Integer, nullable=False, index=True)
    status = db.Column(db.String(16), nullable=False, default="scheduled")
    # final scores once the day has been resolved
    home_score = db.Column(db.Integer, nullable=True)
    away_score = db.Column(db.Integer, nullable=True)
    # Hook for a future live odds feed.
    external_id = db.Column(db.String(80), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=_utcnow, nullable=False)

    markets = db.relationship(
        "BettingMarket",
        backref="event",
        lazy="select",
        cascade="all, delete-orphan",
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "sport": self.sport,
            "league": self.league,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "day": self.day,
            "status": self.status,
            "home_score": self.home_score,
            "away_score": self.away_score,
            "markets": [m.to_dict() for m in self.markets],
        }


class BettingMarket(db.Model):
    """One market on an event — moneyline, spread, total, or a prop.
    `selections_json` is the array of selectable outcomes with their
    American odds. After the event settles, `winner_key` records
    which selection paid (or "PUSH" / "VOID")."""
    __tablename__ = "betting_market"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(
        db.Integer,
        db.ForeignKey("sports_event.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    market_type = db.Column(db.String(32), nullable=False)
    # JSON list of selections:
    #   [{"key": "home", "label": "Lakers", "odds": -150, "line": null},
    #    {"key": "away", "label": "Celtics", "odds": +130, "line": null}]
    selections_json = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(16), nullable=False, default="open")
    # Set on settle: "home" / "away" / "over" / "under" / "PUSH" / "VOID".
    winner_key = db.Column(db.String(32), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_id": self.event_id,
            "market_type": self.market_type,
            "selections": json.loads(self.selections_json),
            "status": self.status,
            "winner_key": self.winner_key,
        }


class BettingSlip(db.Model):
    """A user's wager — single or parlay. `legs_json` is the array of
    (market_id, selection_key, odds_at_placement) tuples. We store the
    odds at placement so a market's odds shifting later doesn't change
    the payout."""
    __tablename__ = "betting_slip"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer,
        db.ForeignKey("sportsbook_session.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    slip_type = db.Column(db.String(16), nullable=False)  # "single" | "parlay"
    legs_json = db.Column(db.Text, nullable=False)
    stake = db.Column(db.Integer, nullable=False)
    potential_payout = db.Column(db.Integer, nullable=False)
    # "pending" | "won" | "lost" | "push" | "void"
    status = db.Column(db.String(16), nullable=False, default="pending")
    # On settle: dollar payout the user got back (0 on loss, stake on push,
    # stake + winnings on win). Net = payout_actual - stake.
    payout_actual = db.Column(db.Integer, nullable=False, default=0)
    placed_at = db.Column(db.DateTime(timezone=True), default=_utcnow, nullable=False)
    placed_on_day = db.Column(db.Integer, nullable=False)
    settled_at = db.Column(db.DateTime(timezone=True), nullable=True)
    # Per-leg results stored after settle for analytics surfaces.
    leg_results_json = db.Column(db.Text, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "slip_type": self.slip_type,
            "legs": json.loads(self.legs_json),
            "stake": self.stake,
            "potential_payout": self.potential_payout,
            "status": self.status,
            "payout_actual": self.payout_actual,
            "net": self.payout_actual - self.stake,
            "placed_at": self.placed_at.isoformat() if self.placed_at else None,
            "placed_on_day": self.placed_on_day,
            "settled_at": self.settled_at.isoformat() if self.settled_at else None,
            "leg_results": (
                json.loads(self.leg_results_json) if self.leg_results_json else None
            ),
        }


def _ensure_columns() -> None:
    """Idempotent boot migrations — a safety net for non-alembic DBs.

    Alembic / Flask-Migrate now owns the production migration story
    (see docs/MIGRATIONS.md). This shim still runs at boot for two
    cases:
      1. Local SQLite dev DBs that haven't been migrated.
      2. The existing Render Postgres deployment until it gets stamped
         (`flask db stamp head`) + the build's `flask db upgrade` is
         uncommented.

    Once both are migrated, this function can be deleted and
    create_app's call to it removed. Until then it's defensive code
    that's idempotent — `ALTER TABLE ... ADD COLUMN` is a no-op when
    the column already exists in our check.

    Each block: check if a known table exists, check if the new column
    exists, ALTER if missing. Designed for SQLite + Postgres.
    """
    from sqlalchemy import inspect, text

    insp = inspect(db.engine)
    table_names = set(insp.get_table_names())

    def _add(table: str, column: str, ddl: str) -> None:
        if table not in table_names:
            return
        cols = {c["name"] for c in insp.get_columns(table)}
        if column in cols:
            return
        with db.engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))

    _add("settings_template", "game_type", "VARCHAR(32) NOT NULL DEFAULT 'blackjack'")
    _add("game_session", "ev_lost_cents", "INTEGER NOT NULL DEFAULT 0")
    _add("game_session", "wins", "INTEGER NOT NULL DEFAULT 0")
    _add("game_session", "losses", "INTEGER NOT NULL DEFAULT 0")
    _add("game_session", "pushes", "INTEGER NOT NULL DEFAULT 0")
    _add("game_session", "player_blackjacks", "INTEGER NOT NULL DEFAULT 0")
    _add("game_session", "busts", "INTEGER NOT NULL DEFAULT 0")
    _add("game_session", "surrenders", "INTEGER NOT NULL DEFAULT 0")
    _add("game_session", "book_bankroll", "INTEGER NOT NULL DEFAULT 0")
    _add("game_session", "counter_bankroll", "INTEGER NOT NULL DEFAULT 0")
    _add("game_session", "bankroll_history_json", "TEXT NOT NULL DEFAULT '[]'")
    _add("game_session", "room_code", "VARCHAR(8)")
    _add("game_session", "seat_tokens_json", "TEXT")
    _add("game_session", "shoe_shuffles", "INTEGER NOT NULL DEFAULT 1")
    # One-time backfill: legacy rows came in at the column default of 0,
    # but a pre-existing session's book / counter bankroll should start
    # from the original buy-in. Idempotent — only flips rows that are
    # still at the migration default.
    if "game_session" in table_names:
        cols = {c["name"] for c in insp.get_columns("game_session")}
        if {"book_bankroll", "counter_bankroll", "starting_bankroll"} <= cols:
            with db.engine.begin() as conn:
                conn.execute(text(
                    "UPDATE game_session SET book_bankroll = starting_bankroll, "
                    "counter_bankroll = starting_bankroll "
                    "WHERE book_bankroll = 0 AND counter_bankroll = 0"
                ))


def seed_builtin_presets() -> None:
    """Insert canonical presets if they're missing. Safe to call repeatedly."""
    from ..engine.presets import all_presets

    _ensure_columns()

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
                game_type="blackjack",
            )
        )
        added = True
    if added:
        db.session.commit()
