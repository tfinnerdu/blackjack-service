import { CardSpread } from "./Card";
import type { DealerView } from "../lib/types";

export function Dealer({ dealer, hideHole }: { dealer: DealerView; hideHole: boolean }) {
  // Show total only when it's settled / fully revealed; mid-round we show
  // the up-card value so the player has the same info they would at a real
  // table.
  const visibleTotal = hideHole
    ? dealer.cards[0]
      ? cardValue(dealer.cards[0].rank)
      : 0
    : dealer.total;
  const status = dealer.bust ? "Bust" : dealer.blackjack ? "Blackjack" : "";

  return (
    <div className="rounded-xl bg-felt-dark/60 p-3 ring-1 ring-white/10">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs uppercase tracking-wide text-white/60">Dealer</span>
        <span className="text-lg font-mono font-semibold">
          {visibleTotal}
          {status && <span className="ml-2 text-xs uppercase text-white/70">{status}</span>}
        </span>
      </div>
      <CardSpread cards={dealer.cards} hideSecond={hideHole} />
    </div>
  );
}

function cardValue(rank: string): number {
  if (rank === "A") return 11;
  if (["T", "J", "Q", "K"].includes(rank)) return 10;
  return parseInt(rank, 10);
}
