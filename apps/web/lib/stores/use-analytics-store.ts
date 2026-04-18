"use client";

import { create } from "zustand";
import type { BreakdownMode, ForecastHorizon } from "@/types/analytics";

export interface AnalyticsStoreState {
  breakdownMode: BreakdownMode;
  forecastHorizon: ForecastHorizon;
  setBreakdownMode: (mode: BreakdownMode) => void;
  setForecastHorizon: (days: ForecastHorizon) => void;
  reset: () => void;
}

const initialState = {
  breakdownMode: "workspace" as const,
  forecastHorizon: 30 as const,
};

export const useAnalyticsStore = create<AnalyticsStoreState>()((set) => ({
  ...initialState,
  setBreakdownMode: (breakdownMode) => set({ breakdownMode }),
  setForecastHorizon: (forecastHorizon) => set({ forecastHorizon }),
  reset: () => set(initialState),
}));
