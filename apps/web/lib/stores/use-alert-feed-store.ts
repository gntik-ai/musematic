"use client";

import { create } from "zustand";
import type { AlertFeedState, OperatorAlert } from "@/lib/types/operator-dashboard";

const MAX_ALERTS = 200;

const initialState = {
  alerts: [] as OperatorAlert[],
  isConnected: true,
  severityFilter: "all" as const,
};

export const useAlertFeedStore = create<AlertFeedState>()((set) => ({
  ...initialState,
  addAlert: (alert) =>
    set((state) => ({
      alerts: [alert, ...state.alerts].slice(0, MAX_ALERTS),
    })),
  setConnected: (connected) => set({ isConnected: connected }),
  setSeverityFilter: (severityFilter) => set({ severityFilter }),
  clearAlerts: () => set({ alerts: [] }),
}));
