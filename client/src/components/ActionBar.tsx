import { useState } from "react";

import { ApiError, Rounds } from "../lib/api";
import { useApp } from "../lib/store";
import type { ActionVerb, RoundView } from "../lib/types";

interface ButtonSpec {
  action: ActionVerb;
  label: string;
  short: string;
}

const ALL_BUTTONS: ButtonSpec[] = [
  { action: "hit", label: "Hit", short: "Hit" },
  { action: "stand", label: "Stand", short: "Stand" },
  { action: "double", label: "Double", short: "DBL" },
  { action: "split", label: "Split", short: "Split" },
  { action: "surrender", label: "Surrender", short: "Surr" },
];

export function ActionBar({ round }: { round: RoundView }) {
  const setRound = useApp((s) => s.setRound);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (round.state === "insurance") {
    return <InsuranceBar setBusy={setBusy} setError={setError} busy={busy} error={error} />;
  }
  if (round.state !== "playing") return null;

  async function act(action: ActionVerb) {
    setBusy(true);
    setError(null);
    try {
      const r = await Rounds.act(action);
      setRound(r);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-x-0 bottom-0 px-3 pt-3 bg-felt-dark/95 backdrop-blur ring-1 ring-white/10"
      style={{ paddingBottom: "calc(env(safe-area-inset-bottom) + 12px)" }}
    >
      {error && <div className="text-red-300 text-xs text-center mb-2">{error}</div>}
      <div className="grid grid-cols-5 gap-2 max-w-md mx-auto">
        {ALL_BUTTONS.map((b) => {
          const allowed = round.legal_actions.includes(b.action);
          return (
            <button
              key={b.action}
              onClick={() => act(b.action)}
              disabled={!allowed || busy}
              className={`min-h-touch rounded-xl text-sm font-semibold transition-colors
                ${
                  allowed
                    ? "bg-white text-felt-dark active:bg-white/80"
                    : "bg-white/10 text-white/30"
                }`}
            >
              {b.short}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function InsuranceBar({
  busy,
  error,
  setBusy,
  setError,
}: {
  busy: boolean;
  error: string | null;
  setBusy: (b: boolean) => void;
  setError: (s: string | null) => void;
}) {
  const setRound = useApp((s) => s.setRound);

  async function decide(accept: boolean) {
    setBusy(true);
    setError(null);
    try {
      const r = await Rounds.insurance(accept);
      setRound(r);
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-x-0 bottom-0 px-3 pt-3 bg-felt-dark/95 backdrop-blur ring-1 ring-white/10"
      style={{ paddingBottom: "calc(env(safe-area-inset-bottom) + 12px)" }}
    >
      <div className="text-center text-xs text-white/70 mb-2">
        Dealer shows an Ace. Insurance?
      </div>
      {error && <div className="text-red-300 text-xs text-center mb-2">{error}</div>}
      <div className="grid grid-cols-2 gap-2 max-w-md mx-auto">
        <button
          onClick={() => decide(false)}
          disabled={busy}
          className="min-h-touch rounded-xl bg-white/10 text-white font-semibold"
        >
          No
        </button>
        <button
          onClick={() => decide(true)}
          disabled={busy}
          className="min-h-touch rounded-xl bg-white text-felt-dark font-semibold"
        >
          Yes
        </button>
      </div>
    </div>
  );
}
