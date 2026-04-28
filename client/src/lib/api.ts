// Thin fetch wrapper. Cookie-based auth means we don't have to plumb a
// token through the call sites — `credentials: "include"` is enough.

import type {
  ActionVerb,
  RoundView,
  SessionView,
  TemplateView,
} from "./types";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function http<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    credentials: "include",
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) {
    return undefined as T;
  }
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const code = (data && data.code) || `HTTP_${res.status}`;
    const msg = (data && data.error) || res.statusText || "request failed";
    throw new ApiError(res.status, code, msg);
  }
  return data as T;
}

// ---- templates ---------------------------------------------------------

export interface SaveTemplateBody {
  game_type?: string;
  name: string;
  description?: string;
  rules: Record<string, unknown>;
  side_bets: Record<string, unknown>;
}

export const Templates = {
  list: (gameType?: string) =>
    http<{ templates: TemplateView[] }>(
      "GET",
      gameType ? `/api/v1/templates?game_type=${encodeURIComponent(gameType)}` : "/api/v1/templates",
    ),
  get: (id: number) => http<TemplateView>("GET", `/api/v1/templates/${id}`),
  create: (body: SaveTemplateBody) =>
    http<TemplateView>("POST", "/api/v1/templates", body),
  update: (id: number, body: Partial<SaveTemplateBody>) =>
    http<TemplateView>("PATCH", `/api/v1/templates/${id}`, body),
  destroy: (id: number) =>
    http<void>("DELETE", `/api/v1/templates/${id}`),
};

// ---- sessions ---------------------------------------------------------

export interface CreateSessionBody {
  template_id?: number | null;
  starting_bankroll?: number;
  player_seat?: number;
  ai_seats?: unknown[];
  rules?: Record<string, unknown>;
  side_bets?: Record<string, unknown>;
  seed?: number;
}

export interface BankrollHistoryEntry {
  hand: number;
  actual: number;
  book: number;
  counter: number;
}

export interface SessionStatsView {
  hands_played: number;
  starting_bankroll: number;
  bankroll: number;
  net_profit: number;
  wins: number;
  losses: number;
  pushes: number;
  player_blackjacks: number;
  busts: number;
  surrenders: number;
  book_mistakes: number;
  ev_lost_dollars: number;
  ev_lost_estimate_note: string;
  rates: {
    win_pct: number;
    loss_pct: number;
    push_pct: number;
    mistake_pct: number;
    blackjack_pct: number;
    bust_pct: number;
  };
  counter: {
    running_count: number;
    cards_seen: number;
  };
  bankrolls: {
    actual: number;
    book: number;
    counter: number;
    starting: number;
  };
  bankroll_history: BankrollHistoryEntry[];
}

export const Sessions = {
  create: (body: CreateSessionBody) =>
    http<SessionView>("POST", "/api/v1/sessions", body),
  me: () => http<SessionView>("GET", "/api/v1/sessions/me"),
  stats: () => http<SessionStatsView>("GET", "/api/v1/sessions/me/stats"),
  reset: (seed?: number) =>
    http<SessionView>("POST", "/api/v1/sessions/me/reset", { seed }),
  destroy: () => http<{ deleted: boolean }>("DELETE", "/api/v1/sessions/me"),
};

// ---- rounds -----------------------------------------------------------

export interface StartRoundBody {
  main_bet: number;
  side_bets?: Record<string, number | string>;
}

export const Rounds = {
  start: (body: StartRoundBody) =>
    http<RoundView>("POST", "/api/v1/sessions/me/rounds", body),
  active: () => http<RoundView>("GET", "/api/v1/sessions/me/rounds/active"),
  insurance: (accept: boolean, amount?: number) =>
    http<RoundView>("POST", "/api/v1/sessions/me/rounds/active/insurance", {
      accept,
      amount,
    }),
  act: (action: ActionVerb) =>
    http<RoundView>("POST", "/api/v1/sessions/me/rounds/active/action", { action }),
};

// ---- meta -------------------------------------------------------------

export const Health = {
  ping: () =>
    http<{ status: string; service: string; version: string; uptime_seconds: number }>(
      "GET",
      "/health",
    ),
};
