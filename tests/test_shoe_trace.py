"""Shoe-trace logger tests. The trace is environment-gated so the play
loop cost is zero by default. These tests verify the gate flips with
BLACKJACK_SHOE_TRACE and that one round produces one JSON line with the
expected keys.
"""
from __future__ import annotations

import json
import os
from types import SimpleNamespace

from app.engine.cards import Card, Suit
from app.engine.round import Round, Seat
from app.engine.rules import Rules, SideBets
from app.services import shoe_trace


def C(rank: str, suit: str = "S") -> Card:
    return Card(rank, Suit(suit))


class RiggedShoe:
    def __init__(self, cards: list[Card]):
        self._cards = list(cards)

    def next_card(self) -> Card:
        return self._cards.pop(0)

    @property
    def needs_reshuffle(self) -> bool:
        return False


def _fake_session():
    """The trace function only reads a few attrs off the session. A
    SimpleNamespace stand-in keeps the test free of DB setup."""
    return SimpleNamespace(
        id=42,
        shoe_seed=12345,
        cards_dealt=10,
    )


def _played_round() -> Round:
    rules = Rules(insurance_offered=False, dealer_peeks=False)
    cards = [C("T"), C("9"), C("9"), C("8")]
    rnd = Round(rules, SideBets(), RiggedShoe(cards))
    rnd.add_seat(Seat(seat_num=1, main_bet=10, is_human=True))
    rnd.deal()
    while rnd.state.value == "playing":
        rnd.act("stand")
    return rnd


def test_trace_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("BLACKJACK_SHOE_TRACE", raising=False)
    assert not shoe_trace.is_enabled()

    rnd = _played_round()
    # No file path set; trace_round must be a no-op even if called.
    shoe_trace.trace_round(_fake_session(), rnd, running_count_after=0,
                           cards_seen_after=0)


def test_trace_writes_one_line_per_round(tmp_path, monkeypatch):
    log_path = tmp_path / "shoe-trace.jsonl"
    monkeypatch.setenv("BLACKJACK_SHOE_TRACE", str(log_path))
    assert shoe_trace.is_enabled()

    rnd = _played_round()
    sess = _fake_session()
    shoe_trace.trace_round(sess, rnd, running_count_after=-2,
                           cards_seen_after=4)

    text = log_path.read_text(encoding="utf-8")
    lines = [l for l in text.splitlines() if l.strip()]
    assert len(lines) == 1

    record = json.loads(lines[0])
    assert record["session_id"] == 42
    assert record["shoe_seed"] == 12345
    assert record["running_count_after"] == -2
    assert record["cards_seen_after"] == 4
    assert record["dealer"]["cards"][0]["rank"] == "9"
    assert len(record["seats"]) == 1
    seat = record["seats"][0]
    assert seat["seat_num"] == 1
    assert seat["is_human"] is True
    # First hand has the original 2 cards (player stood; dealer total=17).
    assert len(seat["hands"][0]) == 2
    assert len(seat["outcomes"]) == 1


def test_trace_appends_across_rounds(tmp_path, monkeypatch):
    log_path = tmp_path / "trace.jsonl"
    monkeypatch.setenv("BLACKJACK_SHOE_TRACE", str(log_path))

    sess = _fake_session()
    for _ in range(3):
        shoe_trace.trace_round(sess, _played_round(),
                               running_count_after=0, cards_seen_after=0)

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    for line in lines:
        json.loads(line)  # all three lines parse


def test_trace_swallows_io_errors(tmp_path, monkeypatch):
    """If the path is unwritable (e.g. directory is a file), tracing
    must silently swallow the error rather than blowing up settlement."""
    bad_dir = tmp_path / "not-a-dir"
    bad_dir.write_text("file masquerading as dir")
    monkeypatch.setenv("BLACKJACK_SHOE_TRACE", str(bad_dir / "trace.jsonl"))

    # Should not raise.
    shoe_trace.trace_round(_fake_session(), _played_round(),
                           running_count_after=0, cards_seen_after=0)
