import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import {
  ApiError,
  BankrollHistoryEntry,
  SessionStatsView,
  Sessions,
} from "../lib/api";
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

        {stats && stats.bankrolls && (
          <BankrollComparison
            bankrolls={stats.bankrolls}
            history={stats.bankroll_history}
          />
        )}

        {session.room_code && <RoomCodeCard code={session.room_code} />}

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

function RoomCodeCard({ code }: { code: string }) {
  const url = `${window.location.origin}/join/${code}`;
  const [copied, setCopied] = useState<string | null>(null);

  function copy(value: string, label: string) {
    void navigator.clipboard?.writeText(value);
    setCopied(label);
    window.setTimeout(() => setCopied(null), 1500);
  }

  return (
    <div className="rounded-xl bg-felt p-3 space-y-2">
      <div className="text-xs uppercase tracking-wide text-white/60">
        Invite a friend
      </div>
      <div className="flex items-center gap-3">
        <div className="font-mono text-2xl tracking-widest flex-1 text-center bg-felt-dark rounded-lg py-2">
          {code}
        </div>
        <button
          onClick={() => copy(code, "code")}
          className="min-h-touch px-3 rounded-lg border border-white/20 text-xs"
        >
          {copied === "code" ? "Copied!" : "Copy code"}
        </button>
      </div>
      <div className="flex items-center gap-2">
        <input
          readOnly
          value={url}
          className="flex-1 rounded-lg bg-felt-dark text-white/80 text-xs px-2 py-2 font-mono"
        />
        <button
          onClick={() => copy(url, "link")}
          className="min-h-touch px-3 rounded-lg border border-white/20 text-xs"
        >
          {copied === "link" ? "Copied!" : "Copy link"}
        </button>
      </div>
      <p className="text-[11px] text-white/50">
        Share the link or have someone open <span className="font-mono">/join</span> and enter the code.
        They can take over any of the bot seats.
      </p>
    </div>
  );
}

function BankrollComparison({
  bankrolls,
  history,
}: {
  bankrolls: SessionStatsView["bankrolls"];
  history: BankrollHistoryEntry[];
}) {
  const actualDelta = bankrolls.actual - bankrolls.starting;
  const bookDelta = bankrolls.book - bankrolls.starting;
  const counterDelta = bankrolls.counter - bankrolls.starting;
  return (
    <div className="rounded-xl bg-felt p-3 space-y-3">
      <div className="text-xs uppercase tracking-wide text-white/60">
        How would I be doing if…
      </div>
      <div className="grid grid-cols-3 gap-2 text-center">
        <BankrollLine
          label="You"
          value={bankrolls.actual}
          delta={actualDelta}
          color="text-amber-300"
        />
        <BankrollLine
          label="Book"
          value={bankrolls.book}
          delta={bookDelta}
          color="text-emerald-300"
        />
        <BankrollLine
          label="Counter"
          value={bankrolls.counter}
          delta={counterDelta}
          color="text-sky-300"
        />
      </div>
      <BankrollSparkline history={history} starting={bankrolls.starting} />
      <div className="text-[11px] text-white/50 leading-relaxed">
        Each line replays the same shoe state. <span className="text-emerald-300">Book</span> is
        you playing perfect basic strategy. <span className="text-sky-300">Counter</span> adds
        Hi-Lo / Illustrious 18 deviations and a count-spread bet sizing on top.
      </div>
    </div>
  );
}

function BankrollLine({
  label,
  value,
  delta,
  color,
}: {
  label: string;
  value: number;
  delta: number;
  color: string;
}) {
  const sign = delta > 0 ? "+" : delta < 0 ? "" : "";
  return (
    <div>
      <div className={`text-xs ${color}`}>{label}</div>
      <div className="font-mono text-lg">${value}</div>
      <div className="text-[11px] text-white/50">
        {sign}
        {delta}
      </div>
    </div>
  );
}

function BankrollSparkline({
  history,
  starting,
}: {
  history: BankrollHistoryEntry[];
  starting: number;
}) {
  if (history.length < 2) {
    return (
      <div className="h-24 flex items-center justify-center text-xs text-white/40">
        Play a few hands to see the comparison line.
      </div>
    );
  }
  const w = 320;
  const h = 96;
  const pad = 6;
  const xs = history.map((_, i) => i);
  const ys = history.flatMap((p) => [p.actual, p.book, p.counter]);
  ys.push(starting); // anchor the y-axis around the buy-in
  const yMin = Math.min(...ys);
  const yMax = Math.max(...ys);
  const yRange = Math.max(1, yMax - yMin);

  const xStep = (w - pad * 2) / Math.max(1, xs.length - 1);
  const yScale = (v: number) =>
    h - pad - ((v - yMin) / yRange) * (h - pad * 2);
  const xScale = (i: number) => pad + i * xStep;

  function path(values: number[]): string {
    return values
      .map((v, i) => `${i === 0 ? "M" : "L"} ${xScale(i)} ${yScale(v)}`)
      .join(" ");
  }

  const startingY = yScale(starting);

  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      className="w-full h-24"
      role="img"
      aria-label="bankroll comparison over hands played"
    >
      <line
        x1={pad}
        x2={w - pad}
        y1={startingY}
        y2={startingY}
        stroke="rgba(255,255,255,0.18)"
        strokeDasharray="2 3"
      />
      <path
        d={path(history.map((p) => p.actual))}
        fill="none"
        stroke="#fcd34d"
        strokeWidth={1.6}
      />
      <path
        d={path(history.map((p) => p.book))}
        fill="none"
        stroke="#6ee7b7"
        strokeWidth={1.6}
      />
      <path
        d={path(history.map((p) => p.counter))}
        fill="none"
        stroke="#7dd3fc"
        strokeWidth={1.6}
      />
    </svg>
  );
}
