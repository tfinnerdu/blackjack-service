// Tiny global store for the active session + current round.
// Avoids re-fetching on every navigation; pages still call the API
// to mutate, then update the store with the response.

import { create } from "zustand";

import type { RoundView, SessionView } from "./types";

interface AppState {
  session: SessionView | null;
  round: RoundView | null;
  showCoach: boolean;
  showCount: boolean;

  setSession: (s: SessionView | null) => void;
  setRound: (r: RoundView | null) => void;
  toggleCoach: () => void;
  toggleCount: () => void;
}

export const useApp = create<AppState>((set) => ({
  session: null,
  round: null,
  showCoach: false,
  showCount: false,
  setSession: (s) => set({ session: s }),
  setRound: (r) => set({ round: r }),
  toggleCoach: () => set((st) => ({ showCoach: !st.showCoach })),
  toggleCount: () => set((st) => ({ showCount: !st.showCount })),
}));
