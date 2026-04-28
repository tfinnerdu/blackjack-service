// Touch-friendly card picker. Tap a rank, tap a suit, the card is appended
// to the active "slot" (your hand / hole / board, depending on context).
// Tapping an existing card removes it.

import { useState } from "react";

const RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K"] as const;
const SUITS = [
  { code: "S", glyph: "♠", red: false },
  { code: "H", glyph: "♥", red: true },
  { code: "D", glyph: "♦", red: true },
  { code: "C", glyph: "♣", red: false },
] as const;

export function CardPicker({
  onAdd,
  onAddJoker,
  jokersAllowed,
}: {
  onAdd: (token: string) => void;
  onAddJoker?: (big: boolean) => void;
  jokersAllowed?: boolean;
}) {
  const [rank, setRank] = useState<string | null>(null);

  function pickSuit(suit: string) {
    if (!rank) return;
    onAdd(`${rank}${suit}`);
    setRank(null);
  }

  return (
    <div className="space-y-2">
      <div className="text-xs uppercase tracking-wide text-white/60">
        {rank ? `Pick a suit for ${rank}` : "Pick a rank"}
      </div>

      {!rank ? (
        <div className="grid grid-cols-7 gap-1.5">
          {RANKS.map((r) => (
            <button
              key={r}
              onClick={() => setRank(r)}
              className="min-h-touch rounded-lg bg-felt text-white font-mono text-base"
            >
              {r === "T" ? "10" : r}
            </button>
          ))}
          {jokersAllowed && onAddJoker ? (
            <button
              onClick={() => onAddJoker(true)}
              className="min-h-touch col-span-7 rounded-lg bg-amber-500/30 text-amber-100 font-mono text-sm"
            >
              + Big joker (JK)
            </button>
          ) : null}
        </div>
      ) : (
        <div className="grid grid-cols-4 gap-1.5">
          {SUITS.map((s) => (
            <button
              key={s.code}
              onClick={() => pickSuit(s.code)}
              className={`min-h-touch rounded-lg bg-white text-2xl ${s.red ? "text-red-600" : "text-black"}`}
            >
              {s.glyph}
            </button>
          ))}
          <button
            onClick={() => setRank(null)}
            className="min-h-touch col-span-4 rounded-lg border border-white/20 text-xs text-white/60"
          >
            cancel
          </button>
        </div>
      )}
    </div>
  );
}

export function CardChips({
  cards,
  onRemove,
  onToggleWild,
  wildIndices,
  emptyLabel,
}: {
  cards: string[];
  onRemove: (index: number) => void;
  onToggleWild?: (index: number) => void;
  wildIndices?: number[];
  emptyLabel: string;
}) {
  if (cards.length === 0) {
    return <div className="text-xs text-white/40 italic">{emptyLabel}</div>;
  }
  const wildSet = new Set(wildIndices ?? []);
  const wildMode = !!onToggleWild;
  return (
    <div className="flex flex-wrap gap-1.5">
      {cards.map((token, i) => {
        const isJoker = token === "JK" || token === "jk";
        const suit = isJoker ? "" : token[1];
        const rank = isJoker ? "" : token[0] === "T" ? "10" : token[0];
        const red = suit === "H" || suit === "D";
        const isWild = wildSet.has(i);
        return (
          <button
            key={i}
            onClick={() => (wildMode ? onToggleWild!(i) : onRemove(i))}
            className={`min-h-touch px-2 rounded-lg font-mono text-sm flex items-center gap-1
              ${isJoker
                ? "bg-amber-500/30 text-amber-100"
                : "bg-white"}
              ${isWild ? "ring-2 ring-amber-400" : ""}`}
            title={wildMode ? "Tap to mark wild" : "Tap to remove"}
          >
            {isJoker ? (
              <span>{token}</span>
            ) : (
              <>
                <span className={red ? "text-red-600" : "text-black"}>{rank}</span>
                <span className={red ? "text-red-600" : "text-black"}>
                  {suit === "S" ? "♠" : suit === "H" ? "♥" : suit === "D" ? "♦" : "♣"}
                </span>
              </>
            )}
            {!wildMode && <span className="text-xs opacity-50">×</span>}
            {isWild && <span className="text-xs text-amber-600">★</span>}
          </button>
        );
      })}
    </div>
  );
}
