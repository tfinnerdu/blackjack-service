"""Optional per-round shoe trace. Activated by `BLACKJACK_SHOE_TRACE`.

When the env var is set to a writable file path, every settled round
appends one JSON line capturing:
  - the cards dealt to each seat and the dealer
  - the running count + cards-seen after the round
  - the player outcome and dealer-blackjack flag
  - the session id and shoe seed (so a trace can be replayed)

Off by default — zero overhead on the normal play path. Useful when a
user reports anecdotal bias and we need a real session trace to compare
against the fairness audit's expected rates.

Format is JSON Lines so a long session can be tailed/streamed without
loading the whole file. Failures during write are swallowed — debug
tracing must never break a real round.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..engine.round import Round
    from ..models import GameSession


_ENV_VAR = "BLACKJACK_SHOE_TRACE"
_lock = threading.Lock()


def is_enabled() -> bool:
    return bool(os.environ.get(_ENV_VAR))


def _path() -> str | None:
    p = os.environ.get(_ENV_VAR)
    return p or None


def trace_round(sess: "GameSession", rnd: "Round",
                running_count_after: int, cards_seen_after: int) -> None:
    """Append one JSON line describing the round. No-op if disabled or
    if the round didn't reach completion.
    """
    path = _path()
    if not path:
        return
    if rnd.result is None:
        return

    try:
        record = _build_record(sess, rnd, running_count_after, cards_seen_after)
    except Exception:
        # Defensive: a malformed round shouldn't kill the play loop.
        return

    line = json.dumps(record, separators=(",", ":")) + "\n"
    with _lock:
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            return


def _build_record(sess: "GameSession", rnd: "Round",
                  running_count_after: int,
                  cards_seen_after: int) -> dict:
    seats = []
    for s in rnd.seats:
        seat_outcomes = [
            {
                "hand_index": o.hand_index,
                "result": o.result,
                "profit": o.profit,
                "final_total": o.final_total,
            }
            for o in rnd.result.outcomes if o.seat_num == s.seat_num
        ]
        seats.append({
            "seat_num": s.seat_num,
            "is_human": s.is_human,
            "main_bet": s.main_bet,
            "hands": [
                [c.to_dict() for c in h.cards] for h in s.hands
            ],
            "outcomes": seat_outcomes,
        })

    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "session_id": getattr(sess, "id", None),
        "shoe_seed": getattr(sess, "shoe_seed", None),
        "shoe_cards_dealt_before": getattr(sess, "cards_dealt", None),
        "dealer": {
            "cards": [c.to_dict() for c in rnd.dealer.cards],
            "total": rnd.dealer.total,
            "blackjack": rnd.result.dealer_blackjack,
            "bust": rnd.dealer.is_bust,
        },
        "seats": seats,
        "running_count_after": running_count_after,
        "cards_seen_after": cards_seen_after,
    }
