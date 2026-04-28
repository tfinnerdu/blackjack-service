"""Shared infrastructure for the simple-state casino games:
Roulette, Baccarat, Craps. Each game has its own engine + routes, but
they share session storage, room-code multi-player, and bankroll math.

Blackjack and Poker have their own session tables because they carry
richer in-flight state (round state machines, AI seats, counters). The
`CasinoSession` model is a deliberately small surface — `state_json`
holds whatever the game wants, `history_json` is the capped per-round
log the Stats UI plots.
"""
from .session import (
    create_session,
    claim_guest_seat,
    get_session_for_room_code,
    get_session_for_token,
    record_round,
    release_guest_seat,
)

__all__ = [
    "create_session",
    "claim_guest_seat",
    "get_session_for_room_code",
    "get_session_for_token",
    "record_round",
    "release_guest_seat",
]
