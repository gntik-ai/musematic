"use client";

import { useMemo, useState } from "react";
import { RefreshCw, ServerCog } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useIBORConnectors, useIBORSyncNow, useIBORTestConnection } from "@/lib/hooks/use-ibor-admin";
import type { IBORConnector } from "@/lib/schemas/workspace-owner";
import { IBORConnectorWizard } from "./_components/IBORConnectorWizard";
import { SyncHistoryDrillDown } from "./_components/SyncHistoryDrillDown";

export function IBORTab() {
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
            IBOR connectors
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            Manage LDAP, OIDC, and SCIM identity-broker sync connectors.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Last run</TableHead>
                  <TableHead className="w-[220px]">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(connectors.data?.items ?? []).map((connector) => (
                  <TableRow key={connector.id}>
                    <TableCell className="font-medium">{connector.name}</TableCell>
                    <TableCell>{connector.source_type.toUpperCase()}</TableCell>
                    <TableCell>
                      <Badge variant={connector.enabled ? "secondary" : "outline"}>
                        {connector.last_run_status ?? (connector.enabled ? "enabled" : "disabled")}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {connector.last_run_at ? new Date(connector.last_run_at).toLocaleString() : "Never"}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          size="sm"
                          type="button"
                          variant="outline"
                          onClick={() => setSelectedConnectorId(connector.id)}
                        >
                          Details
                        </Button>
                        <Button
                          size="sm"
                          type="button"
                          variant="outline"
                          onClick={() => testConnection.mutate(connector.id)}
                        >
                          Test
                        </Button>
                        <Button
                          size="sm"
                          type="button"
                          onClick={() => syncNow.mutate(connector.id)}
                        >
                          <RefreshCw className="h-4 w-4" />
                          Sync
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          {connectors.data?.items.length === 0 ? (
            <p className="text-sm text-muted-foreground">No IBOR connectors configured.</p>
          ) : null}
        </CardContent>
      </Card>

      <IBORConnectorWizard onCreated={handleCreated} />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <SyncHistoryDrillDown connectorId={selectedConnectorId} />
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Selected connector</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {selectedConnector ? (
              <>
                <p className="font-medium">{selectedConnector.name}</p>
                <p className="text-muted-foreground">{selectedConnector.credential_ref}</p>
                <p>Cadence: {selectedConnector.cadence_seconds}s</p>
              </>
            ) : (
              <p className="text-muted-foreground">Select a connector to inspect sync history.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
