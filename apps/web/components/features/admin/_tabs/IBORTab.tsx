"use client";

import { useMemo, useState } from "react";
import { RefreshCw, ServerCog } from "lucide-react";
import { useTranslations } from "next-intl";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useIBORConnectors, useIBORSyncNow, useIBORTestConnection } from "@/lib/hooks/use-ibor-admin";
import type { IBORConnector } from "@/lib/schemas/workspace-owner";
import { IBORConnectorWizard } from "./_components/IBORConnectorWizard";
import { SyncHistoryDrillDown } from "./_components/SyncHistoryDrillDown";

export function IBORTab() {
  const t = useTranslations("admin.ibor");
  const connectors = useIBORConnectors();
  const testConnection = useIBORTestConnection();
  const syncNow = useIBORSyncNow();
  const [selectedConnectorId, setSelectedConnectorId] = useState<string | null>(null);
  const selectedConnector = useMemo(() => {
    return (connectors.data?.items ?? []).find((item) => item.id === selectedConnectorId) ?? null;
  }, [connectors.data?.items, selectedConnectorId]);

  function handleCreated(connector: IBORConnector) {
    setSelectedConnectorId(connector.id);
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ServerCog className="h-4 w-4" />
            {t("title")}
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            {t("description")}
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("table.name")}</TableHead>
                  <TableHead>{t("table.type")}</TableHead>
                  <TableHead>{t("history.status")}</TableHead>
                  <TableHead>{t("table.lastRun")}</TableHead>
                  <TableHead className="w-[220px]">{t("table.actions")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(connectors.data?.items ?? []).map((connector) => (
                  <TableRow key={connector.id}>
                    <TableCell className="font-medium">{connector.name}</TableCell>
                    <TableCell>{connector.source_type.toUpperCase()}</TableCell>
                    <TableCell>
                      <Badge variant={connector.enabled ? "secondary" : "outline"}>
                        {connector.last_run_status ?? (connector.enabled ? t("enabled") : t("disabled"))}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {connector.last_run_at ? new Date(connector.last_run_at).toLocaleString() : t("never")}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          size="sm"
                          type="button"
                          variant="outline"
                          onClick={() => setSelectedConnectorId(connector.id)}
                        >
                          {t("details")}
                        </Button>
                        <Button
                          size="sm"
                          type="button"
                          variant="outline"
                          onClick={() => testConnection.mutate(connector.id)}
                        >
                          {t("test")}
                        </Button>
                        <Button
                          size="sm"
                          type="button"
                          onClick={() => syncNow.mutate(connector.id)}
                        >
                          <RefreshCw className="h-4 w-4" />
                          {t("sync")}
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          {connectors.data?.items.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("noConnectors")}</p>
          ) : null}
        </CardContent>
      </Card>

      <IBORConnectorWizard onCreated={handleCreated} />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <SyncHistoryDrillDown connectorId={selectedConnectorId} />
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("selectedConnector")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {selectedConnector ? (
              <>
                <p className="font-medium">{selectedConnector.name}</p>
                <p className="text-muted-foreground">{selectedConnector.credential_ref}</p>
                <p>{t("cadence", { seconds: selectedConnector.cadence_seconds })}</p>
              </>
            ) : (
              <p className="text-muted-foreground">{t("selectConnector")}</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
