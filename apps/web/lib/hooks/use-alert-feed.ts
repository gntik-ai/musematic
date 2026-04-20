"use client";

import { useEffect } from "react";
import {
  extractAlertInteractionId,
  isInteractionAlertMuted,
} from "@/lib/alerts/interaction-mutes";
import { useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import { normalizeOperatorAlert } from "@/lib/hooks/operator-dashboard-shared";
import { useAlertFeedStore } from "@/lib/stores/use-alert-feed-store";
import { wsClient } from "@/lib/ws";
import { useAlertStore } from "@/store/alert-store";
import { useAuthStore } from "@/store/auth-store";

const notificationsApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export function useAlertFeed() {
  const queryClient = useQueryClient();
  const userId = useAuthStore((state) => state.user?.id ?? null);
  const addAlert = useAlertFeedStore((state) => state.addAlert);
  const setConnected = useAlertFeedStore((state) => state.setConnected);
  const increment = useAlertStore((state) => state.increment);
  const setUnreadCount = useAlertStore((state) => state.setUnreadCount);

  useEffect(() => {
    wsClient.connect();

    const unsubscribeConnection = wsClient.onConnectionChange((isConnected) => {
      setConnected(isConnected);
      if (!isConnected || !userId) {
        return;
      }
      void notificationsApi
        .get<{ count: number }>("/me/alerts/unread-count")
        .then((response) => {
          setUnreadCount(response.count);
        })
        .catch(() => undefined);
    });
    const unsubscribeAlerts = wsClient.subscribe("alerts", (event) => {
      const interactionId = extractAlertInteractionId(event.payload);
      if (
        event.type !== "alert.read" &&
        userId &&
        isInteractionAlertMuted(userId, interactionId)
      ) {
        return;
      }

      addAlert(normalizeOperatorAlert(event.payload, event.timestamp));
      if (event.type === "alert.created") {
        increment();
      }
      if (
        event.type === "alert.read" &&
        typeof event.payload === "object" &&
        event.payload !== null &&
        "unreadCount" in event.payload
      ) {
        const unreadCount = (event.payload as { unreadCount?: unknown }).unreadCount;
        if (typeof unreadCount === "number") {
          setUnreadCount(unreadCount);
        }
      }
      if (userId) {
        void queryClient.invalidateQueries({
          queryKey: ["alert-feed", userId],
        });
      }
    });

    return () => {
      unsubscribeAlerts();
      unsubscribeConnection();
    };
  }, [addAlert, increment, queryClient, setConnected, setUnreadCount, userId]);

  return {
    isConnected: useAlertFeedStore.getState().isConnected,
  };
}
