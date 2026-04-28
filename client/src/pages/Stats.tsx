import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ApiError, SessionStatsView, Sessions } from "../lib/api";
import { useApp } from "../lib/store";

export default function Stats() {
  const { session, setSession } = useApp();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<SessionStatsView | null>(null);

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

  // Always re-pull derived stats; the cached session view in the store
  // doesn't include EV-lost / win-rate.
  useEffect(() => {
    Sessions.stats()
      .then(setStats)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 404) {
          // Will be handled by the session redirect above.
        } else {
          setError(String(e));
        }
      });
  }, [session?.stats.hands_played]);

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
          <Stat label="Hands played" value={String(stats?.hands_played ?? session.stats.hands_played)} />
          <Stat
            label="Win rate"
            value={stats ? `${stats.rates.win_pct}%` : "—"}
            sub={
              stats
                ? `${stats.wins}W / ${stats.losses}L / ${stats.pushes}P`
                : undefined
            }
          />
          <Stat
            label="Book mistakes"
            value={String(stats?.book_mistakes ?? session.stats.book_mistakes)}
            sub={stats ? `${stats.rates.mistake_pct}% of hands` : undefined}
          />
          <Stat
            label="EV lost (est.)"
            value={stats ? `$${stats.ev_lost_dollars.toFixed(2)}` : "—"}
            sub="heuristic"
          />
          <Stat
            label="Player blackjacks"
            value={String(stats?.player_blackjacks ?? session.stats.player_blackjacks)}
          />
          <Stat label="Busts" value={String(stats?.busts ?? session.stats.busts)} />
          <Stat label="Surrenders" value={String(stats?.surrenders ?? session.stats.surrenders)} />
          <Stat label="Cards seen" value={String(session.counter.cards_seen)} />
          <Stat
            label="Running count"
            value={String(session.counter.running_count)}
          />
        </div>

        {stats && stats.ev_lost_dollars > 0 && (
          <div className="text-xs text-white/50">
            EV-lost is a heuristic estimate based on your action vs the book —
            not a true Monte Carlo expected-value calculation. Use it for
            direction (mistakes are costing you ~${stats.ev_lost_dollars.toFixed(0)}),
            not absolute accuracy.
          </div>
        )}

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
