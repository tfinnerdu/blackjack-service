import type { CardJSON } from "../lib/types";

const SUIT_CHAR: Record<string, string> = {
  S: "♠",
  H: "♥",
  D: "♦",
  C: "♣",
};

const RED = new Set(["H", "D"]);

export function CardFace({
  card,
  hidden,
  small,
}: {
  card?: CardJSON;
  hidden?: boolean;
  small?: boolean;
}) {
  const w = small ? "w-10 h-14" : "w-12 h-16 sm:w-14 sm:h-20";
  if (hidden || !card) {
    return (
      <div
        className={`${w} rounded-md border-2 border-white/30 bg-felt
                    flex items-center justify-center text-white/40`}
      >
        <span className="text-xs">??</span>
      </div>
    );
  }
  const red = RED.has(card.suit);
  const rankLabel = card.rank === "T" ? "10" : card.rank;
  return (
    <div
      className={`${w} rounded-md bg-white text-black flex flex-col
                  justify-between p-1 shadow-md`}
    >
      <div className={`text-xs font-bold leading-none ${red ? "text-red-600" : "text-black"}`}>
        {rankLabel}
      </div>
      <div className={`text-center text-lg leading-none ${red ? "text-red-600" : "text-black"}`}>
        {SUIT_CHAR[card.suit]}
      </div>
      <div
        className={`text-xs font-bold leading-none rotate-180 self-end ${
          red ? "text-red-600" : "text-black"
        }`}
      >
        {rankLabel}
      </div>
    </div>
  );
}

export function CardSpread({
  cards,
  hideSecond,
}: {
  cards: CardJSON[];
  hideSecond?: boolean;
}) {
  return (
    <div className="flex">
      {cards.map((c, i) => (
        <div
          key={i}
          className="-ml-3 first:ml-0"
          style={{ zIndex: i }}
        >
          <CardFace card={c} hidden={hideSecond && i === 1} />
        </div>
      ))}
    </div>
  );
}
