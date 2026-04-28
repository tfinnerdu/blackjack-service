// Poker types + API wrappers. Mirrors app/poker/variants.py + companion.py.

import { ApiError } from "./api";

export interface DeckSpecJSON {
  decks: number;
  jokers: number;
}

export interface DealSchemeJSON {
  hole_cards: number;
  up_cards: number;
  community_streets: number[];
  stud_streets: number[];
  stud_face_down_final: boolean;
  draws: number[];
}

export interface WildRuleJSON {
  kind: string;
  mode: string;
  rank?: string | null;
  suit?: string | null;
  card_token?: string | null;
}

export interface VariantSpec {
  name: string;
  description: string;
  family: string;
  deck: DeckSpecJSON;
  deal: DealSchemeJSON;
  wilds: WildRuleJSON[];
  hand: string;
  hi_lo: string;
  lo_rule: string | null;
  lo_eight_or_better: boolean;
  notes: string;
}

export interface HighAnalysisView {
  cls_name: string;
  cls_value: number;
  tiebreakers: number[];
  cards: string[];
  explanation: string;
}

export interface LowAnalysisView {
  qualifies: boolean;
  rule: string;
  name: string;
  cards: string[];
  explanation: string;
}

export interface CompanionAnalysisView {
  variant_name: string;
  user_cards: string[];
  hi: HighAnalysisView | null;
  lo: LowAnalysisView | null;
  hi_lo_explanation: string;
  wild_resolution: string | null;
  hands_that_beat_you: string[];
  notes: string[];
}

async function http<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    credentials: "include",
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const code = (data && data.code) || `HTTP_${res.status}`;
    const msg = (data && data.error) || res.statusText || "request failed";
    throw new ApiError(res.status, code, msg);
  }
  return data as T;
}

// ---- simulator types -------------------------------------------------

export interface SeatConfigJSON {
  seat_num: number;
  name: string;
  is_human: boolean;
  stack: number;
  personality: string;
  seed?: number | null;
  last_results?: number[];
}

export interface PokerSessionView {
  id: number;
  token: string;
  variant: VariantSpec;
  config: { small_blind: number; big_blind: number; starting_stack: number };
  seats: SeatConfigJSON[];
  dealer_seat: number;
  active_hand: unknown | null;
  hands_played: number;
  starting_bankroll: number;
}

export interface PlayerView {
  seat_num: number;
  name: string;
  is_human: boolean;
  personality: string | null;
  stack: number;
  committed_this_round: number;
  folded: boolean;
  all_in: boolean;
  is_active: boolean;
}

export interface HandResultView {
  winner_seats: number[];
  pot_total: number;
  side_pots: { amount: number; eligible: number[] }[];
  community: string[];
  outcomes: {
    seat_num: number;
    profit: number;
    final_hand_name: string;
    final_cards: string[];
    won: boolean;
    reason: string;
  }[];
}

export interface RoundView {
  state:
    | "dealing" | "pre_flop" | "flop" | "turn" | "river"
    | "showdown" | "complete";
  community: string[];
  human_hole: string[];
  pot_total: number;
  current_bet: number;
  to_call: number;
  legal_actions: string[];
  active_seat: number | null;
  players: PlayerView[];
  result: HandResultView | null;
  dealer_seat: number;
}

export const Poker = {
  variants: () => http<{ variants: (VariantSpec & { _saved_template_id?: number })[] }>(
    "GET", "/api/v1/poker/variants",
  ),
  saveVariant: (variant: VariantSpec) =>
    http<VariantSpec & { _saved_template_id: number }>(
      "POST", "/api/v1/poker/variants", variant,
    ),
  deleteVariant: (templateId: number) =>
    http<void>("DELETE", `/api/v1/poker/variants/${templateId}`),
  personalities: () => http<{ personalities: string[] }>("GET", "/api/v1/poker/personalities"),
  analyze: (body: {
    variant: string | VariantSpec;
    cards?: string[];
    hole?: string[];
    board?: string[];
    wild_indices?: number[];
  }) => http<CompanionAnalysisView>("POST", "/api/v1/poker/analyze", body),

  // ---- simulator -----------------------------------------------------
  createSession: (body: {
    variant?: string;
    starting_stack?: number;
    small_blind?: number;
    big_blind?: number;
    bots?: { name: string; personality: string }[];
    human_name?: string;
  }) => http<PokerSessionView>("POST", "/api/v1/poker/sessions", body),
  getSession: () => http<PokerSessionView>("GET", "/api/v1/poker/sessions/me"),
  endSession: () => http<{ deleted: boolean }>("DELETE", "/api/v1/poker/sessions/me"),
  startHand: () => http<RoundView>("POST", "/api/v1/poker/sessions/me/hands"),
  activeHand: () => http<RoundView>("GET", "/api/v1/poker/sessions/me/hands/active"),
  act: (action: string, amount?: number) =>
    http<RoundView>(
      "POST",
      "/api/v1/poker/sessions/me/hands/active/action",
      { action, amount },
    ),
};
