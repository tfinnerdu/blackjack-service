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

export const Poker = {
  variants: () => http<{ variants: VariantSpec[] }>("GET", "/api/v1/poker/variants"),
  analyze: (body: {
    variant: string | VariantSpec;
    cards?: string[];
    hole?: string[];
    board?: string[];
  }) => http<CompanionAnalysisView>("POST", "/api/v1/poker/analyze", body),
};
