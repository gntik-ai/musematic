"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity } from "lucide-react";
import { useTranslations } from "next-intl";
import { listConnectorDeliveries } from "@/lib/api/workspace-owner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export function ConnectorActivityPanel({ workspaceId, connectorId }: { workspaceId: string; connectorId: string }) {
  const t = useTranslations("workspaces.connectors");
  const query = useQuery({
    queryKey: ["workspace-owner", workspaceId, "connectors", connectorId, "deliveries"],
    queryFn: () => listConnectorDeliveries(workspaceId, connectorId),
  });
  const deliveries = query.data?.items ?? [];
  const delivered = deliveries.filter((item) => item.status === "delivered").length;
  const failed = deliveries.filter((item) => ["failed", "dead_lettered"].includes(item.status)).length;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Activity className="h-4 w-4" />
          {t("activity")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-md border p-3"><p className="text-2xl font-semibold">{delivered}</p><p className="text-xs text-muted-foreground">{t("delivered")}</p></div>
          <div className="rounded-md border p-3"><p className="text-2xl font-semibold">{failed}</p><p className="text-xs text-muted-foreground">{t("failed")}</p></div>
        </div>
        <div className="space-y-2">
          {deliveries.slice(0, 6).map((delivery) => (
            <div key={delivery.id} className="flex items-center justify-between rounded-md border p-2 text-sm">
              <span className="truncate">{delivery.destination}</span>
              <Badge variant={delivery.status === "delivered" ? "secondary" : "outline"}>{delivery.status}</Badge>
            </div>
          ))}
          {!deliveries.length ? <p className="text-sm text-muted-foreground">{t("noDeliveries")}</p> : null}
        </div>
      </CardContent>
    </Card>
  );
}
