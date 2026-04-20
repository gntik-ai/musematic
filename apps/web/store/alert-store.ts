"use client";

import { create } from "zustand";

interface AlertStoreState {
  unreadCount: number;
  isDropdownOpen: boolean;
  increment: () => void;
  setUnreadCount: (count: number) => void;
  markAllAsRead: () => void;
  setDropdownOpen: (open: boolean) => void;
}

export const useAlertStore = create<AlertStoreState>()((set) => ({
  unreadCount: 0,
  isDropdownOpen: false,
  increment: () =>
    set((state) => ({
      unreadCount: state.unreadCount + 1,
    })),
  setUnreadCount: (count) =>
    set({
      unreadCount: Math.max(0, count),
    }),
  markAllAsRead: () => set({ unreadCount: 0 }),
  setDropdownOpen: (open) => set({ isDropdownOpen: open }),
}));
