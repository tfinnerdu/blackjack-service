import { useApp } from "../lib/store";
import type { BookView, RoundView, SessionView } from "../lib/types";

export function CoachPanel({
  round,
  session,
}: {
  round: RoundView;
  session: SessionView;
}) {
  const { showCoach, showCount, toggleCoach, toggleCount } = useApp();

  const trueCount = computeTrueCount(session);

  return (
    <div className="rounded-xl bg-felt-dark/60 p-3 ring-1 ring-white/10 space-y-2">
      <div className="grid grid-cols-2 gap-2 text-sm">
        <button
          onClick={toggleCoach}
          className={`min-h-touch rounded-lg ${
            showCoach ? "bg-white text-felt-dark" : "border border-white/20 text-white"
          }`}
        >
          {showCoach ? "Hide book" : "Show book"}
        </button>
        <button
          onClick={toggleCount}
          className={`min-h-touch rounded-lg ${
            showCount ? "bg-white text-felt-dark" : "border border-white/20 text-white"
          }`}
        >
          {showCount ? "Hide count" : "Show count"}
        </button>
      </div>

      {showCount && (
        <div className="grid grid-cols-3 gap-2 text-xs">
          <Stat label="Running" value={String(session.counter.running_count)} />
          <Stat label="True" value={trueCount.toFixed(2)} />
          <Stat
            label="Cards seen"
            value={`${session.counter.cards_seen}/${session.rules.decks * 52}`}
          />
        </div>
      )}

      {showCoach && round.book && round.state === "playing" && (
        <BookHint book={round.book} />
      )}
    </div>
  );
}

function BookHint({ book }: { book: BookView }) {
  const isDeviation = book.source === "index" && book.action !== book.basic_action;
  return (
    <div className="rounded-lg bg-white/10 p-2 text-sm">
      <div>
        Book says <strong className="font-semibold capitalize">{book.action}</strong>
        {isDeviation && (
          <span className="text-white/60">
            {" "}
            (basic = <span className="capitalize">{book.basic_action}</span>)
          </span>
        )}
      </div>
      {book.deviation && (
        <div className="text-xs text-white/60 mt-1">{book.deviation}</div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-white/5 p-2 text-center">
      <div className="text-white/50 uppercase text-[10px] tracking-wide">{label}</div>
      <div className="font-mono">{value}</div>
    </div>
  );
}

function computeTrueCount(session: SessionView): number {
  const cardsRemaining = session.rules.decks * 52 - session.counter.cards_seen;
  const decksRemaining = Math.max(0.5, cardsRemaining / 52);
  if (decksRemaining <= 0) return 0;
  return session.counter.running_count / decksRemaining;
}
