import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { RouletteWheel } from "../components/RouletteWheel";
import {
  ApiError,
  CasinoParticipant,
  CasinoSessionView,
  Roulette as RouletteApi,
} from "../lib/api";

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
    pocket: string; color: string; perParticipant: { label: string; profit: number }[];
  } | null>(null);
  const [wheelSpinning, setWheelSpinning] = useState(false);
  const [pendingPocket, setPendingPocket] = useState<string | null>(null);
  const [straightInput, setStraightInput] = useState("");
  const [joinCode, setJoinCode] = useState("");

  // Bootstrap.
  useEffect(() => {
    RouletteApi.me()
      .then(setSession)
      .catch((e) => {
        if (!(e instanceof ApiError && e.status === 404)) {
          setError(String(e));
        }
      })
      .finally(() => setLoading(false));
  }, []);

  // Live presence: poll every 4s so guests see each other join/leave +
  // see results land when the host spins.
  useEffect(() => {
    if (!session?.room_code) return;
    const id = window.setInterval(async () => {
      try {
        const next = await RouletteApi.me();
        setSession(next);
      } catch { /* ignore blips */ }
    }, 4000);
    return () => window.clearInterval(id);
  }, [session?.room_code]);

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
      });
      setSession(sess);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function joinRoom() {
    if (!joinCode.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await RouletteApi.joinByCode(joinCode.trim().toUpperCase(), {});
      const sess = await RouletteApi.me();
      setSession(sess);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function commitBetsAndMaybeSpin() {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      // Stage caller's bets server-side.
      await RouletteApi.stageBets(
        pendingBets.map((b) => ({
          bet_type: b.bet_type,
          stake: b.stake,
          selection: b.selection,
        })),
      );
      setPendingBets([]);
      const sess = await RouletteApi.me();
      setSession(sess);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function spinWheel() {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      const result = await RouletteApi.spin();
      const spin = result.spin!;
      // Kick the wheel animation off immediately with the target
      // pocket; the result text + bankroll refresh wait until the
      // animation has played out so the ball lands BEFORE the
      // outcome lights up.
      setPendingPocket(spin.pocket);
      setWheelSpinning(true);
      await new Promise((res) => window.setTimeout(res, 3500));
      setWheelSpinning(false);
      setLastSpin({
        pocket: spin.pocket,
        color: spin.color,
        perParticipant: result.participants.map((p) => ({
          label: p.label,
          profit: p.total_profit,
        })),
      });
      const next = await RouletteApi.me();
      setSession(next);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
      setWheelSpinning(false);
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
    return <div className="min-h-screen flex items-center justify-center text-white/40">loading…</div>;
  }

  if (!session) {
    return (
      <div className="min-h-screen px-4 py-6 max-w-md mx-auto space-y-4"
           style={{ paddingTop: "calc(env(safe-area-inset-top) + 16px)" }}>
        <Link to="/" className="text-white/60 text-sm">← home</Link>
        <h1 className="text-2xl font-bold">Roulette</h1>
        <p className="text-sm text-white/70">
          American wheel (38 pockets, 5.26% house edge). Bankroll starts at $500.
          Share the room code after starting and friends can bet alongside you.
        </p>
        <button
          onClick={startSession}
          disabled={busy}
          className="w-full min-h-touch rounded-xl bg-white text-felt-dark font-semibold disabled:opacity-50"
        >
          Sit at the wheel
        </button>
        <div className="rounded-xl bg-felt p-3 space-y-2">
          <div className="text-xs uppercase tracking-wide text-white/60">
            Or join a friend's room
          </div>
          <div className="flex gap-2">
            <input
              autoCapitalize="characters"
              placeholder="ABC234"
              value={joinCode}
              onChange={(e) => setJoinCode(e.target.value.toUpperCase().slice(0, 6))}
              className="flex-1 min-h-touch rounded-lg bg-felt-dark text-white font-mono px-3"
            />
            <button
              onClick={joinRoom}
              disabled={busy || joinCode.length < 4}
              className="min-h-touch px-4 rounded-lg border border-white/20 text-sm disabled:opacity-30"
            >
              Join
            </button>
          </div>
        </div>
        {error && <div className="text-red-300 text-sm">{error}</div>}
      </div>
    );
  }

  const isHost = session.caller_is_host;
  const callerBankroll = session.caller_bankroll;
  const callerPending = (session.caller_pending_bets ?? []) as Array<{ bet_type: string; stake: number; selection?: unknown }>;
  const stagedTotal = callerPending.reduce((s, b) => s + b.stake, 0);

  return (
    <div className="min-h-screen px-3 py-3 flex flex-col gap-3"
         style={{
           paddingTop: "calc(env(safe-area-inset-top) + 12px)",
           paddingBottom: "calc(env(safe-area-inset-bottom) + 16px)",
         }}>
      <div className="flex items-center justify-between">
        <Link to="/" className="text-white/60 text-sm">←</Link>
        <div className="text-center">
          <div className="text-xs text-white/50">{isHost ? "Bankroll" : "Your bankroll"}</div>
          <div className="font-mono text-xl">${callerBankroll}</div>
        </div>
        <button onClick={endSession} className="text-white/60 text-xs underline">
          {isHost ? "end" : "leave"}
        </button>
      </div>

      {session.room_code && (
        <div className="rounded-xl bg-felt p-2 text-center text-xs">
          Room <span className="font-mono text-base tracking-widest">{session.room_code}</span>
          {" · "}
          {session.participants.length} player{session.participants.length === 1 ? "" : "s"}
        </div>
      )}

      {(pendingPocket || lastSpin) && (
        <div className="rounded-xl bg-felt p-3 pb-5">
          <RouletteWheel
            kind={(session.rules.wheel_kind as "american" | "european") ?? "american"}
            pocket={pendingPocket}
            spinning={wheelSpinning}
          />
          {lastSpin && !wheelSpinning && (
            <div className="text-xs text-white/70 mt-3 text-center">
              {lastSpin.perParticipant.map((p, i) => (
                <span key={i} className="mx-1">
                  {p.label}: <span className={p.profit >= 0 ? "text-emerald-300" : "text-red-300"}>
                    {p.profit >= 0 ? "+" : ""}${p.profit}
                  </span>
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      <ParticipantsList participants={session.participants} />

      <div className="rounded-xl bg-felt p-3 space-y-2">
        <div className="text-xs uppercase tracking-wide text-white/60">Bet unit</div>
        <div className="flex gap-2">
          {[1, 5, 25, 100].map((v) => (
            <button
              key={v}
              onClick={() => setUnitBet(v)}
              className={`flex-1 min-h-touch rounded-lg ${
                unitBet === v ? "bg-white text-felt-dark" : "border border-white/20 text-white"
              }`}
            >
              ${v}
            </button>
          ))}
        </div>
      </div>

      <div className="rounded-xl bg-felt p-3 space-y-2">
        <div className="text-xs uppercase tracking-wide text-white/60">Outside bets</div>
        <div className="grid grid-cols-3 gap-2">
          {OUTSIDE_BETS.map((b) => (
            <button
              key={b.bet_type}
              onClick={() => addBet({ bet_type: b.bet_type, stake: unitBet, label: b.label })}
              className="min-h-touch rounded-lg border border-white/20 text-sm"
            >
              + {b.label}
            </button>
          ))}
          {DOZENS.map((d) => (
            <button
              key={`dozen-${d.sel}`}
              onClick={() => addBet({ bet_type: "dozen", stake: unitBet, selection: d.sel, label: d.label })}
              className="min-h-touch rounded-lg border border-white/20 text-sm"
            >
              + {d.label}
            </button>
          ))}
        </div>
      </div>

      <div className="rounded-xl bg-felt p-3 space-y-2">
        <div className="text-xs uppercase tracking-wide text-white/60">Straight up (35:1)</div>
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

      {(pendingBets.length > 0 || stagedTotal > 0) && (
        <div className="rounded-xl bg-felt p-3 space-y-1 text-sm">
          <div className="text-xs uppercase tracking-wide text-white/60">
            Your bets
            {stagedTotal > 0 && (
              <span className="ml-2 text-white/40">staged ${stagedTotal}</span>
            )}
          </div>
          {pendingBets.map((b, i) => (
            <div key={i} className="flex items-center justify-between">
              <span>{b.label} (unstaged)</span>
              <span className="flex items-center gap-2">
                <span className="font-mono">${b.stake}</span>
                <button onClick={() => removeBet(i)} className="text-white/40 text-xs">✕</button>
              </span>
            </div>
          ))}
          {callerPending.map((b, i) => (
            <div key={`s${i}`} className="flex items-center justify-between text-emerald-200">
              <span>{b.bet_type}{b.selection != null ? ` ${String(b.selection)}` : ""}</span>
              <span className="font-mono">${b.stake}</span>
            </div>
          ))}
        </div>
      )}

      {error && <div className="text-red-300 text-sm">{error}</div>}

      <div className="mt-auto space-y-2">
        {pendingBets.length > 0 && (
          <button
            onClick={commitBetsAndMaybeSpin}
            disabled={busy}
            className="w-full min-h-touch rounded-xl border border-white/20 text-white"
          >
            {busy ? "Saving…" : `Stage ${pendingBets.length} bet${pendingBets.length === 1 ? "" : "s"}`}
          </button>
        )}
        {isHost ? (
          <button
            onClick={spinWheel}
            disabled={busy}
            className="w-full min-h-touch rounded-xl bg-white text-felt-dark font-semibold disabled:opacity-40"
          >
            {busy ? "Spinning…" : "Spin"}
          </button>
        ) : (
          <div className="w-full min-h-touch rounded-xl bg-felt p-3 text-center text-sm text-white/60">
            Waiting for the host to spin…
          </div>
        )}
      </div>
    </div>
  );
}

function ParticipantsList({ participants }: { participants: CasinoParticipant[] }) {
  if (participants.length <= 1) return null;
  return (
    <div className="rounded-xl bg-felt p-2 space-y-1">
      <div className="text-xs uppercase tracking-wide text-white/60">At the table</div>
      {participants.map((p, i) => (
        <div key={i} className="flex items-center justify-between text-sm">
          <span>
            <span className={p.is_host ? "text-amber-300" : "text-emerald-300"}>●</span>
            {" "}{p.label}{p.is_host && <span className="text-white/40 text-xs"> · host</span>}
          </span>
          <span className="font-mono">
            ${p.bankroll}
            {p.has_pending_bets && <span className="ml-2 text-emerald-300 text-xs">staged</span>}
          </span>
        </div>
      ))}
    </div>
  );
}
