// Placeholder play page. The actual table view lands in the next commit.
import { Link } from "react-router-dom";

import { useApp } from "../lib/store";

export default function Play() {
  const session = useApp((s) => s.session);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-4 text-center space-y-4">
      <h1 className="text-2xl font-bold">Table</h1>
      <p className="text-white/60 text-sm">Bankroll: ${session?.bankroll ?? "—"}</p>
      <p className="text-white/40 text-sm max-w-xs">
        The table UI lands in the next commit. Backend is fully wired —
        you can already POST a round via /api/v1/sessions/me/rounds.
      </p>
      <Link to="/" className="underline text-white/70">
        back
      </Link>
    </div>
  );
}
