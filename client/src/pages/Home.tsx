import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ApiError, Sessions } from "../lib/api";
import { useApp } from "../lib/store";

export default function Home() {
  const setSession = useApp((s) => s.setSession);
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [hasSession, setHasSession] = useState(false);

  useEffect(() => {
    Sessions.me()
      .then((sess) => {
        setSession(sess);
        setHasSession(true);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) {
          setHasSession(false);
        }
      })
      .finally(() => setLoading(false));
  }, [setSession]);

  return (
    <div
      className="min-h-screen flex flex-col items-center justify-center px-6"
      style={{
        paddingTop: "env(safe-area-inset-top)",
        paddingBottom: "env(safe-area-inset-bottom)",
      }}
    >
      <div className="w-full max-w-md text-center space-y-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Card Trainer</h1>
          <p className="text-white/70 text-sm mt-2">Pick a game.</p>
        </div>

        <div className="grid gap-3">
          <ModeCard
            title="Blackjack"
            blurb="Real-bankroll trainer. Book vs your plays. Counting helper."
            primary={
              hasSession ? (
                <button
                  onClick={() => navigate("/play")}
                  className="w-full min-h-touch rounded-xl bg-white text-felt-dark font-semibold"
                >
                  Continue session
                </button>
              ) : (
                <Link
                  to="/setup"
                  className="block w-full min-h-touch flex items-center justify-center rounded-xl bg-white text-felt-dark font-semibold"
                >
                  New session
                </Link>
              )
            }
            secondary={
              hasSession ? (
                <Link
                  to="/setup"
                  className="block w-full min-h-touch flex items-center justify-center rounded-xl border border-white/20 text-white"
                >
                  Start a new session
                </Link>
              ) : null
            }
          />

          <ModeCard
            title="Poker"
            blurb="Variant-aware helper + simulator. Hi/lo splits explained. Wild rule builder."
            primary={
              <Link
                to="/poker"
                className="block w-full min-h-touch flex items-center justify-center rounded-xl bg-white text-felt-dark font-semibold"
              >
                Open poker
              </Link>
            }
            secondary={
              <div className="text-xs text-white/40 text-center">
                Phase 1: foundations. Variant library + companion ship in phase 3.
              </div>
            }
          />
        </div>

        {loading && <div className="text-white/40 text-xs">checking session…</div>}
      </div>
    </div>
  );
}

function ModeCard({
  title,
  blurb,
  primary,
  secondary,
}: {
  title: string;
  blurb: string;
  primary: React.ReactNode;
  secondary: React.ReactNode;
}) {
  return (
    <div className="rounded-xl bg-felt p-4 text-left space-y-3">
      <div>
        <div className="text-lg font-semibold">{title}</div>
        <div className="text-xs text-white/60">{blurb}</div>
      </div>
      <div className="space-y-2">
        {primary}
        {secondary}
      </div>
    </div>
  );
}
