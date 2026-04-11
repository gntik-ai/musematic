"use client";

import { useEffect, useState } from "react";
import { RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useWebSocket } from "@/components/providers/WebSocketProvider";
import type { WsConnectionState } from "@/types/websocket";

const stateClasses: Record<WsConnectionState, string> = {
  connected: "bg-green-500",
  connecting: "animate-pulse bg-slate-400",
  disconnected: "bg-red-500",
  reconnecting: "bg-amber-500",
};

export function ConnectionIndicator() {
  const client = useWebSocket();
  const [state, setState] = useState<WsConnectionState>(client.connectionState);

  useEffect(() => client.onStateChange(setState), [client]);

  return (
    <div className="flex items-center gap-3 text-sm">
      <div className="flex items-center gap-2" title={`WebSocket state: ${state}`}>
        <span className={`h-2.5 w-2.5 rounded-full ${stateClasses[state]}`} />
        {state === "connected" ? null : <span className="text-muted-foreground">{state === "reconnecting" ? "Reconnecting..." : state}</span>}
      </div>
      {state === "disconnected" ? (
        <Button className="gap-2" size="sm" variant="outline" onClick={() => client.connect()}>
          <RotateCw className="h-3.5 w-3.5" />
          Retry
        </Button>
      ) : null}
    </div>
  );
}
