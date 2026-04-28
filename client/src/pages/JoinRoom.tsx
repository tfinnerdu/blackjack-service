import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApiError, Rooms } from "../lib/api";
import type { RoomLobbyView } from "../lib/types";

// Lobby for a shared session. Anyone who knows the room code can pull
// this up, see the seats, and claim a bot. Claiming sets the guest's
// auth cookie and bounces them to /play, which then reads round state
// like any other session participant.
export default function JoinRoom() {
  const { code = "" } = useParams<{ code: string }>();
  const navigate = useNavigate();
  const [lobby, setLobby] = useState<RoomLobbyView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [manualCode, setManualCode] = useState("");

  useEffect(() => {
    if (!code) return;
    refresh().catch(() => {});
  }, [code]);

  async function refresh() {
    try {
      setLobby(await Rooms.lobby(code));
      setError(null);
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.status === 404
            ? "no such room"
            : `${e.code}: ${e.message}`
          : String(e),
      );
    }
  }

  async function claim(seatNum: number) {
    setBusy(seatNum);
    try {
      const resp = await Rooms.claim(code, seatNum);
      // Auth cookie is set server-side; just redirect to /play.
      navigate("/play", { replace: true });
      void resp;
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(null);
    }
  }

  if (!code) {
    // Manual code entry — let folks type a 6-char code if they were
    // told it verbally rather than handed a link.
    return (
      <div
        className="min-h-screen px-4 py-6 flex flex-col items-center gap-4"
        style={{ paddingTop: "calc(env(safe-area-inset-top) + 32px)" }}
      >
        <Link to="/" className="text-white/60 text-sm self-start">← home</Link>
        <h1 className="text-2xl font-bold">Join a room</h1>
        <p className="text-sm text-white/70 text-center max-w-xs">
          Enter the 6-character room code your host shared with you.
        </p>
        <input
          autoFocus
          autoCapitalize="characters"
          placeholder="ABC234"
          value={manualCode}
          onChange={(e) => setManualCode(e.target.value.toUpperCase().slice(0, 6))}
          className="font-mono text-3xl tracking-widest text-center w-56 bg-felt-dark rounded-xl py-4"
        />
        <button
          disabled={manualCode.length < 4}
          onClick={() => navigate(`/join/${manualCode}`)}
          className="min-h-touch px-6 rounded-xl bg-white text-felt-dark font-semibold disabled:opacity-50"
        >
          Look it up
        </button>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-3 text-white/80">
        <div className="text-lg">Couldn't open room</div>
        <div className="text-sm text-red-300">{error}</div>
        <Link to="/join" className="underline text-sm">try a different code</Link>
      </div>
    );
  }

  if (!lobby) {
    return (
      <div className="min-h-screen flex items-center justify-center text-white/40">
        loading…
      </div>
    );
  }

  const claimable = lobby.seats.filter((s) => s.kind === "ai" && s.claimable);

  return (
    <div
      className="min-h-screen px-4 py-6"
      style={{
        paddingTop: "calc(env(safe-area-inset-top) + 16px)",
        paddingBottom: "calc(env(safe-area-inset-bottom) + 16px)",
      }}
    >
      <div className="max-w-md mx-auto space-y-5">
        <div className="flex items-center justify-between">
          <Link to="/" className="text-white/60 text-sm">
            ← home
          </Link>
          <button
            onClick={refresh}
            className="text-white/60 text-sm underline"
          >
            refresh
          </button>
        </div>

        <div className="text-center space-y-1">
          <div className="text-xs uppercase tracking-wide text-white/60">
            Room code
          </div>
          <div className="font-mono text-3xl tracking-widest">{lobby.room_code}</div>
          {lobby.template_name && (
            <div className="text-xs text-white/60">{lobby.template_name}</div>
          )}
          <div className="text-xs text-white/60">
            {lobby.hands_played} hand{lobby.hands_played === 1 ? "" : "s"} played so far
          </div>
        </div>

        <div className="space-y-2">
          <div className="text-xs uppercase tracking-wide text-white/60">Seats</div>
          {lobby.seats.map((s) => (
            <div
              key={s.seat_num}
              className="rounded-xl bg-felt p-3 flex items-center gap-3"
            >
              <div className="font-mono text-lg w-8 text-center">{s.seat_num}</div>
              <div className="flex-1">
                <div className="text-sm">
                  {s.kind === "host"
                    ? "Host (taken)"
                    : s.kind === "guest"
                      ? "Another player (taken)"
                      : `${s.playstyle ?? "bot"} • ${s.bet_pattern ?? ""} • $${s.base_bet ?? "?"}`}
                </div>
                {s.kind === "ai" && s.bankroll != null && (
                  <div className="text-[11px] text-white/50">
                    bot bankroll: ${s.bankroll}
                  </div>
                )}
              </div>
              {s.kind === "ai" && s.claimable && (
                <button
                  disabled={busy === s.seat_num}
                  onClick={() => claim(s.seat_num)}
                  className="min-h-touch px-4 rounded-lg bg-white text-felt-dark font-semibold text-sm disabled:opacity-50"
                >
                  {busy === s.seat_num ? "Joining…" : "Take seat"}
                </button>
              )}
            </div>
          ))}
          {claimable.length === 0 && (
            <p className="text-sm text-white/60 text-center">
              No bot seats are open right now. Ask the host to add a seat or
              wait for someone to leave.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
