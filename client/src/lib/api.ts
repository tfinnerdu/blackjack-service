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

export const Templates = {
  list: () => http<{ templates: TemplateView[] }>("GET", "/api/v1/templates"),
  get: (id: number) => http<TemplateView>("GET", `/api/v1/templates/${id}`),
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

export const Sessions = {
  create: (body: CreateSessionBody) =>
    http<SessionView>("POST", "/api/v1/sessions", body),
  me: () => http<SessionView>("GET", "/api/v1/sessions/me"),
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
