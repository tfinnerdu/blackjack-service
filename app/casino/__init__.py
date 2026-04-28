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
    apply_round_to_participant,
    claim_guest_seat,
    clear_caller_bets,
    create_session,
    get_caller_bankroll,
    get_caller_bets,
    get_guest_entry,
    get_session_for_room_code,
    get_session_for_token,
    participants,
    record_round,
    release_guest_seat,
    set_caller_bets,
)

__all__ = [
    "apply_round_to_participant",
    "claim_guest_seat",
    "clear_caller_bets",
    "create_session",
    "get_caller_bankroll",
    "get_caller_bets",
    "get_guest_entry",
    "get_session_for_room_code",
    "get_session_for_token",
    "participants",
    "record_round",
    "release_guest_seat",
    "set_caller_bets",
]
