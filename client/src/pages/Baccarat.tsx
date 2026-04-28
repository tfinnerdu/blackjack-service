import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { CardFace } from "../components/Card";
import {
  ApiError,
  Baccarat as BaccaratApi,
  CasinoParticipant,
  CasinoSessionView,
} from "../lib/api";

const BETS: { bet_type: string; label: string; payout: string }[] = [
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
  const [lastResult, setLastResult] = useState<any>(null);
  const [unitBet, setUnitBet] = useState(10);
  const [joinCode, setJoinCode] = useState("");

  useEffect(() => {
    BaccaratApi.me()
      .then(setSession)
      .catch((e) => {
        if (!(e instanceof ApiError && e.status === 404)) setError(String(e));
      })
      .finally(() => setLoading(false));
  }, []);

  // Live presence polling.
  useEffect(() => {
    if (!session?.room_code) return;
    const id = window.setInterval(async () => {
      try {
        const next = await BaccaratApi.me();
        setSession(next);
      } catch { /* ignore */ }
    }, 4000);
    return () => window.clearInterval(id);
  }, [session?.room_code]);

  function bumpStake(bet_type: string) {
    setStakes((s) => ({ ...s, [bet_type]: (s[bet_type] ?? 0) + unitBet }));
  }
  function clearStake(bet_type: string) {
    setStakes((s) => { const next = { ...s }; delete next[bet_type]; return next; });
  }
  function clearAll() { setStakes({}); }

  const totalStake = Object.values(stakes).reduce((s, v) => s + v, 0);
  const placedBets = Object.entries(stakes).filter(([_, v]) => v > 0)
    .map(([bet_type, stake]) => ({ bet_type, stake }));

  async function startSession() {
    setBusy(true);
    setError(null);
    try {
      const sess = await BaccaratApi.create({ starting_bankroll: 500 });
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
      await BaccaratApi.joinByCode(joinCode.trim().toUpperCase(), {});
      const sess = await BaccaratApi.me();
      setSession(sess);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function stage() {
    if (!session || placedBets.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      await BaccaratApi.stageBets(placedBets);
      setStakes({});
      const next = await BaccaratApi.me();
      setSession(next);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function deal() {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      const result = await BaccaratApi.play();
      setLastResult(result);
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
          Punto Banco — bet on Player, Banker, or Tie. House draws by fixed
          rules. Bankroll starts at $500.
        </p>
        <button
          onClick={startSession}
          disabled={busy}
          className="w-full min-h-touch rounded-xl bg-white text-felt-dark font-semibold disabled:opacity-50"
        >
          Sit at the shoe
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

  const round = lastResult?.round;
  const isHost = session.caller_is_host;
  const callerBankroll = session.caller_bankroll;
  const stagedBets = (session.caller_pending_bets ?? []) as Array<{ bet_type: string; stake: number }>;
  const stagedTotal = stagedBets.reduce((s, b) => s + b.stake, 0);

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

      {round && (
        <div className="rounded-xl bg-felt p-3 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="text-xs uppercase tracking-wide text-white/60">Player</div>
              <div className="flex gap-1 my-1 flex-wrap">
                {round.player_cards.map((c: any, i: number) => <CardFace key={i} card={c} />)}
              </div>
              <div className="font-mono">Total {round.player_total}</div>
            </div>
            <div>
              <div className="text-xs uppercase tracking-wide text-white/60">Banker</div>
              <div className="flex gap-1 my-1 flex-wrap">
                {round.banker_cards.map((c: any, i: number) => <CardFace key={i} card={c} />)}
              </div>
              <div className="font-mono">Total {round.banker_total}</div>
            </div>
          </div>
          <div className="text-center text-sm">
            <span className={
              round.outcome === "player" ? "text-emerald-300"
              : round.outcome === "banker" ? "text-amber-300"
              : "text-sky-300"
            }>{round.outcome.toUpperCase()} wins</span>
            {round.natural && <span className="text-white/60"> · natural</span>}
          </div>
          <div className="text-xs text-white/70 text-center">
            {(lastResult.participants ?? []).map((p: any, i: number) => (
              <span key={i} className="mx-1">
                {p.label}: <span className={p.total_profit >= 0 ? "text-emerald-300" : "text-red-300"}>
                  {p.total_profit >= 0 ? "+" : ""}${p.total_profit}
                </span>
              </span>
            ))}
          </div>
        </div>
      )}

      <ParticipantsList participants={session.participants} />

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
            <span className="text-sm">
              {b.label} <span className="text-white/40 text-xs">({b.payout})</span>
            </span>
            <span className="font-mono">${stakes[b.bet_type] ?? 0}</span>
          </button>
        ))}
      </div>

      {(stagedBets.length > 0 || stagedTotal > 0) && (
        <div className="rounded-xl bg-felt/50 p-2 text-xs space-y-1">
          <div className="text-white/60 uppercase tracking-wide">Staged with house</div>
          {stagedBets.map((b, i) => (
            <div key={i} className="flex justify-between text-emerald-200">
              <span>{b.bet_type}</span>
              <span className="font-mono">${b.stake}</span>
            </div>
          ))}
        </div>
      )}

      {error && <div className="text-red-300 text-sm">{error}</div>}

      <div className="mt-auto space-y-2">
        {placedBets.length > 0 && (
          <button
            onClick={stage}
            disabled={busy || totalStake > callerBankroll}
            className="w-full min-h-touch rounded-xl border border-white/20"
          >
            {busy ? "Staging…" : `Stage $${totalStake}`}
          </button>
        )}
        {isHost ? (
          <button
            onClick={deal}
            disabled={busy}
            className="w-full min-h-touch rounded-xl bg-white text-felt-dark font-semibold disabled:opacity-40"
          >
            {busy ? "Dealing…" : "Deal"}
          </button>
        ) : (
          <div className="w-full rounded-xl bg-felt p-3 text-center text-sm text-white/60">
            Waiting for the host to deal…
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
