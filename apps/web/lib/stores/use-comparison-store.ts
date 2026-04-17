"use client";

import { create } from "zustand";

const MAX_COMPARISON_AGENTS = 4;

interface ComparisonState {
  selectedFqns: string[];
  add: (fqn: string) => void;
  remove: (fqn: string) => void;
  clear: () => void;
  isSelected: (fqn: string) => boolean;
  canAdd: () => boolean;
  toggle: (fqn: string) => void;
}

export const useComparisonStore = create<ComparisonState>()((set, get) => ({
  selectedFqns: [],
  add: (fqn) =>
    set((state) => {
      if (state.selectedFqns.includes(fqn) || state.selectedFqns.length >= MAX_COMPARISON_AGENTS) {
        return state;
      }

      return { selectedFqns: [...state.selectedFqns, fqn] };
    }),
  remove: (fqn) =>
    set((state) => ({
      selectedFqns: state.selectedFqns.filter((entry) => entry !== fqn),
    })),
  clear: () => set({ selectedFqns: [] }),
  isSelected: (fqn) => get().selectedFqns.includes(fqn),
  canAdd: () => get().selectedFqns.length < MAX_COMPARISON_AGENTS,
  toggle: (fqn) => {
    if (get().selectedFqns.includes(fqn)) {
      get().remove(fqn);
      return;
    }

    get().add(fqn);
  },
}));
