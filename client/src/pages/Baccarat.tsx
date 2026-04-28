import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { CardFace } from "../components/Card";
import { ApiError, Baccarat as BaccaratApi, CasinoSessionView } from "../lib/api";

interface BetRow {
  bet_type: "player" | "banker" | "tie" | "player_pair" | "banker_pair";
  label: string;
  payout: string;
  stake: number;
}

const BETS: Omit<BetRow, "stake">[] = [
  { bet_type: "player", label: "Player", payout: "1:1" },
  { bet_type: "banker", label: "Banker", payout: "1:1 - 5%" },
  { bet_type: "tie", label: "Tie", payout: "8:1" },
  { bet_type: "player_pair", label: "Player pair", payout: "11:1" },
  { bet_type: "banker_pair", label: "Banker pair", payout: "11:1" },
];

export default function Baccarat() {
  const [session, setSession] = useState<CasinoSessionView | null>(null);
  const [loading, setLoading] = useState(true);
  const [stakes, setStakes] = useState<Record<string, number>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<{
    round: any;
    payouts: number[];
    total_profit: number;
  } | null>(null);
  const [unitBet, setUnitBet] = useState(10);

  useEffect(() => {
    BaccaratApi.me()
      .then(setSession)
      .catch((e) => {
        if (!(e instanceof ApiError && e.status === 404)) {
          setError(String(e));
        }
      })
      .finally(() => setLoading(false));
  }, []);

  function bumpStake(bet_type: string) {
    setStakes((s) => ({ ...s, [bet_type]: (s[bet_type] ?? 0) + unitBet }));
  }
  function clearStake(bet_type: string) {
    setStakes((s) => {
      const next = { ...s };
      delete next[bet_type];
      return next;
    });
  }
  function clearAll() {
    setStakes({});
  }

  const totalStake = Object.values(stakes).reduce((s, v) => s + v, 0);
  const placedBets = Object.entries(stakes)
    .filter(([_, v]) => v > 0)
    .map(([bet_type, stake]) => ({ bet_type, stake }));

  async function startSession() {
    setBusy(true);
    setError(null);
    try {
      const sess = await BaccaratApi.create({
        starting_bankroll: 500, decks: 8, min_bet: 1, max_bet: 500,
      });
      setSession(sess);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function play() {
    if (!session || placedBets.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const result = await BaccaratApi.play(placedBets as any);
      setLastResult(result);
      setStakes({});
      const next = await BaccaratApi.me();
      setSession(next);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function endSession() {
    if (!confirm("End this baccarat session? Bankroll resets.")) return;
    await BaccaratApi.destroy().catch(() => {});
    setSession(null);
    setStakes({});
    setLastResult(null);
  }

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center text-white/40">loading…</div>;
  }

  if (!session) {
    return (
      <div className="min-h-screen px-4 py-6 max-w-md mx-auto space-y-4"
           style={{ paddingTop: "calc(env(safe-area-inset-top) + 16px)" }}>
        <Link to="/" className="text-white/60 text-sm">← home</Link>
        <h1 className="text-2xl font-bold">Baccarat</h1>
        <p className="text-sm text-white/70">
          Punto Banco — bet on Player, Banker, or Tie. The house draws by
          fixed rules. Bankroll starts at $500.
        </p>
        <button
          onClick={startSession}
          disabled={busy}
          className="w-full min-h-touch rounded-xl bg-white text-felt-dark font-semibold disabled:opacity-50"
        >
          Sit at the shoe
        </button>
        {error && <div className="text-red-300 text-sm">{error}</div>}
      </div>
    );
  }

  const round = lastResult?.round;

  return (
    <div className="min-h-screen px-3 py-3 flex flex-col gap-3"
         style={{
           paddingTop: "calc(env(safe-area-inset-top) + 12px)",
           paddingBottom: "calc(env(safe-area-inset-bottom) + 16px)",
         }}>
      <div className="flex items-center justify-between">
        <Link to="/" className="text-white/60 text-sm">←</Link>
        <div className="text-center">
          <div className="text-xs text-white/50">Bankroll</div>
          <div className="font-mono text-xl">${session.bankroll}</div>
        </div>
        <button onClick={endSession} className="text-white/60 text-xs underline">end</button>
      </div>

      {round && (
        <div className="rounded-xl bg-felt p-3 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="text-xs uppercase tracking-wide text-white/60">Player</div>
              <div className="flex gap-1 my-1 flex-wrap">
                {round.player_cards.map((c: any, i: number) => (
                  <CardFace key={i} card={c} />
                ))}
              </div>
              <div className="font-mono">Total {round.player_total}</div>
            </div>
            <div>
              <div className="text-xs uppercase tracking-wide text-white/60">Banker</div>
              <div className="flex gap-1 my-1 flex-wrap">
                {round.banker_cards.map((c: any, i: number) => (
                  <CardFace key={i} card={c} />
                ))}
              </div>
              <div className="font-mono">Total {round.banker_total}</div>
            </div>
          </div>
          <div className="text-center text-sm">
            <span className={
              round.outcome === "player"
                ? "text-emerald-300"
                : round.outcome === "banker"
                  ? "text-amber-300"
                  : "text-sky-300"
            }>
              {round.outcome.toUpperCase()} wins
            </span>
            {round.natural && <span className="text-white/60"> · natural</span>}
            {round.player_pair && <span className="text-white/60"> · player pair</span>}
            {round.banker_pair && <span className="text-white/60"> · banker pair</span>}
            <span className={`ml-2 font-mono ${
              (lastResult?.total_profit ?? 0) >= 0 ? "text-emerald-300" : "text-red-300"
            }`}>
              {(lastResult?.total_profit ?? 0) >= 0 ? "+" : ""}${lastResult?.total_profit ?? 0}
            </span>
          </div>
        </div>
      )}

      <div className="rounded-xl bg-felt p-3 space-y-2">
        <div className="flex items-center justify-between">
          <div className="text-xs uppercase tracking-wide text-white/60">Bet unit</div>
          <button onClick={clearAll} className="text-xs text-white/50 underline">clear</button>
        </div>
        <div className="flex gap-2">
          {[1, 5, 25, 100].map((v) => (
            <button
              key={v}
              onClick={() => setUnitBet(v)}
              className={`flex-1 min-h-touch rounded-lg ${
                unitBet === v ? "bg-white text-felt-dark" : "border border-white/20"
              }`}
            >
              ${v}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-2">
        {BETS.map((b) => (
          <button
            key={b.bet_type}
            onClick={() => bumpStake(b.bet_type)}
            onContextMenu={(e) => { e.preventDefault(); clearStake(b.bet_type); }}
            className="w-full rounded-xl bg-felt p-3 flex items-center justify-between"
          >
            <span className="text-sm">{b.label} <span className="text-white/40 text-xs">({b.payout})</span></span>
            <span className="font-mono">${stakes[b.bet_type] ?? 0}</span>
          </button>
        ))}
      </div>

      {error && <div className="text-red-300 text-sm">{error}</div>}

      <button
        onClick={play}
        disabled={busy || placedBets.length === 0 || totalStake > session.bankroll}
        className="mt-auto w-full min-h-touch rounded-xl bg-white text-felt-dark font-semibold disabled:opacity-40"
      >
        {busy ? "Dealing…" : placedBets.length === 0 ? "Place a bet first" : `Deal · $${totalStake}`}
      </button>
    </div>
  );
}
