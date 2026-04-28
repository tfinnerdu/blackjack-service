import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { CardFace } from "../components/Card";
import { LoadingScreen } from "../components/LoadingScreen";
import { TableSurface } from "../components/TableSurface";
import { ApiError } from "../lib/api";
import { PersonalityAggregate, Poker, PokerSessionView, RoundView } from "../lib/poker";

export default function PokerTable() {
  const navigate = useNavigate();
  const [session, setSession] = useState<PokerSessionView | null>(null);
  const [round, setRound] = useState<RoundView | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [raiseAmount, setRaiseAmount] = useState<number | null>(null);
  const [discardSelected, setDiscardSelected] = useState<Set<number>>(new Set());

  useEffect(() => {
    Poker.getSession()
      .then(setSession)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 404) navigate("/poker/sim/setup");
        else setError(String(e));
      });
  }, [navigate]);

  useEffect(() => {
    if (!session) return;
    Poker.activeHand()
      .then(setRound)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 404) {
          setRound(null);
        } else {
          setError(String(e));
        }
      });
  }, [session]);

  // Refresh session after a hand completes so stacks stay current.
  useEffect(() => {
    if (round?.state === "complete") {
      Poker.getSession().then(setSession).catch(() => {});
    }
  }, [round?.state]);

  async function startHand() {
    setBusy(true);
    setError(null);
    try {
      const r = await Poker.startHand();
      setRound(r);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function act(action: string, amount?: number) {
    setBusy(true);
    setError(null);
    try {
      const r = await Poker.act(action, amount);
      setRound(r);
      setRaiseAmount(null);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function confirmDiscard() {
    setBusy(true);
    setError(null);
    try {
      const indices = Array.from(discardSelected).sort((a, b) => a - b);
      const r = await Poker.discard(indices);
      setRound(r);
      setDiscardSelected(new Set());
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  }

  function toggleDiscardIdx(i: number, max: number) {
    setDiscardSelected((cur) => {
      const next = new Set(cur);
      if (next.has(i)) next.delete(i);
      else if (next.size < max) next.add(i);
      return next;
    });
  }

  async function endSession() {
    if (!confirm("End this poker session? Stacks will be lost.")) return;
    await Poker.endSession();
    navigate("/poker");
  }

  if (!session) {
    return <LoadingScreen
      label="loading poker table…"
      hint="First load can take a moment if the server has been idle."
    />;
  }

  const human = round?.players.find((p) => p.is_human);
  const showStartCTA = !round || round.state === "complete";
  const BETTING_STATES = new Set([
    "betting",     // draw + stud + (poker holdem after our refactor)
    "pre_flop", "flop", "turn", "river",  // legacy holdem state names
  ]);
  const isBettingTurn = !!(
    round
    && BETTING_STATES.has(round.state)
    && round.active_seat !== null
    && human
    && round.active_seat === human.seat_num
  );
  const isDiscardTurn = !!(
    round
    && round.family === "draw"
    && round.draw?.discard_pending
  );

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
        <Link to="/poker" className="text-white/60 text-sm">←</Link>
        <div className="text-center">
          <div className="text-xs text-white/50">{session.variant.name}</div>
          <div className="font-mono text-sm">
            ${session.config.small_blind}/${session.config.big_blind}
          </div>
        </div>
        <button onClick={endSession} className="text-xs text-white/40 underline">
          End
        </button>
      </div>

      {/* Felt table: AI seats around the rim, community cards in the middle. */}
      <TableSurface>
        <div className="flex flex-wrap gap-2 mb-3">
          {round?.players.filter((p) => !p.is_human).map((p) => (
            <SeatChip key={p.seat_num} player={p} dealerSeat={round?.dealer_seat ?? 0} />
          ))}
        </div>

        <div className="rounded-xl bg-black/20 p-3 ring-1 ring-white/10">
          <div className="text-xs uppercase tracking-wide text-white/60 mb-2 flex justify-between">
            <span>Board</span>
            <span>Pot ${round?.pot_total ?? 0}</span>
          </div>
          <div className="flex">
            {round?.community.map((tok, i) => (
              <div key={i} className="-ml-3 first:ml-0">
                <CardFace card={tokenToCard(tok)} />
              </div>
            ))}
            {(!round || round.community.length === 0) && (
              <div className="text-xs text-white/40 italic">no community cards yet</div>
            )}
          </div>
        </div>
      </TableSurface>

      {/* Human hole */}
      {round && human && (
        <div className="rounded-xl bg-white/10 p-3 ring-2 ring-white/40">
          <div className="text-xs uppercase tracking-wide text-white/60 mb-2 flex justify-between">
            <span>You · {human.name} · ${human.stack}</span>
            {human.committed_this_round > 0 && <span>bet ${human.committed_this_round}</span>}
          </div>
          <div className="flex">
            {round.human_hole.map((tok, i) => {
              const isMarkedDiscard = isDiscardTurn && discardSelected.has(i);
              return (
                <div
                  key={i}
                  className={`-ml-3 first:ml-0 transition-transform ${
                    isMarkedDiscard ? "translate-y-2 opacity-60" : ""
                  }`}
                  onClick={() => {
                    if (isDiscardTurn && round.draw) {
                      toggleDiscardIdx(i, round.draw.max_discard);
                    }
                  }}
                  style={{ cursor: isDiscardTurn ? "pointer" : "default" }}
                >
                  <CardFace card={tokenToCard(tok)} />
                </div>
              );
            })}
          </div>
          {isDiscardTurn && round?.draw && (
            <div className="text-xs text-amber-200/80 mt-2">
              Tap to mark up to {round.draw.max_discard} card
              {round.draw.max_discard === 1 ? "" : "s"} for discard
              ({discardSelected.size} selected). Confirm with the
              button below.
            </div>
          )}
        </div>
      )}

      {error && <div className="text-red-300 text-sm">{error}</div>}

      {/* Hand summary on completion */}
      {round?.state === "complete" && round.result && (
        <ResultPanel round={round} humanSeat={human?.seat_num ?? 0} />
      )}

      {/* Personality scoreboard between hands */}
      {round && showStartCTA && round.personality_stats?.length > 0 && (
        <PersonalityScoreboard stats={round.personality_stats} />
      )}

      {/* Action bar (human's betting turn) */}
      {round && isBettingTurn && (
        <ActionBar
          round={round}
          humanStack={human?.stack ?? 0}
          raiseAmount={raiseAmount}
          setRaiseAmount={setRaiseAmount}
          onAct={act}
          busy={busy}
        />
      )}

      {/* Discard confirm (draw poker, drawing phase) */}
      {round && isDiscardTurn && (
        <div
          className="fixed inset-x-0 bottom-0 px-3 pt-3 bg-felt-dark/95 backdrop-blur ring-1 ring-white/10"
          style={{ paddingBottom: "calc(env(safe-area-inset-bottom) + 12px)" }}
        >
          <div className="max-w-md mx-auto">
            <button
              onClick={confirmDiscard}
              disabled={busy}
              className="w-full min-h-touch rounded-xl bg-white text-felt-dark font-semibold disabled:opacity-50"
            >
              {busy
                ? "…"
                : discardSelected.size === 0
                ? "Stand pat"
                : `Discard ${discardSelected.size}`}
            </button>
          </div>
        </div>
      )}

      {/* Start CTA */}
      {showStartCTA && (
        <div
          className="fixed bottom-0 inset-x-0 px-4 pt-3 bg-felt-dark/95 backdrop-blur"
          style={{ paddingBottom: "calc(env(safe-area-inset-bottom) + 12px)" }}
        >
          <button
            onClick={startHand}
            disabled={busy}
            className="w-full max-w-md mx-auto block min-h-touch rounded-xl bg-white text-felt-dark font-semibold disabled:opacity-50"
          >
            {busy ? "Dealing…" : round?.state === "complete" ? "Next hand" : "Deal"}
          </button>
        </div>
      )}
    </div>
  );
}

function SeatChip({
  player,
  dealerSeat,
}: {
  player: import("../lib/poker").PlayerView;
  dealerSeat: number;
}) {
  const isActive = player.is_active;
  const isFolded = player.folded;
  const tag = isFolded ? "folded" : player.all_in ? "all-in" : "";
  return (
    <div
      className={`rounded-lg px-2 py-1 text-xs ring-1 ring-white/10 ${
        isActive ? "bg-white text-felt-dark" : "bg-felt-dark/60"
      } ${isFolded ? "opacity-40" : ""}`}
    >
      <div className="flex items-center gap-1">
        {dealerSeat === player.seat_num && <span title="dealer">⊙</span>}
        <span className="font-semibold">{player.name}</span>
      </div>
      <div className="font-mono">
        ${player.stack}
        {player.committed_this_round > 0 && (
          <span className="opacity-70"> · ${player.committed_this_round}</span>
        )}
      </div>
      {tag && <div className="opacity-60 italic">{tag}</div>}
      <div className="text-[10px] opacity-50">{player.personality?.replace(/_/g, " ")}</div>
      {/* Stud-only: render each visible card slot. null = face-down. */}
      {player.cards && player.cards.length > 0 && (
        <div className="flex gap-0.5 mt-1">
          {player.cards.map((tok, i) => (
            <div
              key={i}
              className={`w-5 h-7 rounded-sm flex items-center justify-center text-[8px] font-mono
                ${tok ? "bg-white text-black" : "bg-felt ring-1 ring-white/20 text-white/40"}`}
            >
              {tok ? formatStudToken(tok) : "??"}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function formatStudToken(tok: string): string {
  if (tok === "JK" || tok === "jk") return "JK";
  const rank = tok[0] === "T" ? "10" : tok[0];
  const suit = tok[1];
  const glyph =
    suit === "S" ? "♠" : suit === "H" ? "♥" : suit === "D" ? "♦" : "♣";
  return `${rank}${glyph}`;
}

function ActionBar({
  round,
  humanStack,
  raiseAmount,
  setRaiseAmount,
  onAct,
  busy,
}: {
  round: RoundView;
  humanStack: number;
  raiseAmount: number | null;
  setRaiseAmount: (n: number | null) => void;
  onAct: (action: string, amount?: number) => void;
  busy: boolean;
}) {
  const minRaise = round.current_bet + Math.max(round.current_bet, 10);
  const showSizing = round.legal_actions.includes("bet") || round.legal_actions.includes("raise");
  const sizingValue =
    raiseAmount ?? Math.min(round.pot_total > 0 ? Math.max(round.pot_total, minRaise) : minRaise, humanStack + round.to_call);

  return (
    <div
      className="fixed inset-x-0 bottom-0 px-3 pt-3 bg-felt-dark/95 backdrop-blur ring-1 ring-white/10"
      style={{ paddingBottom: "calc(env(safe-area-inset-bottom) + 12px)" }}
    >
      <div className="max-w-md mx-auto space-y-2">
        {showSizing && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => setRaiseAmount(Math.max(minRaise, (raiseAmount ?? sizingValue) - 10))}
              className="min-w-touch min-h-touch rounded-lg border border-white/20"
            >
              −
            </button>
            <div className="flex-1 text-center font-mono">${sizingValue}</div>
            <button
              onClick={() => setRaiseAmount(Math.min(humanStack + round.to_call, (raiseAmount ?? sizingValue) + 10))}
              className="min-w-touch min-h-touch rounded-lg border border-white/20"
            >
              +
            </button>
          </div>
        )}
        <div className="grid grid-cols-5 gap-1.5">
          {(["fold", "check", "call", "bet", "raise", "all_in"] as const).map((a) => {
            const allowed = round.legal_actions.includes(a);
            const label =
              a === "all_in" ? "All-in" :
              a === "call" && round.to_call > 0 ? `Call $${round.to_call}` :
              a.charAt(0).toUpperCase() + a.slice(1);
            return (
              <button
                key={a}
                onClick={() => onAct(a, a === "bet" || a === "raise" ? sizingValue : undefined)}
                disabled={!allowed || busy}
                className={`min-h-touch rounded-xl text-xs font-semibold col-span-${a === "call" ? 2 : 1}
                  ${allowed ? "bg-white text-felt-dark" : "bg-white/10 text-white/30"}`}
              >
                {label}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function ResultPanel({
  round,
  humanSeat,
}: {
  round: RoundView;
  humanSeat: number;
}) {
  if (!round.result) return null;
  const youWon = round.result.winner_seats.includes(humanSeat);
  const yourOutcome = round.result.outcomes.find((o) => o.seat_num === humanSeat);
  return (
    <div className="rounded-xl bg-felt-dark/80 p-3 ring-1 ring-white/10 space-y-2">
      <div className="text-center">
        <div
          className={`text-xl font-bold ${
            youWon ? "text-emerald-300" : (yourOutcome?.profit ?? 0) < 0 ? "text-red-300" : "text-white"
          }`}
        >
          {youWon ? "You won" : (yourOutcome?.profit ?? 0) < 0 ? "Lost" : "—"}
          {yourOutcome ? `  ${yourOutcome.profit >= 0 ? "+" : ""}$${yourOutcome.profit}` : ""}
        </div>
      </div>
      <div className="space-y-1 text-sm">
        {round.result.outcomes.map((o) => (
          <div key={o.seat_num} className="flex justify-between">
            <span>
              {o.seat_num === humanSeat ? "You" : `Seat ${o.seat_num}`}: {o.final_hand_name}
            </span>
            <span className="font-mono">
              {o.profit >= 0 ? "+" : ""}${o.profit}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function PersonalityScoreboard({ stats }: { stats: PersonalityAggregate[] }) {
  // Skip personalities that haven't played a hand yet (showed up after a
  // session reset or fresh start).
  const rows = stats.filter((p) => p.hands_played > 0);
  if (rows.length === 0) return null;
  return (
    <div className="rounded-xl bg-felt-dark/60 ring-1 ring-white/10 p-3 space-y-2">
      <div className="text-xs uppercase tracking-wide text-white/60">
        How everyone's doing
      </div>
      <div className="space-y-1">
        {rows.map((p) => {
          const winPct = p.hands_played
            ? Math.round((p.hands_won / p.hands_played) * 100)
            : 0;
          const profitColor =
            p.profit_total > 0 ? "text-emerald-300"
            : p.profit_total < 0 ? "text-red-300"
            : "text-white/60";
          return (
            <div
              key={p.personality}
              className="flex items-center justify-between text-sm"
            >
              <span className="capitalize">
                {p.personality.replace(/_/g, " ")}
                {p.seat_count > 1 && (
                  <span className="text-white/40 text-xs"> ×{p.seat_count}</span>
                )}
              </span>
              <span className="font-mono text-xs text-white/60">
                {winPct}% · {p.hands_won}/{p.hands_played}
              </span>
              <span className={`font-mono ${profitColor}`}>
                {p.profit_total >= 0 ? "+" : ""}${p.profit_total}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}


// ---- helpers --------------------------------------------------------

function tokenToCard(token: string) {
  if (token === "JK" || token === "jk") {
    return undefined;
  }
  return { rank: token[0] as any, suit: token[1] as any };
}
