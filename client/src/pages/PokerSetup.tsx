import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ApiError } from "../lib/api";
import { Poker, VariantSpec } from "../lib/poker";

const PERSONALITY_BLURBS: Record<string, string> = {
  book: "tight-aggressive baseline",
  tight: "scared, only premium hands",
  loose: "calls a lot, rarely raises",
  aggressive: "raises constantly",
  calling_station: "calls everything, never raises",
  bluffer: "bluffs the river ~25%",
  hot_cold: "presses when up, tightens when down",
  drunk: "30% mistake rate",
  mimic: "always check/call minimum",
};

interface BotSlot {
  name: string;
  personality: string;
}

export default function PokerSetup() {
  const navigate = useNavigate();
  const [variants, setVariants] = useState<VariantSpec[]>([]);
  const [variantName, setVariantName] = useState("Texas Hold'em");
  const [personalities, setPersonalities] = useState<string[]>([]);
  const [stack, setStack] = useState(1000);
  const [smallBlind, setSmallBlind] = useState(5);
  const [bigBlind, setBigBlind] = useState(10);
  const [humanName, setHumanName] = useState("Hero");
  const [bots, setBots] = useState<BotSlot[]>([
    { name: "Tight Tom", personality: "tight" },
    { name: "Maniac Mike", personality: "aggressive" },
    { name: "Calling Carl", personality: "calling_station" },
  ]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([Poker.variants(), Poker.personalities()])
      .then(([v, p]) => {
        // Only community-card variants are simulator-supported.
        const ok = v.variants.filter(
          (vv) => vv.deal.community_streets.length > 0
            && vv.deal.up_cards === 0
            && vv.deal.stud_streets.length === 0
            && vv.deal.draws.length === 0,
        );
        setVariants(ok);
        if (ok.length && !ok.find((x) => x.name === variantName)) {
          setVariantName(ok[0].name);
        }
        setPersonalities(p.personalities);
      })
      .catch((e) => setError(String(e)));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function setBot(i: number, partial: Partial<BotSlot>) {
    setBots((bs) => bs.map((b, idx) => (idx === i ? { ...b, ...partial } : b)));
  }

  function addBot() {
    setBots((bs) => [...bs, { name: `Bot ${bs.length + 2}`, personality: "book" }]);
  }

  function removeBot(i: number) {
    setBots((bs) => bs.filter((_, idx) => idx !== i));
  }

  async function start() {
    setBusy(true);
    setError(null);
    try {
      await Poker.createSession({
        variant: variantName,
        starting_stack: stack,
        small_blind: smallBlind,
        big_blind: bigBlind,
        bots,
        human_name: humanName,
      });
      navigate("/poker/sim/table");
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  }

  const selected = variants.find((v) => v.name === variantName);

  return (
    <div
      className="min-h-screen px-4 py-6"
      style={{
        paddingTop: "calc(env(safe-area-inset-top) + 16px)",
        paddingBottom: "calc(env(safe-area-inset-bottom) + 100px)",
      }}
    >
      <div className="max-w-md mx-auto space-y-5">
        <div className="flex items-center justify-between">
          <Link to="/poker" className="text-white/60 text-sm">
            ← back
          </Link>
          <div className="text-right text-xs text-white/40">poker simulator</div>
        </div>

        <h1 className="text-2xl font-bold">New simulator session</h1>

        <Field label="Variant">
          <select
            className="w-full min-h-touch rounded-xl bg-felt px-3 text-white"
            value={variantName}
            onChange={(e) => setVariantName(e.target.value)}
          >
            {variants.map((v) => (
              <option key={v.name} value={v.name}>{v.name}</option>
            ))}
          </select>
          {selected && (
            <p className="text-xs text-white/60 mt-2">{selected.description}</p>
          )}
        </Field>

        <div className="grid grid-cols-3 gap-2">
          <Field label="Stack">
            <Stepper value={stack} setValue={setStack} step={100} min={100} max={50000} />
          </Field>
          <Field label="SB">
            <Stepper value={smallBlind} setValue={setSmallBlind} step={1} min={1} max={500} />
          </Field>
          <Field label="BB">
            <Stepper value={bigBlind} setValue={setBigBlind} step={2} min={2} max={1000} />
          </Field>
        </div>

        <Field label="Your name">
          <input
            className="w-full min-h-touch rounded-xl bg-felt px-3 text-white"
            value={humanName}
            onChange={(e) => setHumanName(e.target.value)}
          />
        </Field>

        <div>
          <div className="text-xs uppercase tracking-wide text-white/60 mb-2">
            AI opponents ({bots.length})
          </div>
          <div className="space-y-2">
            {bots.map((b, i) => (
              <div key={i} className="rounded-xl bg-felt p-3 space-y-2">
                <div className="flex gap-2">
                  <input
                    value={b.name}
                    onChange={(e) => setBot(i, { name: e.target.value })}
                    className="flex-1 min-h-touch rounded-lg bg-felt-dark px-2 text-white"
                    placeholder="Name"
                  />
                  <button
                    onClick={() => removeBot(i)}
                    className="min-h-touch min-w-touch rounded-lg border border-white/20 text-white/60"
                  >
                    ×
                  </button>
                </div>
                <select
                  value={b.personality}
                  onChange={(e) => setBot(i, { personality: e.target.value })}
                  className="w-full min-h-touch rounded-lg bg-felt-dark px-2 text-white"
                >
                  {personalities.map((p) => (
                    <option key={p} value={p}>
                      {p.replace(/_/g, " ")}
                    </option>
                  ))}
                </select>
                <div className="text-xs text-white/50">
                  {PERSONALITY_BLURBS[b.personality] ?? ""}
                </div>
              </div>
            ))}
            <button
              onClick={addBot}
              className="w-full min-h-touch rounded-lg border border-white/20 text-white/70"
            >
              + Add opponent
            </button>
          </div>
        </div>

        {error && <div className="text-red-300 text-sm">{error}</div>}
      </div>

      <div
        className="fixed bottom-0 inset-x-0 px-4 pt-3 bg-felt-dark/95 backdrop-blur"
        style={{ paddingBottom: "calc(env(safe-area-inset-bottom) + 12px)" }}
      >
        <button
          onClick={start}
          disabled={busy || bots.length === 0}
          className="w-full max-w-md mx-auto block min-h-touch rounded-xl bg-white text-felt-dark font-semibold disabled:opacity-50"
        >
          {busy ? "Starting…" : "Take a seat"}
        </button>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <div className="text-xs text-white/60 mb-1 uppercase tracking-wide">{label}</div>
      {children}
    </label>
  );
}

function Stepper({
  value, setValue, step, min, max,
}: {
  value: number;
  setValue: (n: number) => void;
  step: number;
  min: number;
  max: number;
}) {
  return (
    <div className="flex items-center gap-1">
      <button
        onClick={() => setValue(Math.max(min, value - step))}
        className="min-w-touch min-h-touch rounded-lg border border-white/20"
      >
        −
      </button>
      <div className="flex-1 text-center font-mono">{value}</div>
      <button
        onClick={() => setValue(Math.min(max, value + step))}
        className="min-w-touch min-h-touch rounded-lg border border-white/20"
      >
        +
      </button>
    </div>
  );
}
