// Felt-style Craps layout. Each labeled cell is a tappable bet zone
// — tapping adds a bet of the current unit stake; tapping again
// stacks more on the same area. A small ✕ in each occupied cell
// cancels the most-recent bet on that zone.
//
// The standard craps layout is denser than this — we collapse the
// near-symmetric Pass / Don't Pass bars and the prop / hardway
// areas into a compact grid that reads on mobile.

interface BookBet {
  bet_id: string;
  bet_type: string;
  stake: number;
  selection?: number;
  established_point?: number | null;
}

const PLACE_NUMBERS = [4, 5, 6, 8, 9, 10];
const HARD_NUMBERS = [4, 6, 8, 10];

export function CrapsTable({
  book,
  onAddBet,
  onCancelBet,
}: {
  book: BookBet[];
  onAddBet: (bet_type: string, selection?: number) => void;
  onCancelBet: (bet_id: string) => void;
}) {
  // Bucket the user's open bets so each zone can show its own chip
  // stack + cancel-by-zone affordance.
  function betsFor(bet_type: string, selection?: number): BookBet[] {
    return book.filter((b) =>
      b.bet_type === bet_type
      && (selection == null || b.selection === selection),
    );
  }

  return (
    <div
      className="rounded-2xl p-2 ring-1 ring-amber-700/50 shadow-inner"
      style={{ background: "linear-gradient(135deg, #0e5b34 0%, #073a23 60%, #052a1a 100%)" }}
    >
      {/* Top: Come (full width) */}
      <Zone
        label="Come"
        sub="1:1"
        bets={betsFor("come")}
        onTap={() => onAddBet("come")}
        onCancel={onCancelBet}
        accent="border-amber-500/60"
        height="h-14"
      />

      {/* Place numbers row */}
      <div className="grid grid-cols-6 gap-1 mt-1">
        {PLACE_NUMBERS.map((n) => (
          <Zone
            key={`place-${n}`}
            label={String(n)}
            sub="place"
            bets={betsFor("place", n)}
            onTap={() => onAddBet("place", n)}
            onCancel={onCancelBet}
            accent="border-emerald-700/70"
            height="h-12"
            mono
          />
        ))}
      </div>

      {/* Field bar */}
      <Zone
        label="Field"
        sub="2/3/4/9/10/11/12 · 2x on 2, 3x on 12"
        bets={betsFor("field")}
        onTap={() => onAddBet("field")}
        onCancel={onCancelBet}
        accent="border-amber-500/60"
        height="h-12"
      />

      {/* Hardways grid */}
      <div className="grid grid-cols-4 gap-1 mt-1">
        {HARD_NUMBERS.map((n) => (
          <Zone
            key={`hard-${n}`}
            label={`Hard ${n}`}
            sub={n === 6 || n === 8 ? "9:1" : "7:1"}
            bets={betsFor("hard", n)}
            onTap={() => onAddBet("hard", n)}
            onCancel={onCancelBet}
            accent="border-rose-600/60"
            height="h-12"
          />
        ))}
      </div>

      {/* Pass / Don't Pass */}
      <div className="grid grid-cols-2 gap-1 mt-1">
        <Zone
          label="Pass Line"
          sub="1:1"
          bets={betsFor("pass_line")}
          onTap={() => onAddBet("pass_line")}
          onCancel={onCancelBet}
          accent="border-amber-400/70"
          height="h-12"
        />
        <Zone
          label="Don't Pass"
          sub="1:1, 12 push"
          bets={betsFor("dont_pass")}
          onTap={() => onAddBet("dont_pass")}
          onCancel={onCancelBet}
          accent="border-amber-400/70"
          height="h-12"
        />
      </div>

      {/* Props */}
      <div className="grid grid-cols-2 gap-1 mt-1">
        <Zone
          label="Any 7"
          sub="4:1 one-roll"
          bets={betsFor("any_seven")}
          onTap={() => onAddBet("any_seven")}
          onCancel={onCancelBet}
          accent="border-rose-600/60"
          height="h-10"
        />
        <Zone
          label="Any Craps"
          sub="7:1 one-roll"
          bets={betsFor("any_craps")}
          onTap={() => onAddBet("any_craps")}
          onCancel={onCancelBet}
          accent="border-rose-600/60"
          height="h-10"
        />
      </div>
    </div>
  );
}

function Zone({
  label,
  sub,
  bets,
  onTap,
  onCancel,
  accent,
  height,
  mono,
}: {
  label: string;
  sub: string;
  bets: BookBet[];
  onTap: () => void;
  onCancel: (bet_id: string) => void;
  accent: string;
  height: string;
  mono?: boolean;
}) {
  const total = bets.reduce((s, b) => s + b.stake, 0);
  return (
    <div
      onClick={onTap}
      className={`relative rounded-md ${height} px-2 py-1 cursor-pointer
        bg-emerald-900/40 hover:bg-emerald-900/60 border ${accent}
        flex flex-col justify-center select-none transition-colors`}
    >
      <div
        className={`text-white text-xs leading-tight ${
          mono ? "font-mono text-base" : "font-semibold uppercase tracking-wide"
        }`}
      >
        {label}
      </div>
      <div className="text-[10px] text-white/55 leading-tight">{sub}</div>

      {total > 0 && (
        <div className="absolute right-1 top-1 flex items-center gap-1">
          <ChipStack amount={total} />
          <button
            onClick={(e) => {
              e.stopPropagation();
              onCancel(bets[bets.length - 1].bet_id);
            }}
            className="text-[10px] text-white/60 leading-none hover:text-white"
            aria-label="cancel last bet"
          >
            ✕
          </button>
        </div>
      )}
    </div>
  );
}

function ChipStack({ amount }: { amount: number }) {
  // Pick a chip color based on dollar amount so the eye reads $25
  // chips green, $100 chips black, etc. — casino convention.
  const color =
    amount >= 100 ? "bg-zinc-900 ring-zinc-100"
    : amount >= 25 ? "bg-emerald-700 ring-emerald-100"
    : amount >= 5 ? "bg-rose-700 ring-rose-100"
    : "bg-sky-700 ring-sky-100";
  return (
    <div
      className={`min-w-[28px] h-5 rounded-full flex items-center justify-center
        text-[10px] font-mono text-white ring-2 ${color}`}
      style={{ boxShadow: "0 1px 4px rgba(0,0,0,0.5)" }}
    >
      ${amount}
    </div>
  );
}
