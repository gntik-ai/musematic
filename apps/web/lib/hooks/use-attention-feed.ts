"use client";

import { useEffect } from "react";
import { useAppQuery } from "@/lib/hooks/use-api";
import { useAttentionFeedStore } from "@/lib/stores/use-attention-feed-store";
import {
  asNumber,
  normalizeAttentionEvent,
  operatorDashboardApi,
  operatorDashboardQueryKeys,
} from "@/lib/hooks/operator-dashboard-shared";
import { wsClient } from "@/lib/ws";

interface AttentionInitResponse {
  items: unknown[];
  total: number;
}

export function useAttentionFeed(userId: string | null | undefined) {
  const setEvents = useAttentionFeedStore((state) => state.setEvents);
  const addEvent = useAttentionFeedStore((state) => state.addEvent);

  const query = useAppQuery<AttentionInitResponse>(
    operatorDashboardQueryKeys.attentionInit(userId),
    async () => {
      const response = (await operatorDashboardApi.get(
        "/api/v1/interactions/attention?status=pending&page_size=50",
      )) as Record<string, unknown>;
      const items = Array.isArray(response.items) ? response.items : [];
      const normalized = items.map(normalizeAttentionEvent);
      setEvents(normalized);

      return {
        items,
        total: asNumber(response.total, items.length),
      };
    },
    {
      enabled: Boolean(userId),
      staleTime: Number.POSITIVE_INFINITY,
    },
  );

  useEffect(() => {
    if (!userId) {
      return undefined;
    }

    wsClient.connect();

    const unsubscribe = wsClient.subscribe(`attention:${userId}`, (event) => {
      addEvent(normalizeAttentionEvent(event.payload));
    });

    return () => {
      unsubscribe();
    };
  }, [addEvent, userId]);

  return {
    isLoading: query.isLoading,
  };
}
