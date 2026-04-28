import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  ApiError,
  CasinoParticipant,
  CasinoSessionView,
  Craps as CrapsApi,
} from "../lib/api";

interface BookBet {
  bet_id: string;
  bet_type: string;
  stake: number;
  selection?: number;
  established_point?: number | null;
}

const SIMPLE_BETS: { bet_type: string; label: string; phaseHint: string }[] = [
  { bet_type: "pass_line", label: "Pass Line", phaseHint: "1:1" },
  { bet_type: "dont_pass", label: "Don't Pass", phaseHint: "1:1, 12 push" },
  { bet_type: "field", label: "Field", phaseHint: "2/3/4/9/10/11/12" },
  { bet_type: "any_seven", label: "Any 7", phaseHint: "4:1 one-roll" },
  { bet_type: "any_craps", label: "Any Craps", phaseHint: "7:1 one-roll" },
];

const PLACE_NUMBERS = [4, 5, 6, 8, 9, 10];
const HARD_NUMBERS = [4, 6, 8, 10];

export default function Craps() {
  const [session, setSession] = useState<CasinoSessionView | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [unitBet, setUnitBet] = useState(5);
  const [lastRoll, setLastRoll] = useState<any>(null);
  const [joinCode, setJoinCode] = useState("");

  useEffect(() => {
    CrapsApi.me()
      .then(setSession)
      .catch((e) => {
        if (!(e instanceof ApiError && e.status === 404)) setError(String(e));
      })
      .finally(() => setLoading(false));
  }, []);

  // Live polling.
  useEffect(() => {
    if (!session?.room_code) return;
    const id = window.setInterval(async () => {
      try {
        const next = await CrapsApi.me();
        setSession(next);
      } catch { /* ignore */ }
    }, 4000);
    return () => window.clearInterval(id);
  }, [session?.room_code]);

  const phase = (session?.state as any)?.table?.phase ?? "come_out";
  const point = (session?.state as any)?.table?.point ?? null;
  const book: BookBet[] = ((session?.caller_book ?? []) as unknown) as BookBet[];
  const onTableTotal = book.reduce((s, b) => s + b.stake, 0);

  async function startSession() {
    setBusy(true);
    setError(null);
    try {
      const sess = await CrapsApi.create({ starting_bankroll: 500 });
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
      await CrapsApi.joinByCode(joinCode.trim().toUpperCase(), {});
      const sess = await CrapsApi.me();
      setSession(sess);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function addBet(bet_type: string, selection?: number) {
    if (!session) return;
    setError(null);
    try {
      await CrapsApi.addBets([{ bet_type, stake: unitBet, selection }]);
      const next = await CrapsApi.me();
      setSession(next);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    }
  }

  async function cancelBet(betId: string) {
    setError(null);
    try {
      await CrapsApi.cancelBet(betId);
      const next = await CrapsApi.me();
      setSession(next);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    }
  }

  async function rollDice() {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      const result = await CrapsApi.roll();
      setLastRoll(result);
      const next = await CrapsApi.me();
      setSession(next);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function endSession() {
    if (!confirm("End this craps session? Bankroll resets.")) return;
    await CrapsApi.destroy().catch(() => {});
    setSession(null);
    setLastRoll(null);
  }

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center text-white/40">loading…</div>;
  }

  if (!session) {
    return (
      <div className="min-h-screen px-4 py-6 max-w-md mx-auto space-y-4"
           style={{ paddingTop: "calc(env(safe-area-inset-top) + 16px)" }}>
        <Link to="/" className="text-white/60 text-sm">← home</Link>
        <h1 className="text-2xl font-bold">Craps</h1>
        <p className="text-sm text-white/70">
          Pass / Don't Pass + odds + Come / Don't Come + Place + Field + props
          + Hardways. Bankroll starts at $500.
        </p>
        <button
          onClick={startSession}
          disabled={busy}
          className="w-full min-h-touch rounded-xl bg-white text-felt-dark font-semibold disabled:opacity-50"
        >
          Belly up to the table
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
          {" · "}{session.participants.length} player{session.participants.length === 1 ? "" : "s"}
        </div>
      )}

      <div className="rounded-xl bg-felt p-3 text-center">
        <div className="text-xs uppercase tracking-wide text-white/60">
          {phase === "come_out" ? "Come-out" : `Point: ${point}`}
        </div>
        {lastRoll && (
          <>
            <div className="font-mono text-3xl mt-1">
              {lastRoll.roll.d1} + {lastRoll.roll.d2} = {lastRoll.roll.total}
            </div>
            <div className="text-xs text-white/70 mt-1">
              {(lastRoll.participants ?? []).map((p: any, i: number) => (
                <span key={i} className="mx-1">
                  {p.label}: <span className={p.total_profit >= 0 ? "text-emerald-300" : "text-red-300"}>
                    {p.total_profit >= 0 ? "+" : ""}${p.total_profit}
                  </span>
                </span>
              ))}
            </div>
          </>
        )}
      </div>

      <ParticipantsList participants={session.participants} />

      <div className="rounded-xl bg-felt p-3 space-y-2">
        <div className="text-xs uppercase tracking-wide text-white/60">Bet unit</div>
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

      <div className="grid grid-cols-2 gap-2">
        {SIMPLE_BETS.map((b) => (
          <button
            key={b.bet_type}
            onClick={() => addBet(b.bet_type)}
            className="rounded-xl bg-felt p-3 text-left"
          >
            <div className="text-sm">+ {b.label}</div>
            <div className="text-[11px] text-white/50">{b.phaseHint}</div>
          </button>
        ))}
      </div>

      <div className="rounded-xl bg-felt p-3 space-y-2">
        <div className="text-xs uppercase tracking-wide text-white/60">Place numbers</div>
        <div className="grid grid-cols-6 gap-1">
          {PLACE_NUMBERS.map((n) => (
            <button
              key={n}
              onClick={() => addBet("place", n)}
              className="min-h-touch rounded-lg border border-white/20 text-sm font-mono"
            >
              {n}
            </button>
          ))}
        </div>
      </div>

      <div className="rounded-xl bg-felt p-3 space-y-2">
        <div className="text-xs uppercase tracking-wide text-white/60">Hardways</div>
        <div className="grid grid-cols-4 gap-1">
          {HARD_NUMBERS.map((n) => (
            <button
              key={n}
              onClick={() => addBet("hard", n)}
              className="min-h-touch rounded-lg border border-white/20 text-sm font-mono"
            >
              Hard {n}
            </button>
          ))}
        </div>
      </div>

      {book.length > 0 && (
        <div className="rounded-xl bg-felt p-3 space-y-1">
          <div className="text-xs uppercase tracking-wide text-white/60">
            On the table · ${onTableTotal}
          </div>
          {book.map((b) => (
            <div key={b.bet_id} className="flex items-center justify-between text-sm">
              <span>
                {b.bet_type.replace(/_/g, " ")}
                {b.selection != null && ` ${b.selection}`}
                {b.established_point != null && ` (point ${b.established_point})`}
              </span>
              <span className="flex items-center gap-2">
                <span className="font-mono">${b.stake}</span>
                <button onClick={() => cancelBet(b.bet_id)} className="text-white/40 text-xs">✕</button>
              </span>
            </div>
          ))}
        </div>
      )}

      {error && <div className="text-red-300 text-sm">{error}</div>}

      {isHost ? (
        <button
          onClick={rollDice}
          disabled={busy}
          className="mt-auto w-full min-h-touch rounded-xl bg-white text-felt-dark font-semibold disabled:opacity-40"
        >
          {busy ? "Rolling…" : "Roll the dice"}
        </button>
      ) : (
        <div className="mt-auto w-full rounded-xl bg-felt p-3 text-center text-sm text-white/60">
          Waiting for the shooter to roll…
        </div>
      )}
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
            {p.open_bets ? <span className="ml-2 text-emerald-300 text-xs">{p.open_bets} bet{p.open_bets === 1 ? "" : "s"}</span> : null}
          </span>
        </div>
      ))}
    </div>
  );
}
