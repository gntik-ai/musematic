"use client";

import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { useMcpServerMutations, useMcpServers } from "@/lib/hooks/use-mcp-servers";

const HEALTH_META = {
  healthy: { className: "bg-emerald-500/10 text-emerald-700", label: "Healthy" },
  unhealthy: { className: "bg-red-500/10 text-red-700", label: "Unhealthy" },
  unknown: { className: "bg-amber-500/10 text-amber-700", label: "Unknown" },
} as const;

export interface AgentProfileMcpTabProps {
  agentId: string;
}

export function AgentProfileMcpTab({ agentId }: AgentProfileMcpTabProps) {
  const { servers, isLoading } = useMcpServers(agentId);
  const { disconnectServer } = useMcpServerMutations(agentId);
  const [serverIdToRemove, setServerIdToRemove] = useState<string | null>(null);
  const serverToRemove = useMemo(
    () => servers.find((server) => server.id === serverIdToRemove) ?? null,
    [serverIdToRemove, servers],
  );

  return (
    <div className="space-y-3">
      {isLoading ? (
        <div className="h-24 animate-pulse rounded-2xl bg-muted/50" />
      ) : servers.length === 0 ? (
        <p className="rounded-xl border border-border/70 bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
          No MCP servers are registered.
        </p>
      ) : (
        servers.map((server) => {
          const healthMeta = HEALTH_META[server.healthStatus];
          return (
            <div
              key={server.id}
              className="flex flex-col gap-4 rounded-2xl border border-border/70 bg-card/80 p-4 md:flex-row md:items-center md:justify-between"
            >
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-medium">{server.name}</p>
                  <Badge className={healthMeta.className} variant="secondary">
                    {healthMeta.label}
                  </Badge>
                </div>
                <p className="text-sm text-muted-foreground">{server.endpoint}</p>
                <p className="text-xs text-muted-foreground">
                  {server.capabilityCounts.tools} tools · {server.capabilityCounts.resources} resources
                </p>
              </div>
              <Button variant="outline" onClick={() => setServerIdToRemove(server.id)}>
                Disconnect
              </Button>
            </div>
          );
        })
      )}
      <ConfirmDialog
        confirmLabel="Disconnect"
        description={`Disconnect ${serverToRemove?.name ?? "this server"}?`}
        isLoading={disconnectServer.isPending}
        open={Boolean(serverToRemove)}
        title="Disconnect MCP server"
        variant="destructive"
        onConfirm={() => {
          if (!serverToRemove) {
            return;
          }
          void disconnectServer.mutateAsync({ serverId: serverToRemove.id }).then(() => {
            setServerIdToRemove(null);
          });
        }}
        onOpenChange={(open) => {
          if (!open) {
            setServerIdToRemove(null);
          }
        }}
      />
    </div>
  );
}
