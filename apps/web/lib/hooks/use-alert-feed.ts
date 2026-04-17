"use client";

import { useEffect } from "react";
import { useAlertFeedStore } from "@/lib/stores/use-alert-feed-store";
import { normalizeOperatorAlert } from "@/lib/hooks/operator-dashboard-shared";
import { wsClient } from "@/lib/ws";

export function useAlertFeed() {
  const addAlert = useAlertFeedStore((state) => state.addAlert);
  const setConnected = useAlertFeedStore((state) => state.setConnected);

  useEffect(() => {
    wsClient.connect();

    const unsubscribeConnection = wsClient.onConnectionChange((isConnected) => {
      setConnected(isConnected);
    });
    const unsubscribeAlerts = wsClient.subscribe("alerts", (event) => {
      addAlert(normalizeOperatorAlert(event.payload, event.timestamp));
    });

    return () => {
      unsubscribeAlerts();
      unsubscribeConnection();
    };
  }, [addAlert, setConnected]);

  return {
    isConnected: useAlertFeedStore.getState().isConnected,
  };
}
