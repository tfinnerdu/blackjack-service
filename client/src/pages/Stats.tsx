import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ApiError, Sessions } from "../lib/api";
import { useApp } from "../lib/store";

export default function Stats() {
  const { session, setSession } = useApp();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  if (!session) {
    return (
      <div className="min-h-screen flex items-center justify-center text-white/40">
        loading…
      </div>
    );
  }

  async function reshuffle() {
    setBusy(true);
    setError(null);
    try {
      const updated = await Sessions.reset();
      setSession(updated);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function endSession() {
    if (!confirm("End this session? Your bankroll will be lost.")) return;
    setBusy(true);
    try {
      await Sessions.destroy();
      setSession(null);
      navigate("/");
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
      setBusy(false);
    }
  }

  const profit = session.bankroll - session.starting_bankroll;
  // Win-rate-by-hands needs win/loss counts that the API doesn't break out
  // yet; phase 8's /stats endpoint will. For now we show profit + count.

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
          <Link to="/play" className="text-white/60 text-sm">
            ← back to table
          </Link>
        </div>

        <div className="text-center">
          <div className="text-xs uppercase tracking-wide text-white/60">Bankroll</div>
          <div className="text-4xl font-mono font-bold">${session.bankroll}</div>
          <div
            className={`text-sm mt-1 ${
              profit > 0 ? "text-emerald-300" : profit < 0 ? "text-red-300" : "text-white/50"
            }`}
          >
            {profit >= 0 ? "+" : ""}${profit} from ${session.starting_bankroll} buy-in
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Stat label="Hands played" value={String(session.stats.hands_played)} />
          <Stat
            label="Win rate"
            value={
              session.stats.hands_played
                ? `${Math.round((session.stats.wins / session.stats.hands_played) * 100)}%`
                : "—"
            }
            sub={`${session.stats.wins}W / ${session.stats.losses}L / ${session.stats.pushes}P`}
          />
          <Stat
            label="Book mistakes"
            value={String(session.stats.book_mistakes)}
            sub={
              session.stats.hands_played
                ? `${Math.round(
                    (session.stats.book_mistakes / session.stats.hands_played) * 100,
                  )}% of hands`
                : "—"
            }
          />
          <Stat
            label="Player blackjacks"
            value={String(session.stats.player_blackjacks)}
          />
          <Stat label="Busts" value={String(session.stats.busts)} />
          <Stat label="Surrenders" value={String(session.stats.surrenders)} />
          <Stat label="Cards seen" value={String(session.counter.cards_seen)} />
          <Stat
            label="Running count"
            value={String(session.counter.running_count)}
          />
        </div>

        <div className="rounded-xl bg-felt p-3 text-xs space-y-1">
          <div className="flex justify-between">
            <span className="text-white/60">Template</span>
            <span>{session.template_name ?? "Custom"}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-white/60">Decks</span>
            <span>{session.rules.decks}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-white/60">Dealer</span>
            <span>{session.rules.dealer_hits_soft_17 ? "H17" : "S17"}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-white/60">Blackjack pays</span>
            <span>
              {session.rules.blackjack_payout[0]}:{session.rules.blackjack_payout[1]}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-white/60">Bet</span>
            <span>
              ${session.rules.min_bet}–${session.rules.max_bet} (step $
              {session.rules.bet_increment})
            </span>
          </div>
        </div>

        {error && <div className="text-red-300 text-sm">{error}</div>}

        <div className="space-y-2">
          <button
            onClick={reshuffle}
            disabled={busy}
            className="w-full min-h-touch rounded-xl border border-white/20 text-white"
          >
            Re-shuffle (keeps bankroll & stats)
          </button>
          <button
            onClick={endSession}
            disabled={busy}
            className="w-full min-h-touch rounded-xl bg-red-500/80 text-white font-semibold"
          >
            End session
          </button>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl bg-felt p-3">
      <div className="text-xs uppercase tracking-wide text-white/60">{label}</div>
      <div className="text-2xl font-mono">{value}</div>
      {sub && <div className="text-xs text-white/50">{sub}</div>}
    </div>
  );
}
