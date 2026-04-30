import { CardSpread } from "./Card";
import type { HandView } from "../lib/types";

export function HandRow({
  hand,
  active,
  label,
  hideBlackjackStatus,
}: {
  hand: HandView;
  active?: boolean;
  label?: string;
  // Suppress the "Blackjack!" label until the insurance decision is in.
  // Calling it out before the player decides leaks information they're
  // supposed to weigh themselves (even-money / take-insurance is the
  // canonical decision when you have a natural).
  hideBlackjackStatus?: boolean;
}) {
  const totalLabel = hand.soft && hand.total <= 21 ? `Soft ${hand.total}` : String(hand.total);
  const status = hand.bust
    ? "Bust"
    : hand.blackjack && !hideBlackjackStatus
    ? "Blackjack!"
    : hand.surrendered
    ? "Surrendered"
    : hand.doubled
    ? "Doubled"
    : hand.stood
    ? "Stood"
    : "";

  return (
    <div
      className={`rounded-xl p-3 transition-colors ${
        active ? "bg-white/10 ring-2 ring-white/60" : "bg-felt-dark/40"
      }`}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          {label && <span className="text-xs text-white/60">{label}</span>}
          <span className="text-lg font-mono font-semibold">{totalLabel}</span>
          {status && (
            <span className="text-xs uppercase tracking-wide text-white/70">{status}</span>
          )}
        </div>
        <div className="text-xs text-white/50">${hand.bet}</div>
      </div>
      <CardSpread cards={hand.cards} />
    </div>
  );
}
