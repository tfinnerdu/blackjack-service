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
      <div className="w-full max-w-md text-center space-y-6">
        <h1 className="text-3xl font-bold tracking-tight">Blackjack Trainer</h1>
        <p className="text-white/70 text-sm">
          Real bankroll. Real session. The book is watching.
        </p>

        {loading ? (
          <div className="text-white/40">loading…</div>
        ) : hasSession ? (
          <div className="space-y-3">
            <button
              onClick={() => navigate("/play")}
              className="w-full min-h-touch rounded-xl bg-white text-felt-dark font-semibold"
            >
              Continue session
            </button>
            <Link
              to="/setup"
              className="block w-full min-h-touch flex items-center justify-center rounded-xl border border-white/20 text-white"
            >
              Start a new session
            </Link>
          </div>
        ) : (
          <Link
            to="/setup"
            className="block w-full min-h-touch flex items-center justify-center rounded-xl bg-white text-felt-dark font-semibold"
          >
            New session
          </Link>
        )}
      </div>
    </div>
  );
}
