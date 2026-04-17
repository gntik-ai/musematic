"use client";

import { create } from "zustand";
import type { AttentionFeedState } from "@/lib/types/operator-dashboard";

export const useAttentionFeedStore = create<AttentionFeedState>()((set) => ({
  events: [],
  setEvents: (events) =>
    set({
      events: [...events].sort(
        (left, right) =>
          new Date(right.createdAt).getTime() - new Date(left.createdAt).getTime(),
      ),
    }),
  addEvent: (event) =>
    set((state) => {
      const deduped = state.events.filter((item) => item.id !== event.id);
      return {
        events: [event, ...deduped].sort(
          (left, right) =>
            new Date(right.createdAt).getTime() -
            new Date(left.createdAt).getTime(),
        ),
      };
    }),
  acknowledgeEvent: (id) =>
    set((state) => ({
      events: state.events.map((event) =>
        event.id === id ? { ...event, status: "acknowledged" } : event,
      ),
    })),
}));
