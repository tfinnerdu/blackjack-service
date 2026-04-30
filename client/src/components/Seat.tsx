import { HandRow } from "./Hand";
import type { SeatView } from "../lib/types";

export type SeatKind = "host" | "guest" | "ai";

export function SeatBlock({
  seat,
  isActive,
  activeHandIndex,
  kind,
  isYou,
  hideBlackjackStatus,
}: {
  seat: SeatView;
  isActive: boolean;
  activeHandIndex: number | null;
  kind?: SeatKind;
  isYou?: boolean;
  hideBlackjackStatus?: boolean;
}) {
  // Fallback: derive a kind from is_human alone (legacy single-player path).
  const resolvedKind: SeatKind =
    kind ?? (seat.is_human ? "host" : "ai");
  const label = `Seat ${seat.seat_num}`;
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs uppercase tracking-wide text-white/60 flex items-center gap-2">
          <SeatPresenceDot kind={resolvedKind} />
          {label}
          {isYou && <span className="text-emerald-300 normal-case">you</span>}
        </span>
        <span className="text-xs text-white/40">
          {resolvedKind === "host"
            ? "Host"
            : resolvedKind === "guest"
              ? "Player"
              : "Bot"}
        </span>
      </div>
      <div className="space-y-2">
        {seat.hands.map((h, i) => (
          <HandRow
            key={i}
            hand={h}
            active={isActive && activeHandIndex === i && !h.finished}
            label={seat.hands.length > 1 ? `Hand ${i + 1}` : undefined}
            hideBlackjackStatus={hideBlackjackStatus}
          />
        ))}
      </div>
    </div>
  );
}

export function SeatPresenceDot({ kind }: { kind: SeatKind }) {
  const color =
    kind === "host"
      ? "bg-amber-300"
      : kind === "guest"
        ? "bg-emerald-400"
        : "bg-white/30";
  // The host + guest dots get a soft halo to read as 'online'; the AI
  // dot is hollow-feeling so the table layout still parses at a glance.
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full ${color} ${
        kind === "ai" ? "" : "ring-2 ring-white/10"
      }`}
      aria-hidden
    />
  );
}
