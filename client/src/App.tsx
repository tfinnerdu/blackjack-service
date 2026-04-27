import { useEffect, useState } from "react";

type Health = {
  status: string;
  service: string;
  version: string;
  uptime_seconds: number;
};

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/health")
      .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
      .then(setHealth)
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <div
      className="min-h-screen flex flex-col items-center justify-center bg-felt-dark px-4"
      style={{
        paddingTop: "env(safe-area-inset-top)",
        paddingBottom: "env(safe-area-inset-bottom)",
      }}
    >
      <div className="w-full max-w-md text-center space-y-6">
        <h1 className="text-3xl font-bold tracking-tight">Blackjack Trainer</h1>
        <p className="text-white/70">
          Phase 1 scaffold. Game engine and table UI land in phase 2.
        </p>

        <div className="rounded-xl bg-felt p-4 text-left text-sm font-mono">
          <div className="text-white/60 mb-2">/health</div>
          {health && <pre className="whitespace-pre-wrap">{JSON.stringify(health, null, 2)}</pre>}
          {error && <div className="text-red-300">error: {error}</div>}
          {!health && !error && <div className="text-white/40">loading…</div>}
        </div>
      </div>
    </div>
  );
}
