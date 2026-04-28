import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ActionBar } from "../components/ActionBar";
import { CoachPanel } from "../components/CoachPanel";
import { Dealer } from "../components/Dealer";
import { RoundSummary } from "../components/RoundSummary";
import { SeatBlock, SeatPresenceDot } from "../components/Seat";
import { LoadingScreen } from "../components/LoadingScreen";
import { TableSurface } from "../components/TableSurface";
import { ApiError, Rounds, Seat, Sessions } from "../lib/api";
import { useApp } from "../lib/store";
import type { SessionView } from "../lib/types";

export default function Play() {
  const { session, round, setSession, setRound } = useApp();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [bet, setBet] = useState(10);
  const [busy, setBusy] = useState(false);
  const [joinLeaveToast, setJoinLeaveToast] = useState<string | null>(null);

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

  // Live presence: poll the session every 4s so the seat-occupancy view
  // stays fresh, and surface a toast when a guest joins or leaves.
  // We also refresh the round view so guests see the host's deal/actions.
  useEffect(() => {
    if (!session?.room_code) return;
    const interval = window.setInterval(async () => {
      try {
        const next = await Sessions.me();
        const before = Object.keys(session.seat_tokens ?? {});
        const after = Object.keys(next.seat_tokens ?? {});
        const joined = after.filter((s) => !before.includes(s));
        const left = before.filter((s) => !after.includes(s));
        if (joined.length > 0) {
          setJoinLeaveToast(`Player joined seat ${joined.join(", ")}`);
          window.setTimeout(() => setJoinLeaveToast(null), 4000);
        } else if (left.length > 0) {
          setJoinLeaveToast(`Seat ${left.join(", ")} opened up`);
          window.setTimeout(() => setJoinLeaveToast(null), 4000);
        }
        setSession(next);
      } catch {
        // Network blip — keep going.
      }
      // Refresh round if one's in flight (multi-player live updates).
      try {
        const r = await Rounds.active();
        setRound(r);
      } catch {
        // 404 = no round in flight; ignore.
      }
    }, 4000);
    return () => window.clearInterval(interval);
  }, [session?.room_code, session?.seat_tokens, setSession, setRound]);

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
    return <LoadingScreen
      label="loading blackjack table…"
      hint="First load can take a moment if the server has been idle."
    />;
  }

  const callerSeat = session.caller_seat ?? session.player_seat;
  const isHost = session.caller_is_host !== false; // default to host on legacy
  const guestAi = isHost
    ? null
    : session.ai_seats.find((a) => a.seat_num === callerSeat) ?? null;
  const headerBankroll = isHost ? session.bankroll : (guestAi?.bankroll ?? 0);

  const minBet = session.rules.min_bet;
  const maxBet = Math.min(session.rules.max_bet, headerBankroll);
  const inc = session.rules.bet_increment;
  const hideHole =
    !!round && (round.state === "playing" || round.state === "insurance" || round.state === "betting");

  // Seat occupancy lookup — used by SeatBlock to show host/guest/bot icons.
  const seatKindByNum: Record<number, "host" | "guest" | "ai"> = {};
  for (let n = 1; n <= session.rules.seats; n++) {
    if (n === session.player_seat) seatKindByNum[n] = "host";
    else if (session.seat_tokens && String(n) in session.seat_tokens)
      seatKindByNum[n] = "guest";
    else seatKindByNum[n] = "ai";
  }

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
          <div className="text-xs text-white/50">
            {isHost ? "Bankroll" : `You are seat ${callerSeat ?? "?"}`}
          </div>
          <div className="font-mono text-xl">${headerBankroll}</div>
        </div>
        <ShoeBadge session={session} />
      </div>

      {joinLeaveToast && (
        <div className="rounded-xl bg-emerald-500/20 ring-1 ring-emerald-300/40 px-3 py-2 text-sm text-emerald-100">
          {joinLeaveToast}
        </div>
      )}

      {/* Felt table: dealer at top, seats below. */}
      <TableSurface>
        {round ? (
          <Dealer dealer={round.dealer} hideHole={hideHole} />
        ) : (
          <div className="rounded-xl bg-black/15 ring-1 ring-white/10 p-3 text-white/60 text-sm text-center">
            Place a bet to deal.
          </div>
        )}

        {round && (
          <div className="space-y-3 mt-3">
            {round.seats.map((s) => (
              <SeatBlock
                key={s.seat_num}
                seat={s}
                isActive={round.active_seat_num === s.seat_num}
                activeHandIndex={round.active_hand_index}
                kind={seatKindByNum[s.seat_num] ?? "ai"}
                isYou={s.seat_num === callerSeat}
              />
            ))}
          </div>
        )}
      </TableSurface>

      {/* Pre-deal seat-occupancy summary (only when no round in flight) */}
      {!round && session.room_code && (
        <div className="rounded-xl bg-felt p-3 space-y-1">
          <div className="text-xs uppercase tracking-wide text-white/60">
            Table
          </div>
          {Object.entries(seatKindByNum).map(([n, kind]) => (
            <div key={n} className="flex items-center gap-2 text-sm">
              <SeatPresenceDot kind={kind as "host" | "guest" | "ai"} />
              <span className="font-mono w-6">{n}</span>
              <span className="flex-1">
                {kind === "host"
                  ? "Host"
                  : kind === "guest"
                    ? "Player"
                    : "Bot"}
                {Number(n) === callerSeat && (
                  <span className="text-emerald-300 ml-1">(you)</span>
                )}
              </span>
            </div>
          ))}
        </div>
      )}

      {round && <CoachPanel round={round} session={session} />}

      {error && <div className="text-red-300 text-sm">{error}</div>}

      {/* Action bar (playing or insurance) */}
      {round && (round.state === "playing" || round.state === "insurance") && (
        <ActionBar round={round} />
      )}

      {/* Completion summary */}
      {round && round.state === "complete" && (
        <RoundSummary round={round} session={session} onNext={() => setRound(null)} />
      )}

      {/* Bust-out: bankroll below the table minimum, no round in flight */}
      {!round && session.bankroll < session.rules.min_bet ? (
        <div className="mt-auto rounded-xl bg-felt p-4 text-center space-y-2">
          <div className="text-lg font-semibold">You're tapped out.</div>
          <div className="text-sm text-white/70">
            Bankroll ${session.bankroll} is below the ${session.rules.min_bet} minimum.
          </div>
          <Link
            to="/stats"
            className="block w-full min-h-touch flex items-center justify-center rounded-xl border border-white/20"
          >
            View stats / start over
          </Link>
        </div>
      ) : null}

      {/* Guest bet picker — set my own bet for the next round. */}
      {!round && !isHost && (
        <GuestBetPanel
          session={session}
          onUpdated={(bet) =>
            setSession({ ...session, caller_seat_bet: bet } as SessionView)
          }
        />
      )}

      {/* Pre-deal bet panel — host only, when no round AND bankroll is healthy */}
      {!round && isHost && session.bankroll >= session.rules.min_bet ? (
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

function GuestBetPanel({
  session,
  onUpdated,
}: {
  session: SessionView;
  onUpdated: (bet: number) => void;
}) {
  // Guest's chosen bet for the next round. Defaults to whatever the
  // server has stored, falling back to the AI seat's base_bet so the
  // initial value matches what'll actually be wagered.
  const callerSeat = session.caller_seat ?? 0;
  const aiSeat = session.ai_seats.find((a) => a.seat_num === callerSeat);
  const stored = session.caller_seat_bet ?? aiSeat?.base_bet ?? session.rules.min_bet;
  const [bet, setBet] = useState<number>(stored);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const min = session.rules.min_bet;
  const max = session.rules.max_bet;
  const inc = session.rules.bet_increment;

  async function commit(value: number) {
    setBusy(true);
    setErr(null);
    try {
      const r = await Seat.setBet(value);
      onUpdated(r.bet);
    } catch (e) {
      setErr(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-auto rounded-xl bg-felt p-3 space-y-2">
      <div className="text-xs uppercase tracking-wide text-white/60">
        Your bet for the next round
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={() => setBet((b) => Math.max(min, b - inc))}
          className="min-w-[44px] min-h-touch rounded-lg border border-white/20 text-xl"
        >
          −
        </button>
        <div className="flex-1 text-center font-mono text-xl">${bet}</div>
        <button
          onClick={() => setBet((b) => Math.min(max, b + inc))}
          className="min-w-[44px] min-h-touch rounded-lg border border-white/20 text-xl"
        >
          +
        </button>
      </div>
      <button
        onClick={() => commit(bet)}
        disabled={busy || bet < min || bet > max}
        className="w-full min-h-touch rounded-xl border border-white/20 text-sm disabled:opacity-30"
      >
        {busy ? "Saving…" : "Save my bet"}
      </button>
      {err && <div className="text-red-300 text-xs">{err}</div>}
      <div className="text-[11px] text-white/50 text-center">
        Host triggers the deal. Your saved bet will be used for your seat.
      </div>
    </div>
  );
}

function ShoeBadge({ session }: { session: SessionView }) {
  // Shows decks + cards remaining until cut card. Cut-card position
  // varies per shuffle (jitter), so the count is approximate but
  // close enough that a counter can plan around it. Falls back to
  // "—" on a CSM table where there's no cut card.
  const decks = session.rules.decks;
  const isCsm = session.rules.shuffle_mode === "csm";
  const dealt = session.shoe.cards_dealt ?? 0;
  const totalCards = decks * 52;
  // The server doesn't expose the per-shuffle cut index (it jitters
  // around `penetration`); approximate by taking the configured
  // penetration and subtracting cards_dealt.
  const cutTarget = Math.round(totalCards * session.rules.penetration);
  const cardsToCut = Math.max(0, cutTarget - dealt);

  return (
    <Link
      to="/stats"
      className="text-right text-[11px] leading-tight text-white/60 hover:text-white/80"
      title="cards until cut · click for stats"
    >
      <div className="font-mono">{decks}D</div>
      <div className="font-mono">
        {isCsm ? "CSM" : `${cardsToCut} to cut`}
      </div>
    </Link>
  );
}
