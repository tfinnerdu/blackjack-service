import type { RoundView, SessionView } from "../lib/types";

const RESULT_COLORS: Record<string, string> = {
  win: "text-emerald-300",
  blackjack: "text-emerald-300",
  loss: "text-red-300",
  bust: "text-red-300",
  surrender: "text-amber-300",
  push: "text-white/70",
};

export function RoundSummary({
  round,
  session,
  onNext,
}: {
  round: RoundView;
  session: SessionView;
  onNext: () => void;
}) {
  if (round.state !== "complete" || !round.result) return null;
  const playerSeat = session.player_seat;
  const playerOutcomes = round.result.outcomes.filter((o) => o.seat_num === playerSeat);
  const insurance = round.result.insurance_outcomes[String(playerSeat)] ?? 0;
  const sideBets = round.result.side_bet_outcomes[String(playerSeat)] ?? {};

  const totalProfit =
    playerOutcomes.reduce((acc, o) => acc + o.profit, 0) +
    insurance +
    Object.values(sideBets).reduce((a, b) => a + b, 0);

  const big = totalProfit > 0;

  return (
    <div
      className="fixed inset-x-0 bottom-0 px-3 pt-3 bg-felt-dark/95 backdrop-blur ring-1 ring-white/10"
      style={{ paddingBottom: "calc(env(safe-area-inset-bottom) + 12px)" }}
    >
      <div className="max-w-md mx-auto space-y-3">
        <div className="text-center">
          <div className="text-xs uppercase tracking-wide text-white/60">Round result</div>
          <div
            className={`text-3xl font-mono font-bold ${big ? "text-emerald-300" : totalProfit < 0 ? "text-red-300" : "text-white"}`}
          >
            {totalProfit >= 0 ? "+" : ""}${totalProfit}
          </div>
          {round.result.dealer_blackjack && (
            <div className="text-xs text-amber-300 mt-1">Dealer had blackjack</div>
          )}
        </div>

        <div className="space-y-1 text-sm">
          {playerOutcomes.map((o) => (
            <div key={o.hand_index} className="flex justify-between">
              <span className={RESULT_COLORS[o.result] ?? "text-white"}>
                {playerOutcomes.length > 1 ? `Hand ${o.hand_index + 1}: ` : ""}
                {o.result} ({o.final_total})
              </span>
              <span className="font-mono">
                {o.profit >= 0 ? "+" : ""}${o.profit}
              </span>
            </div>
          ))}
          {insurance !== 0 && (
            <div className="flex justify-between text-amber-300">
              <span>Insurance</span>
              <span className="font-mono">
                {insurance >= 0 ? "+" : ""}${insurance}
              </span>
            </div>
          )}
          {Object.entries(sideBets)
            .filter(([, v]) => v !== 0)
            .map(([k, v]) => (
              <div key={k} className="flex justify-between text-white/70">
                <span>{k.replace(/_/g, " ")}</span>
                <span className="font-mono">
                  {v >= 0 ? "+" : ""}${v}
                </span>
              </div>
            ))}
        </div>

        <button
          onClick={onNext}
          className="w-full min-h-touch rounded-xl bg-white text-felt-dark font-semibold"
        >
          Next hand
        </button>
      </div>
    </div>
  );
}
