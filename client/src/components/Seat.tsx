import { HandRow } from "./Hand";
import type { SeatView } from "../lib/types";

export function SeatBlock({
  seat,
  isActive,
  activeHandIndex,
}: {
  seat: SeatView;
  isActive: boolean;
  activeHandIndex: number | null;
}) {
  const label = `Seat ${seat.seat_num}${seat.is_human ? " (you)" : ""}`;
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs uppercase tracking-wide text-white/60">{label}</span>
        {!seat.is_human && <span className="text-xs text-white/40">AI</span>}
      </div>
      <div className="space-y-2">
        {seat.hands.map((h, i) => (
          <HandRow
            key={i}
            hand={h}
            active={isActive && activeHandIndex === i && !h.finished}
            label={seat.hands.length > 1 ? `Hand ${i + 1}` : undefined}
          />
        ))}
      </div>
    </div>
  );
}
