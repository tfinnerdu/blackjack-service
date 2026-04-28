import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { ApiError, CasinoSessionView, Roulette as RouletteApi } from "../lib/api";

interface PlacedBet {
  bet_type: string;
  stake: number;
  selection?: unknown;
  label: string;
}

const OUTSIDE_BETS: { bet_type: string; label: string }[] = [
  { bet_type: "red", label: "Red" },
  { bet_type: "black", label: "Black" },
  { bet_type: "even", label: "Even" },
  { bet_type: "odd", label: "Odd" },
  { bet_type: "low", label: "Low (1-18)" },
  { bet_type: "high", label: "High (19-36)" },
];

const DOZENS: { sel: number; label: string }[] = [
  { sel: 1, label: "1st 12" },
  { sel: 2, label: "2nd 12" },
  { sel: 3, label: "3rd 12" },
];

export default function Roulette() {
  const [session, setSession] = useState<CasinoSessionView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [unitBet, setUnitBet] = useState(5);
  const [pendingBets, setPendingBets] = useState<PlacedBet[]>([]);
  const [busy, setBusy] = useState(false);
  const [lastSpin, setLastSpin] = useState<{
    pocket: string; color: string; profit: number;
  } | null>(null);
  const [straightInput, setStraightInput] = useState("");

  // Bootstrap: load existing session.
  useEffect(() => {
    RouletteApi.me()
      .then(setSession)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 404) {
          // No session — let the user start one.
        } else {
          setError(String(e));
        }
      })
      .finally(() => setLoading(false));
  }, []);

  const totalStake = useMemo(
    () => pendingBets.reduce((s, b) => s + b.stake, 0),
    [pendingBets],
  );

  function addBet(bet: PlacedBet) {
    setPendingBets((cur) => [...cur, bet]);
  }

  function removeBet(i: number) {
    setPendingBets((cur) => cur.filter((_, idx) => idx !== i));
  }

  async function startSession() {
    setError(null);
    setBusy(true);
    try {
      const sess = await RouletteApi.create({
        starting_bankroll: 500,
        wheel_kind: "american",
        min_bet: 1,
        max_bet: 500,
      });
      setSession(sess);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function spin() {
    if (!session || pendingBets.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const result = await RouletteApi.spin(
        pendingBets.map((b) => ({
          bet_type: b.bet_type,
          stake: b.stake,
          selection: b.selection,
        })),
      );
      setLastSpin({
        pocket: result.spin.pocket,
        color: result.spin.color,
        profit: result.total_profit,
      });
      setPendingBets([]);
      // Refresh session to get the new bankroll.
      const next = await RouletteApi.me();
      setSession(next);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function endSession() {
    if (!confirm("End this roulette session? Bankroll resets.")) return;
    try {
      await RouletteApi.destroy();
      setSession(null);
      setPendingBets([]);
      setLastSpin(null);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-white/40">
        loading…
      </div>
    );
  }

  if (!session) {
    return (
      <div
        className="min-h-screen px-4 py-6 max-w-md mx-auto space-y-4"
        style={{ paddingTop: "calc(env(safe-area-inset-top) + 16px)" }}
      >
        <Link to="/" className="text-white/60 text-sm">← home</Link>
        <h1 className="text-2xl font-bold">Roulette</h1>
        <p className="text-sm text-white/70">
          American wheel (38 pockets, 5.26% house edge). Bankroll starts at $500.
        </p>
        <button
          onClick={startSession}
          disabled={busy}
          className="w-full min-h-touch rounded-xl bg-white text-felt-dark font-semibold disabled:opacity-50"
        >
          Sit at the wheel
        </button>
        {error && <div className="text-red-300 text-sm">{error}</div>}
      </div>
    );
  }

  return (
    <div
      className="min-h-screen px-3 py-3 flex flex-col gap-3"
      style={{
        paddingTop: "calc(env(safe-area-inset-top) + 12px)",
        paddingBottom: "calc(env(safe-area-inset-bottom) + 16px)",
      }}
    >
      <div className="flex items-center justify-between">
        <Link to="/" className="text-white/60 text-sm">←</Link>
        <div className="text-center">
          <div className="text-xs text-white/50">Bankroll</div>
          <div className="font-mono text-xl">${session.bankroll}</div>
        </div>
        <button onClick={endSession} className="text-white/60 text-xs underline">end</button>
      </div>

      {lastSpin && (
        <div
          className="rounded-xl p-3 text-center"
          style={{
            background:
              lastSpin.color === "red"
                ? "rgba(220, 38, 38, 0.25)"
                : lastSpin.color === "black"
                  ? "rgba(0, 0, 0, 0.45)"
                  : "rgba(16, 185, 129, 0.25)",
          }}
        >
          <div className="text-xs text-white/70 uppercase tracking-wide">
            last spin
          </div>
          <div className="text-4xl font-bold font-mono">{lastSpin.pocket}</div>
          <div className={`text-sm ${lastSpin.profit >= 0 ? "text-emerald-300" : "text-red-300"}`}>
            {lastSpin.profit >= 0 ? "+" : ""}${lastSpin.profit}
          </div>
        </div>
      )}

      <div className="rounded-xl bg-felt p-3 space-y-2">
        <div className="text-xs uppercase tracking-wide text-white/60">
          Bet unit
        </div>
        <div className="flex gap-2">
          {[1, 5, 25, 100].map((v) => (
            <button
              key={v}
              onClick={() => setUnitBet(v)}
              className={`flex-1 min-h-touch rounded-lg ${
                unitBet === v
                  ? "bg-white text-felt-dark"
                  : "border border-white/20 text-white"
              }`}
            >
              ${v}
            </button>
          ))}
        </div>
      </div>

      <div className="rounded-xl bg-felt p-3 space-y-2">
        <div className="text-xs uppercase tracking-wide text-white/60">
          Outside bets
        </div>
        <div className="grid grid-cols-3 gap-2">
          {OUTSIDE_BETS.map((b) => (
            <button
              key={b.bet_type}
              onClick={() =>
                addBet({ bet_type: b.bet_type, stake: unitBet, label: b.label })
              }
              className="min-h-touch rounded-lg border border-white/20 text-sm"
            >
              + {b.label}
            </button>
          ))}
          {DOZENS.map((d) => (
            <button
              key={`dozen-${d.sel}`}
              onClick={() =>
                addBet({
                  bet_type: "dozen",
                  stake: unitBet,
                  selection: d.sel,
                  label: d.label,
                })
              }
              className="min-h-touch rounded-lg border border-white/20 text-sm"
            >
              + {d.label}
            </button>
          ))}
        </div>
      </div>

      <div className="rounded-xl bg-felt p-3 space-y-2">
        <div className="text-xs uppercase tracking-wide text-white/60">
          Straight up (35:1)
        </div>
        <div className="flex gap-2">
          <input
            placeholder="0, 00, 1-36"
            value={straightInput}
            onChange={(e) => setStraightInput(e.target.value.toUpperCase())}
            className="flex-1 min-h-touch rounded-lg bg-felt-dark text-white px-3 font-mono"
          />
          <button
            disabled={!straightInput.trim()}
            onClick={() => {
              addBet({
                bet_type: "straight",
                stake: unitBet,
                selection: straightInput.trim(),
                label: `Straight ${straightInput.trim()}`,
              });
              setStraightInput("");
            }}
            className="min-h-touch px-3 rounded-lg border border-white/20 text-sm disabled:opacity-30"
          >
            Add
          </button>
        </div>
      </div>

      {pendingBets.length > 0 && (
        <div className="rounded-xl bg-felt p-3 space-y-1">
          <div className="text-xs uppercase tracking-wide text-white/60">
            Pending bets · ${totalStake} total
          </div>
          {pendingBets.map((b, i) => (
            <div key={i} className="flex items-center justify-between text-sm">
              <span>{b.label}</span>
              <span className="flex items-center gap-2">
                <span className="font-mono">${b.stake}</span>
                <button
                  onClick={() => removeBet(i)}
                  className="text-white/40 text-xs"
                >
                  ✕
                </button>
              </span>
            </div>
          ))}
        </div>
      )}

      {error && <div className="text-red-300 text-sm">{error}</div>}

      <button
        onClick={spin}
        disabled={busy || pendingBets.length === 0 || totalStake > session.bankroll}
        className="mt-auto w-full min-h-touch rounded-xl bg-white text-felt-dark font-semibold disabled:opacity-40"
      >
        {busy ? "Spinning…" : pendingBets.length === 0 ? "Place a bet first" : "Spin"}
      </button>
    </div>
  );
}
