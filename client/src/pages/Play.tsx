import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Dealer } from "../components/Dealer";
import { SeatBlock } from "../components/Seat";
import { ApiError, Rounds, Sessions } from "../lib/api";
import { useApp } from "../lib/store";

export default function Play() {
  const { session, round, setSession, setRound } = useApp();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [bet, setBet] = useState(10);
  const [busy, setBusy] = useState(false);

  // Bootstrap: load the session + any active round if we landed here cold.
  useEffect(() => {
    if (!session) {
      Sessions.me()
        .then(setSession)
        .catch((e) => {
          if (e instanceof ApiError && e.status === 404) navigate("/setup");
          else setError(String(e));
        });
    }
  }, [session, setSession, navigate]);

  useEffect(() => {
    if (session && !round) {
      Rounds.active()
        .then(setRound)
        .catch((e) => {
          if (e instanceof ApiError && e.status === 404) {
            // No round in flight — that's the normal "between rounds" state.
            setRound(null);
          } else {
            setError(String(e));
          }
        });
    }
  }, [session, round, setRound]);

  // Re-load the session whenever a round completes so bankroll/stats reflect it.
  useEffect(() => {
    if (round?.state === "complete") {
      Sessions.me().then(setSession).catch(() => {});
    }
  }, [round?.state, setSession]);

  async function startRound() {
    if (!session) return;
    setError(null);
    setBusy(true);
    try {
      const r = await Rounds.start({ main_bet: bet });
      setRound(r);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!session) {
    return (
      <div className="min-h-screen flex items-center justify-center text-white/40">
        loading session…
      </div>
    );
  }

  const minBet = session.rules.min_bet;
  const maxBet = Math.min(session.rules.max_bet, session.bankroll);
  const inc = session.rules.bet_increment;
  const hideHole =
    !!round && (round.state === "playing" || round.state === "insurance" || round.state === "betting");

  return (
    <div
      className="min-h-screen px-3 py-3 flex flex-col gap-3"
      style={{
        paddingTop: "calc(env(safe-area-inset-top) + 12px)",
        paddingBottom: "calc(env(safe-area-inset-bottom) + 96px)",
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <Link to="/" className="text-white/60 text-sm">
          ←
        </Link>
        <div className="text-center">
          <div className="text-xs text-white/50">Bankroll</div>
          <div className="font-mono text-xl">${session.bankroll}</div>
        </div>
        <div className="text-right text-xs text-white/40">
          {session.template_name ?? "Custom"}
        </div>
      </div>

      {/* Dealer */}
      {round ? (
        <Dealer dealer={round.dealer} hideHole={hideHole} />
      ) : (
        <div className="rounded-xl bg-felt-dark/60 p-3 ring-1 ring-white/10 text-white/40 text-sm text-center">
          Place a bet to deal.
        </div>
      )}

      {/* Seats */}
      {round && (
        <div className="space-y-3">
          {round.seats.map((s) => (
            <SeatBlock
              key={s.seat_num}
              seat={s}
              isActive={round.active_seat_num === s.seat_num}
              activeHandIndex={round.active_hand_index}
            />
          ))}
        </div>
      )}

      {error && <div className="text-red-300 text-sm">{error}</div>}

      {/* Pre-deal bet panel */}
      {!round || round.state === "complete" ? (
        <div className="mt-auto rounded-xl bg-felt p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs uppercase tracking-wide text-white/60">Your bet</span>
            <span className="font-mono">${bet}</span>
          </div>
          <div className="grid grid-cols-4 gap-2">
            {[minBet, minBet * 2, minBet * 5, minBet * 10].map((b) => (
              <button
                key={b}
                onClick={() => setBet(Math.min(b, maxBet))}
                className="min-h-touch rounded-lg border border-white/20 text-sm"
              >
                ${b}
              </button>
            ))}
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setBet((b) => Math.max(minBet, b - inc))}
              className="flex-1 min-h-touch rounded-lg border border-white/20 text-xl"
            >
              −
            </button>
            <button
              onClick={() => setBet((b) => Math.min(maxBet, b + inc))}
              className="flex-1 min-h-touch rounded-lg border border-white/20 text-xl"
            >
              +
            </button>
          </div>
          <button
            onClick={startRound}
            disabled={busy || bet < minBet || bet > maxBet}
            className="w-full min-h-touch rounded-xl bg-white text-felt-dark font-semibold disabled:opacity-40"
          >
            {busy ? "Dealing…" : "Deal"}
          </button>
        </div>
      ) : null}
    </div>
  );
}
