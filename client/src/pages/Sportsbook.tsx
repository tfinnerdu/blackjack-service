import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { LoadingScreen } from "../components/LoadingScreen";
import {
  ApiError,
  SportsAnalytics,
  SportsEvent,
  SportsSlip,
  Sportsbook as SportsbookApi,
  SportsbookSessionView,
} from "../lib/api";

type Tab = "events" | "slips" | "analytics";

interface SlipBuilderLeg {
  market_id: number;
  selection_key: string;
  selection_label: string;
  event_label: string;
  market_type: string;
  odds: number;
  line: number | null;
}

function americanString(odds: number): string {
  return odds > 0 ? `+${odds}` : `${odds}`;
}

export default function Sportsbook() {
  const [session, setSession] = useState<SportsbookSessionView | null>(null);
  const [events, setEvents] = useState<SportsEvent[]>([]);
  const [slips, setSlips] = useState<SportsSlip[]>([]);
  const [analytics, setAnalytics] = useState<SportsAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("events");
  const [slipLegs, setSlipLegs] = useState<SlipBuilderLeg[]>([]);
  const [stake, setStake] = useState(25);
  const [filter, setFilter] = useState<string>("all");

  useEffect(() => {
    SportsbookApi.me()
      .then((s) => {
        setSession(s);
        return Promise.all([
          SportsbookApi.events(),
          SportsbookApi.slips(),
          SportsbookApi.analytics(),
        ]);
      })
      .then(([ev, sl, an]) => {
        setEvents(ev.events);
        setSlips(sl.slips);
        setAnalytics(an);
      })
      .catch((e) => {
        if (!(e instanceof ApiError && e.status === 404)) setError(String(e));
      })
      .finally(() => setLoading(false));
  }, []);

  async function startSession() {
    setBusy(true);
    setError(null);
    try {
      const sess = await SportsbookApi.create({ starting_bankroll: 1000 });
      const [ev, sl, an] = await Promise.all([
        SportsbookApi.events(),
        SportsbookApi.slips(),
        SportsbookApi.analytics(),
      ]);
      setSession(sess);
      setEvents(ev.events);
      setSlips(sl.slips);
      setAnalytics(an);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function refresh() {
    try {
      const [me, ev, sl, an] = await Promise.all([
        SportsbookApi.me(),
        SportsbookApi.events(),
        SportsbookApi.slips(),
        SportsbookApi.analytics(),
      ]);
      setSession(me);
      setEvents(ev.events);
      setSlips(sl.slips);
      setAnalytics(an);
    } catch { /* ignore network blips */ }
  }

  function toggleLeg(leg: SlipBuilderLeg) {
    setSlipLegs((cur) => {
      const existingIdx = cur.findIndex(
        (l) => l.market_id === leg.market_id,
      );
      if (existingIdx >= 0) {
        // Same market: replace selection if different, remove if same.
        if (cur[existingIdx].selection_key === leg.selection_key) {
          return cur.filter((_, i) => i !== existingIdx);
        }
        const next = [...cur];
        next[existingIdx] = leg;
        return next;
      }
      return [...cur, leg];
    });
  }

  async function placeSlip() {
    if (!session || slipLegs.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      await SportsbookApi.placeSlip(
        slipLegs.map((l) => ({
          market_id: l.market_id,
          selection_key: l.selection_key,
        })),
        stake,
      );
      setSlipLegs([]);
      await refresh();
      setTab("slips");
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function advanceDay() {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      await SportsbookApi.advance();
      await refresh();
      setTab("slips");
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function endSession() {
    if (!confirm("End this sportsbook session? Bankroll resets.")) return;
    await SportsbookApi.destroy().catch(() => {});
    setSession(null);
    setEvents([]);
    setSlips([]);
    setAnalytics(null);
  }

  const sports = useMemo(() => {
    const set = new Set(events.map((e) => e.sport));
    return ["all", ...Array.from(set).sort()];
  }, [events]);

  const filteredEvents = useMemo(
    () => filter === "all" ? events : events.filter((e) => e.sport === filter),
    [events, filter],
  );

  // Combined decimal odds preview for the slip builder.
  const previewPayout = useMemo(() => {
    if (slipLegs.length === 0 || stake <= 0) return 0;
    const decimals = slipLegs.map((l) => {
      const o = l.odds;
      return o > 0 ? 1 + o / 100 : 1 + 100 / Math.abs(o);
    });
    const product = decimals.reduce((a, b) => a * b, 1);
    return Math.round(stake * product);
  }, [slipLegs, stake]);

  if (loading) {
    return <LoadingScreen
      label="loading sportsbook…"
      hint="First load can take a moment if the server has been idle."
    />;
  }

  if (!session) {
    return (
      <div className="min-h-screen px-4 py-6 max-w-md mx-auto space-y-4"
           style={{ paddingTop: "calc(env(safe-area-inset-top) + 16px)" }}>
        <Link to="/" className="text-white/60 text-sm">← home</Link>
        <h1 className="text-2xl font-bold">Sports betting simulator</h1>
        <p className="text-sm text-white/70">
          Paper-trade single bets and parlays against a daily slate of NBA / NFL /
          MLB / NHL games. Hit "advance day" to fast-forward through the
          schedule, settle your slips, and see how a strategy actually
          performed. Bankroll starts at $1,000.
        </p>
        <button
          onClick={startSession}
          disabled={busy}
          className="w-full min-h-touch rounded-xl bg-white text-felt-dark font-semibold disabled:opacity-50"
        >
          Open the book
        </button>
        {error && <div className="text-red-300 text-sm">{error}</div>}
      </div>
    );
  }

  return (
    <div className="min-h-screen px-3 py-3 flex flex-col gap-3"
         style={{
           paddingTop: "calc(env(safe-area-inset-top) + 12px)",
           paddingBottom: "calc(env(safe-area-inset-bottom) + 16px)",
         }}>
      <div className="flex items-center justify-between">
        <Link to="/" className="text-white/60 text-sm">←</Link>
        <div className="text-center">
          <div className="text-xs text-white/50">Bankroll · day {session.current_day}</div>
          <div className="font-mono text-xl">${session.bankroll}</div>
          {session.analytics_summary && (
            <div className={`text-[11px] ${
              session.analytics_summary.net_profit >= 0
                ? "text-emerald-300" : "text-red-300"
            }`}>
              {session.analytics_summary.net_profit >= 0 ? "+" : ""}${session.analytics_summary.net_profit}
              {" · "}{session.analytics_summary.win_rate_pct}% win
              {" · "}{session.analytics_summary.roi_pct}% ROI
            </div>
          )}
        </div>
        <button onClick={endSession} className="text-white/60 text-xs underline">end</button>
      </div>

      <div className="flex gap-1 rounded-xl bg-felt p-1">
        {(["events", "slips", "analytics"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex-1 min-h-[36px] rounded-lg text-sm capitalize ${
              tab === t ? "bg-white text-felt-dark" : "text-white/70"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {error && <div className="text-red-300 text-sm">{error}</div>}

      {tab === "events" && (
        <>
          {sports.length > 2 && (
            <div className="flex gap-1 overflow-x-auto">
              {sports.map((s) => (
                <button
                  key={s}
                  onClick={() => setFilter(s)}
                  className={`px-3 py-1 rounded-full text-xs capitalize whitespace-nowrap ${
                    filter === s ? "bg-white text-felt-dark" : "border border-white/20"
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
          )}

          {filteredEvents.map((ev) => (
            <EventCard
              key={ev.id}
              event={ev}
              currentDay={session.current_day}
              slipLegs={slipLegs}
              onToggleLeg={toggleLeg}
            />
          ))}

          {filteredEvents.length === 0 && (
            <div className="text-center text-sm text-white/50 py-6">
              No open events. Hit "advance day" to roll forward.
            </div>
          )}

          <div className="mt-auto sticky bottom-0 space-y-2">
            {slipLegs.length > 0 && (
              <SlipBuilder
                legs={slipLegs}
                stake={stake}
                setStake={setStake}
                previewPayout={previewPayout}
                bankroll={session.bankroll}
                onPlace={placeSlip}
                onClear={() => setSlipLegs([])}
                busy={busy}
              />
            )}
            <button
              onClick={advanceDay}
              disabled={busy}
              className="w-full min-h-touch rounded-xl border border-white/20 text-sm disabled:opacity-50"
            >
              {busy ? "Advancing…" : `Advance to day ${session.current_day + 1}`}
            </button>
          </div>
        </>
      )}

      {tab === "slips" && <SlipsTab slips={slips} />}

      {tab === "analytics" && analytics && <AnalyticsTab analytics={analytics} />}
    </div>
  );
}

function EventCard({
  event,
  currentDay,
  slipLegs,
  onToggleLeg,
}: {
  event: SportsEvent;
  currentDay: number;
  slipLegs: SlipBuilderLeg[];
  onToggleLeg: (leg: SlipBuilderLeg) => void;
}) {
  const eventLabel = `${event.away_team} @ ${event.home_team}`;
  return (
    <div className="rounded-xl bg-felt p-3 space-y-2">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold">{eventLabel}</div>
          <div className="text-[11px] text-white/50 uppercase">
            {event.sport} · {event.league}
          </div>
        </div>
        <div className="text-[11px] text-white/40">
          {event.day === currentDay ? "today" : `day ${event.day}`}
        </div>
      </div>
      {event.markets.map((m) => (
        <div key={m.id}>
          <div className="text-[11px] uppercase tracking-wide text-white/50 mb-1">
            {m.market_type}
          </div>
          <div className="grid grid-cols-2 gap-1">
            {m.selections.map((s) => {
              const selected = slipLegs.some(
                (l) => l.market_id === m.id && l.selection_key === s.key,
              );
              const lineStr = s.line != null
                ? (s.line > 0 ? `+${s.line}` : `${s.line}`)
                : null;
              return (
                <button
                  key={s.key}
                  onClick={() => onToggleLeg({
                    market_id: m.id,
                    selection_key: s.key,
                    selection_label: s.label,
                    event_label: eventLabel,
                    market_type: m.market_type,
                    odds: s.odds,
                    line: s.line,
                  })}
                  className={`min-h-touch rounded-lg px-2 py-1 text-left text-sm border ${
                    selected
                      ? "bg-white text-felt-dark border-white"
                      : "border-white/15 hover:border-white/40"
                  }`}
                >
                  <div className="text-xs">
                    {s.label}{lineStr ? ` ${lineStr}` : ""}
                  </div>
                  <div className="font-mono text-sm">{americanString(s.odds)}</div>
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

function SlipBuilder({
  legs,
  stake,
  setStake,
  previewPayout,
  bankroll,
  onPlace,
  onClear,
  busy,
}: {
  legs: SlipBuilderLeg[];
  stake: number;
  setStake: (n: number) => void;
  previewPayout: number;
  bankroll: number;
  onPlace: () => void;
  onClear: () => void;
  busy: boolean;
}) {
  const slipType = legs.length === 1 ? "Single" : "Parlay";
  return (
    <div className="rounded-xl bg-felt-dark/95 backdrop-blur ring-1 ring-white/15 p-3 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs uppercase tracking-wide text-white/60">
          {slipType} · {legs.length} leg{legs.length === 1 ? "" : "s"}
        </span>
        <button onClick={onClear} className="text-xs text-white/50 underline">
          clear
        </button>
      </div>
      <div className="space-y-1 max-h-[110px] overflow-y-auto">
        {legs.map((l, i) => (
          <div key={i} className="text-xs flex justify-between">
            <span>
              {l.selection_label}
              {l.line != null && ` ${l.line > 0 ? "+" : ""}${l.line}`}
              <span className="text-white/40 ml-1">· {l.event_label}</span>
            </span>
            <span className="font-mono">{americanString(l.odds)}</span>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={() => setStake(Math.max(1, stake - 5))}
          className="min-w-[40px] min-h-touch rounded-lg border border-white/20 text-xl"
        >−</button>
        <div className="flex-1 text-center">
          <div className="text-[11px] text-white/50">stake</div>
          <div className="font-mono">${stake}</div>
        </div>
        <button
          onClick={() => setStake(Math.min(bankroll, stake + 5))}
          className="min-w-[40px] min-h-touch rounded-lg border border-white/20 text-xl"
        >+</button>
      </div>
      <div className="text-xs text-white/70 flex justify-between">
        <span>To win</span>
        <span className="font-mono text-white">${previewPayout - stake}</span>
      </div>
      <button
        onClick={onPlace}
        disabled={busy || stake <= 0 || stake > bankroll}
        className="w-full min-h-touch rounded-xl bg-white text-felt-dark font-semibold disabled:opacity-40"
      >
        {busy ? "Placing…" : `Place ${slipType.toLowerCase()} · $${stake}`}
      </button>
    </div>
  );
}

function SlipsTab({ slips }: { slips: SportsSlip[] }) {
  if (slips.length === 0) {
    return (
      <div className="text-center text-sm text-white/50 py-6">
        No slips yet. Place a bet on the events tab.
      </div>
    );
  }
  return (
    <div className="space-y-2">
      {slips.map((s) => (
        <SlipCard key={s.id} slip={s} />
      ))}
    </div>
  );
}

function SlipCard({ slip }: { slip: SportsSlip }) {
  const statusColor =
    slip.status === "won" ? "text-emerald-300"
    : slip.status === "lost" ? "text-red-300"
    : slip.status === "pending" ? "text-amber-300"
    : "text-white/60";
  return (
    <div className="rounded-xl bg-felt p-3 space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-xs uppercase tracking-wide text-white/60">
          {slip.slip_type} · {slip.legs.length} leg{slip.legs.length === 1 ? "" : "s"}
        </span>
        <span className={`text-xs uppercase ${statusColor}`}>{slip.status}</span>
      </div>
      {(slip.leg_results ?? slip.legs).map((l, i) => (
        <div key={i} className="text-xs flex justify-between">
          <span>
            <LegStatusDot outcome={l.outcome ?? null} />
            {l.label ?? l.selection_key}
            {l.line != null && ` ${l.line > 0 ? "+" : ""}${l.line}`}
            <span className="text-white/40 ml-1">· {l.event_label}</span>
          </span>
          <span className="font-mono">{americanString(l.odds)}</span>
        </div>
      ))}
      <div className="flex justify-between text-xs pt-1">
        <span>Stake ${slip.stake}</span>
        <span>
          {slip.status === "won" || slip.status === "push" ? (
            <span className="font-mono">+${slip.payout_actual - slip.stake}</span>
          ) : slip.status === "lost" ? (
            <span className="font-mono text-red-300">-${slip.stake}</span>
          ) : (
            <span className="font-mono text-white/60">to win ${slip.potential_payout - slip.stake}</span>
          )}
        </span>
      </div>
    </div>
  );
}

function LegStatusDot({ outcome }: { outcome: string | null }) {
  if (outcome == null) return null;
  const map: Record<string, string> = {
    won: "text-emerald-300",
    lost: "text-red-300",
    push: "text-sky-300",
    void: "text-white/40",
  };
  return <span className={`mr-1 ${map[outcome] ?? "text-white/40"}`}>●</span>;
}

function AnalyticsTab({ analytics }: { analytics: SportsAnalytics }) {
  const s = analytics.summary;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <Stat label="Net" value={`${s.net_profit >= 0 ? "+" : ""}$${s.net_profit}`} />
        <Stat label="ROI" value={`${s.roi_pct}%`} />
        <Stat label="Win rate" value={`${s.win_rate_pct}%`}
              sub={`${s.wins}W / ${s.losses}L / ${s.pushes}P`} />
        <Stat label="Slips" value={String(s.slips_placed)}
              sub={`${s.settled_count} settled`} />
        <Stat label="Staked" value={`$${s.total_staked}`} />
        <Stat label="Returned" value={`$${s.total_returned}`} />
      </div>

      {analytics.streak.count > 0 && (
        <div className="rounded-xl bg-felt p-3 text-center text-sm">
          {analytics.streak.sign > 0 ? (
            <span className="text-emerald-300">
              🔥 {analytics.streak.count}-slip win streak
            </span>
          ) : (
            <span className="text-red-300">
              ❄️ {analytics.streak.count}-slip cold streak
            </span>
          )}
        </div>
      )}

      {Object.keys(analytics.by_market_type).length > 0 && (
        <div className="rounded-xl bg-felt p-3 space-y-2">
          <div className="text-xs uppercase tracking-wide text-white/60">
            By market type (single bets)
          </div>
          {Object.entries(analytics.by_market_type).map(([mtype, b]) => {
            const total = b.won + b.lost;
            const rate = total ? Math.round((b.won / total) * 100) : 0;
            return (
              <div key={mtype} className="text-sm flex justify-between">
                <span className="capitalize">{mtype}</span>
                <span className="font-mono text-white/80">
                  {rate}% · {b.won}W / {b.lost}L
                  {b.push > 0 && ` / ${b.push}P`}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {Object.keys(analytics.by_slip_type).length > 0 && (
        <div className="rounded-xl bg-felt p-3 space-y-2">
          <div className="text-xs uppercase tracking-wide text-white/60">
            Single vs parlay
          </div>
          {Object.entries(analytics.by_slip_type).map(([k, b]) => {
            const net = b.returned - b.staked;
            return (
              <div key={k} className="text-sm flex justify-between">
                <span className="capitalize">{k}</span>
                <span className="font-mono">
                  {b.won}W / {b.lost}L ·
                  {" "}<span className={net >= 0 ? "text-emerald-300" : "text-red-300"}>
                    {net >= 0 ? "+" : ""}${net}
                  </span>
                </span>
              </div>
            );
          })}
        </div>
      )}

      {analytics.surprising_losses.length > 0 && (
        <div className="rounded-xl bg-felt p-3 space-y-1">
          <div className="text-xs uppercase tracking-wide text-white/60">
            Surprising losses (+200 or longer)
          </div>
          <p className="text-[11px] text-white/50 mb-1">
            Underdog legs you backed that didn't hit. Worth reviewing for trends.
          </p>
          {analytics.surprising_losses.map((l, i) => (
            <div key={i} className="text-xs flex justify-between">
              <span>
                {l.leg_label} <span className="text-white/40">· {l.event_label}</span>
              </span>
              <span className="font-mono">{americanString(l.odds)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl bg-felt p-3">
      <div className="text-xs uppercase tracking-wide text-white/60">{label}</div>
      <div className="text-xl font-mono">{value}</div>
      {sub && <div className="text-[11px] text-white/50">{sub}</div>}
    </div>
  );
}
