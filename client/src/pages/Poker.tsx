import { useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../lib/api";

interface DeckPeekResponse {
  cards: string[];
  deck_size: number;
  cards_remaining: number;
}

export default function Poker() {
  const [decks, setDecks] = useState(1);
  const [jokers, setJokers] = useState(1);
  const [count, setCount] = useState(5);
  const [seed, setSeed] = useState<number | "">("");
  const [result, setResult] = useState<DeckPeekResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function peek() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/v1/poker/deck/peek", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          decks,
          jokers,
          count,
          seed: seed === "" ? undefined : Number(seed),
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new ApiError(res.status, data.code ?? "ERR", data.error ?? res.statusText);
      }
      setResult(data as DeckPeekResponse);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="min-h-screen px-4 py-6"
      style={{
        paddingTop: "calc(env(safe-area-inset-top) + 16px)",
        paddingBottom: "calc(env(safe-area-inset-bottom) + 16px)",
      }}
    >
      <div className="max-w-md mx-auto space-y-5">
        <Link to="/" className="text-white/60 text-sm">
          ← back
        </Link>

        <div>
          <h1 className="text-2xl font-bold">Poker</h1>
          <p className="text-white/60 text-sm mt-1">
            Phase 1 in place. Hand evaluator (phase 2), variant DSL (phase 3),
            companion (phase 5), simulator (phase 6) on the way.
          </p>
        </div>

        <div className="rounded-xl bg-felt p-4 space-y-3">
          <div className="text-xs uppercase tracking-wide text-white/60">
            Deck preview
          </div>
          <p className="text-xs text-white/50">
            Sanity check — the full variant DSL + companion ship later. For
            now, build a deck and peek the top cards.
          </p>

          <Field label="Decks">
            <Stepper value={decks} setValue={setDecks} min={1} max={4} />
          </Field>
          <Field label="Jokers (0/1/2)">
            <Stepper value={jokers} setValue={setJokers} min={0} max={2} />
          </Field>
          <Field label="Cards to peek">
            <Stepper value={count} setValue={setCount} min={1} max={20} />
          </Field>
          <Field label="Seed (optional)">
            <input
              type="number"
              value={seed}
              onChange={(e) => setSeed(e.target.value === "" ? "" : Number(e.target.value))}
              placeholder="random"
              className="w-full min-h-touch rounded-lg bg-felt-dark px-3 text-white"
            />
          </Field>

          <button
            onClick={peek}
            disabled={busy}
            className="w-full min-h-touch rounded-xl bg-white text-felt-dark font-semibold disabled:opacity-40"
          >
            {busy ? "Peeking…" : "Peek deck"}
          </button>

          {error && <div className="text-red-300 text-sm">{error}</div>}
          {result && (
            <div className="rounded-lg bg-felt-dark/60 p-3 text-sm">
              <div className="text-xs text-white/60 mb-1">
                Deck: {result.deck_size} cards · {result.cards_remaining} remaining
              </div>
              <div className="font-mono text-base">
                {result.cards.join(" ")}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <div className="text-xs text-white/60 mb-1">{label}</div>
      {children}
    </label>
  );
}

function Stepper({
  value,
  setValue,
  min,
  max,
}: {
  value: number;
  setValue: (n: number) => void;
  min: number;
  max: number;
}) {
  return (
    <div className="flex items-center gap-2">
      <button
        onClick={() => setValue(Math.max(min, value - 1))}
        className="min-w-touch min-h-touch rounded-lg border border-white/20 text-xl"
      >
        −
      </button>
      <div className="flex-1 text-center font-mono text-lg">{value}</div>
      <button
        onClick={() => setValue(Math.min(max, value + 1))}
        className="min-w-touch min-h-touch rounded-lg border border-white/20 text-xl"
      >
        +
      </button>
    </div>
  );
}
