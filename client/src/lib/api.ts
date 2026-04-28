// Thin fetch wrapper. Cookie-based auth means we don't have to plumb a
// token through the call sites — `credentials: "include"` is enough.

import type {
  ActionVerb,
  ClaimSeatResponse,
  RoomLobbyView,
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

export const Rooms = {
  lobby: (code: string) =>
    http<RoomLobbyView>("GET", `/api/v1/sessions/by-code/${encodeURIComponent(code)}`),
  claim: (code: string, seatNum: number) =>
    http<ClaimSeatResponse>(
      "POST",
      `/api/v1/sessions/by-code/${encodeURIComponent(code)}/seats/${seatNum}/claim`,
    ),
  release: (code: string, seatNum: number) =>
    http<RoomLobbyView>(
      "POST",
      `/api/v1/sessions/by-code/${encodeURIComponent(code)}/seats/${seatNum}/release`,
    ),
};

// ---- casino: roulette / baccarat / craps ------------------------------

export interface CasinoParticipant {
  label: string;
  is_host: boolean;
  bankroll: number;
  rounds_played: number;
  has_pending_bets?: boolean;
  open_bets?: number;
}

export interface CasinoSessionView {
  id: number;
  token?: string;
  game_type: string;
  room_code: string | null;
  guest_tokens: Record<string, unknown>;
  starting_bankroll: number;
  bankroll: number;
  rounds_played: number;
  rules: Record<string, any>;
  state: Record<string, any>;
  history: Array<Record<string, unknown>>;
  caller_is_host: boolean;
  caller_bankroll: number;
  caller_pending_bets?: Array<Record<string, unknown>>;
  caller_book?: Array<Record<string, unknown>>;
  participants: CasinoParticipant[];
}

export interface CasinoSpinResult {
  spin?: { pocket: string; color: string; is_zero: boolean };
  round?: {
    player_cards: Array<{ rank: string; suit: string }>;
    banker_cards: Array<{ rank: string; suit: string }>;
    player_total: number;
    banker_total: number;
    outcome: "player" | "banker" | "tie";
    natural: boolean;
    player_pair: boolean;
    banker_pair: boolean;
  };
  roll?: { d1: number; d2: number; total: number; hard: boolean };
  phase_after?: string;
  point_after?: number | null;
  participants: Array<{
    label: string;
    is_host: boolean;
    total_profit: number;
    bankroll_after: number;
    payouts?: number[];
    outcomes?: Array<{
      bet_id: string;
      profit: number;
      resolved: boolean;
      note: string;
    }>;
  }>;
}

export const Roulette = {
  create: (body: {
    starting_bankroll?: number;
    wheel_kind?: "american" | "european";
    min_bet?: number;
    max_bet?: number;
    seed?: number;
  }) => http<CasinoSessionView>("POST", "/api/v1/roulette/sessions", body),
  me: () => http<CasinoSessionView>("GET", "/api/v1/roulette/sessions/me"),
  stageBets: (bets: Array<{ bet_type: string; stake: number; selection?: unknown }>) =>
    http<CasinoSessionView>("POST", "/api/v1/roulette/sessions/me/bets", { bets }),
  spin: () => http<CasinoSpinResult>("POST", "/api/v1/roulette/sessions/me/spin", {}),
  joinByCode: (code: string, body?: { label?: string; starting_bankroll?: number }) =>
    http<{ token: string; room: CasinoSessionView }>(
      "POST",
      `/api/v1/roulette/sessions/by-code/${encodeURIComponent(code)}/join`,
      body ?? {},
    ),
  destroy: () => http<{ deleted: boolean }>("DELETE", "/api/v1/roulette/sessions/me"),
};

export const Baccarat = {
  create: (body: {
    starting_bankroll?: number;
    decks?: number;
    min_bet?: number;
    max_bet?: number;
    seed?: number;
  }) => http<CasinoSessionView>("POST", "/api/v1/baccarat/sessions", body),
  me: () => http<CasinoSessionView>("GET", "/api/v1/baccarat/sessions/me"),
  stageBets: (bets: Array<{ bet_type: string; stake: number }>) =>
    http<CasinoSessionView>("POST", "/api/v1/baccarat/sessions/me/bets", { bets }),
  play: () => http<CasinoSpinResult>("POST", "/api/v1/baccarat/sessions/me/play", {}),
  joinByCode: (code: string, body?: { label?: string; starting_bankroll?: number }) =>
    http<{ token: string; room: CasinoSessionView }>(
      "POST",
      `/api/v1/baccarat/sessions/by-code/${encodeURIComponent(code)}/join`,
      body ?? {},
    ),
  destroy: () => http<{ deleted: boolean }>("DELETE", "/api/v1/baccarat/sessions/me"),
};

export const Craps = {
  create: (body: {
    starting_bankroll?: number;
    min_bet?: number;
    max_bet?: number;
    seed?: number;
  }) => http<CasinoSessionView>("POST", "/api/v1/craps/sessions", body),
  me: () => http<CasinoSessionView>("GET", "/api/v1/craps/sessions/me"),
  addBets: (bets: Array<{
    bet_type: string;
    stake: number;
    selection?: number;
  }>) =>
    http<CasinoSessionView>("POST", "/api/v1/craps/sessions/me/bets", { bets }),
  cancelBet: (betId: string) =>
    http<CasinoSessionView>(
      "DELETE",
      `/api/v1/craps/sessions/me/bets/${encodeURIComponent(betId)}`,
    ),
  roll: (dice?: [number, number]) =>
    http<CasinoSpinResult>(
      "POST",
      "/api/v1/craps/sessions/me/roll",
      dice ? { dice } : {},
    ),
  joinByCode: (code: string, body?: { label?: string; starting_bankroll?: number }) =>
    http<{ token: string; room: CasinoSessionView }>(
      "POST",
      `/api/v1/craps/sessions/by-code/${encodeURIComponent(code)}/join`,
      body ?? {},
    ),
  destroy: () => http<{ deleted: boolean }>("DELETE", "/api/v1/craps/sessions/me"),
};

export const Seat = {
  setBet: (bet: number) =>
    http<{ seat_num: number; bet: number }>(
      "POST",
      "/api/v1/sessions/me/seat/bet",
      { bet },
    ),
};

// ---- sportsbook -------------------------------------------------------

export interface SportsMarket {
  id: number;
  event_id: number;
  market_type: "moneyline" | "spread" | "total" | string;
  selections: Array<{
    key: string;
    label: string;
    odds: number;
    line: number | null;
  }>;
  status: string;
  winner_key: string | null;
}

export interface SportsEvent {
  id: number;
  sport: string;
  league: string;
  home_team: string;
  away_team: string;
  day: number;
  status: "scheduled" | "final" | string;
  home_score: number | null;
  away_score: number | null;
  markets: SportsMarket[];
}

export interface SportsSlipLeg {
  market_id: number;
  selection_key: string;
  odds: number;
  label?: string;
  line?: number | null;
  market_type?: string;
  event_id?: number;
  event_label?: string;
  event_day?: number;
  outcome?: "won" | "lost" | "push" | "void" | null;
}

export interface SportsSlip {
  id: number;
  slip_type: "single" | "parlay";
  legs: SportsSlipLeg[];
  stake: number;
  potential_payout: number;
  status: "pending" | "won" | "lost" | "push" | "void";
  payout_actual: number;
  net: number;
  placed_at: string;
  placed_on_day: number;
  settled_at: string | null;
  leg_results: SportsSlipLeg[] | null;
}

export interface SportsbookSessionView {
  id: number;
  token: string;
  starting_bankroll: number;
  bankroll: number;
  current_day: number;
  slips_placed: number;
  slips_won: number;
  slips_lost: number;
  slips_pushed: number;
  total_staked: number;
  total_returned: number;
  analytics_summary?: SportsAnalyticsSummary;
}

export interface SportsAnalyticsSummary {
  bankroll: number;
  starting_bankroll: number;
  net_profit: number;
  total_staked: number;
  total_returned: number;
  roi_pct: number;
  slips_placed: number;
  slips_won: number;
  slips_lost: number;
  slips_pushed: number;
  win_rate_pct: number;
  settled_count: number;
  wins: number;
  losses: number;
  pushes: number;
}

export interface SportsAnalytics {
  summary: SportsAnalyticsSummary;
  by_market_type: Record<string, { won: number; lost: number; push: number }>;
  by_slip_type: Record<string, {
    won: number; lost: number; push: number;
    staked: number; returned: number;
  }>;
  streak: { sign: number; count: number };
  surprising_losses: Array<{
    slip_id: number;
    leg_label: string | null;
    event_label: string | null;
    odds: number;
  }>;
}

export const Sportsbook = {
  create: (body?: { starting_bankroll?: number; seed?: number }) =>
    http<SportsbookSessionView>(
      "POST",
      "/api/v1/sportsbook/sessions",
      body ?? {},
    ),
  me: () => http<SportsbookSessionView>("GET", "/api/v1/sportsbook/sessions/me"),
  events: () =>
    http<{ events: SportsEvent[]; current_day: number }>(
      "GET",
      "/api/v1/sportsbook/sessions/me/events",
    ),
  slips: () =>
    http<{ slips: SportsSlip[] }>("GET", "/api/v1/sportsbook/sessions/me/slips"),
  placeSlip: (legs: Array<{ market_id: number; selection_key: string }>, stake: number) =>
    http<SportsSlip>(
      "POST",
      "/api/v1/sportsbook/sessions/me/slips",
      { legs, stake },
    ),
  advance: () =>
    http<{
      current_day: number;
      events_resolved: SportsEvent[];
      slips_settled: SportsSlip[];
    }>("POST", "/api/v1/sportsbook/sessions/me/advance", {}),
  analytics: () =>
    http<SportsAnalytics>("GET", "/api/v1/sportsbook/sessions/me/analytics"),
  destroy: () =>
    http<{ deleted: boolean }>("DELETE", "/api/v1/sportsbook/sessions/me"),
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
