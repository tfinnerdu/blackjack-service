// Shared types — these mirror the Flask API exactly. Whenever the API
// response shape changes, this file changes too.

export type CardSuit = "S" | "H" | "D" | "C";
export type CardRank = "A" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9" | "T" | "J" | "Q" | "K";

export interface CardJSON {
  rank: CardRank;
  suit: CardSuit;
}

export type ActionVerb = "hit" | "stand" | "double" | "split" | "surrender";

export interface HandView {
  cards: CardJSON[];
  total: number;
  soft: boolean;
  bust: boolean;
  blackjack: boolean;
  bet: number;
  doubled: boolean;
  surrendered: boolean;
  from_split: boolean;
  from_split_aces: boolean;
  insurance_bet: number;
  stood: boolean;
  finished: boolean;
}

export interface SeatView {
  seat_num: number;
  main_bet: number;
  is_human: boolean;
  bankroll_before: number;
  finished: boolean;
  side_bet_results: Record<string, number>;
  insurance_decided: boolean;
  hands: HandView[];
}

export interface DealerView {
  cards: CardJSON[];
  total: number;
  blackjack: boolean;
  bust: boolean;
  finished: boolean;
}

export interface BookView {
  action: ActionVerb;
  source: "basic" | "index" | "fallback";
  deviation: string | null;
  basic_action: ActionVerb;
}

export interface HandOutcomeView {
  seat_num: number;
  hand_index: number;
  bet: number;
  profit: number;
  result: "win" | "loss" | "push" | "blackjack" | "surrender" | "bust";
  final_total: number;
  final_cards: CardJSON[];
}

export interface RoundResultView {
  outcomes: HandOutcomeView[];
  insurance_outcomes: Record<string, number>;
  side_bet_outcomes: Record<string, Record<string, number>>;
  dealer_blackjack: boolean;
}

export type RoundState =
  | "betting"
  | "dealing"
  | "insurance"
  | "playing"
  | "dealer"
  | "settling"
  | "complete";

export interface RoundView {
  state: RoundState;
  seats: SeatView[];
  dealer: DealerView;
  active_seat_num: number | null;
  active_hand_index: number | null;
  legal_actions: ActionVerb[];
  insurance_offered: boolean;
  book: BookView | null;
  result: RoundResultView | null;
}

// ---- session ----------------------------------------------------------

export interface RulesView {
  decks: number;
  shuffle_mode: string;
  penetration: number;
  seats: number;
  player_seat: number;
  dealer_hits_soft_17: boolean;
  dealer_peeks: boolean;
  european_no_hole_card: boolean;
  blackjack_payout: [number, number];
  insurance_payout: [number, number];
  double_rule: string;
  double_after_split: boolean;
  max_splits: number;
  resplit_aces: boolean;
  hit_split_aces: boolean;
  surrender: string;
  insurance_offered: boolean;
  starting_bankroll: number;
  min_bet: number;
  max_bet: number;
  bet_increment: number;
}

export interface AISeatView {
  seat_num: number;
  playstyle: string;
  bet_pattern: string;
  base_bet: number;
  bankroll: number;
  rebuy_on_bust?: boolean;
  rebuy_amount?: number;
  drunk_mistake_rate?: number;
  is_bust?: boolean;
}

export interface SessionView {
  id: number;
  token: string;
  room_code: string | null;
  seat_tokens: Record<string, string>;
  template_id: number | null;
  template_name: string | null;
  rules: RulesView;
  side_bets: Record<string, unknown>;
  starting_bankroll: number;
  bankroll: number;
  shoe: { seed: number; cards_dealt: number; shuffles?: number };
  counter: { running_count: number; cards_seen: number };
  player_seat: number;
  ai_seats: AISeatView[];
  stats: {
    hands_played: number;
    actual_profit: number;
    book_profit: number;
    book_mistakes: number;
    wins: number;
    losses: number;
    pushes: number;
    player_blackjacks: number;
    busts: number;
    surrenders: number;
  };
  active_round: unknown | null;
  created_at: string;
  updated_at: string;
  caller_seat?: number | null;
  caller_is_host?: boolean;
  caller_seat_bet?: number | null;
}

export interface RoomSeatView {
  seat_num: number;
  kind: "host" | "guest" | "ai";
  claimable: boolean;
  playstyle?: string | null;
  bet_pattern?: string | null;
  base_bet?: number | null;
  bankroll?: number | null;
}

export interface RoomLobbyView {
  room_code: string;
  template_name: string | null;
  rules: RulesView;
  seats: RoomSeatView[];
  player_seat: number;
  hands_played: number;
}

export interface ClaimSeatResponse {
  token: string;
  seat_num: number;
  room: RoomLobbyView;
}

export interface TemplateView {
  id: number;
  name: string;
  description: string;
  rules: Partial<RulesView>;
  side_bets: Record<string, unknown>;
  is_builtin: boolean;
  created_at: string;
  updated_at: string;
}

export interface ApiError {
  error: string;
  code: string;
}
