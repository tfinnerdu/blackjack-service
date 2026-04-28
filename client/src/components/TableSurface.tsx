// A felt-styled wrapper to give the blackjack / poker table that
// casino feel without rewriting the layout. Renders a green-felt
// gradient with a subtle radial highlight at the top + a warm
// wood-tone rail around the edge.

import type { ReactNode } from "react";

export function TableSurface({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-3xl p-2 ring-2 ring-amber-800/60 shadow-inner ${className}`}
      style={{
        // Outer rail: subtle leather/wood tone.
        background:
          "linear-gradient(180deg, #4a2912 0%, #3a2010 60%, #2a160a 100%)",
        boxShadow:
          "0 1px 0 rgba(255,255,255,0.05) inset, 0 6px 14px rgba(0,0,0,0.4)",
      }}
    >
      <div
        className="rounded-2xl p-3"
        style={{
          // Felt: radial vignette so the center reads brighter,
          // edges darker — like a real table under spotlights.
          background:
            "radial-gradient(ellipse at 50% 30%, #157349 0%, #0d5132 45%, #073a23 100%)",
          boxShadow: "0 0 20px rgba(0,0,0,0.45) inset",
        }}
      >
        {children}
      </div>
    </div>
  );
}
