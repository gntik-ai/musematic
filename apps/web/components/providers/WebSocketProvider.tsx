"use client";

import * as React from "react";
import { type WebSocketClient, wsClient } from "@/lib/ws";

const WebSocketContext = React.createContext<WebSocketClient | null>(null);

export function WebSocketProvider({ children }: React.PropsWithChildren) {
  const client = React.useMemo(() => wsClient, []);
  const [, forceRender] = React.useState(0);

  React.useEffect(() => {
    client.connect();
    const unsubscribe = client.onStateChange(() => {
      forceRender((value) => value + 1);
    });

    return () => {
      unsubscribe();
      client.disconnect();
    };
  }, [client]);

  return <WebSocketContext.Provider value={client}>{children}</WebSocketContext.Provider>;
}

export function useWebSocket(): WebSocketClient {
  const context = React.useContext(WebSocketContext);
  if (!context) {
    throw new Error("useWebSocket must be used within WebSocketProvider");
  }
  return context;
}
