"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { WorkspaceOwnerLayout } from "@/components/layout/WorkspaceOwnerLayout";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { getWorkspaceConnector } from "@/lib/api/workspace-owner";
import { ConnectorActivityPanel } from "../_components/ConnectorActivityPanel";
import { RotateSecretDialog } from "../_components/RotateSecretDialog";

export default function WorkspaceConnectorDetailPage() {
  const params = useParams<{ id: string; connectorId: string }>();
  const t = useTranslations("workspaces.connectors");
  const connector = useQuery({
    queryKey: ["workspace-owner", params.id, "connectors", params.connectorId],
    queryFn: () => getWorkspaceConnector(params.id, params.connectorId),
  });

  return (
    <WorkspaceOwnerLayout title={t("details")} description={t("detailsDescription")}>
      {connector.isLoading ? <Skeleton className="h-96 rounded-lg" /> : null}
      {connector.data ? (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
          <Card>
            <CardHeader>
              <CardTitle>{connector.data.name}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap gap-2">
                <Badge variant="secondary">{t("workspaceOwned")}</Badge>
                <Badge variant="outline">{connector.data.connector_type_slug}</Badge>
                <Badge variant="outline">{connector.data.status}</Badge>
                <Badge variant="outline">{connector.data.health_status}</Badge>
              </div>
              <pre className="overflow-auto rounded-md bg-muted p-3 text-xs">
                {JSON.stringify(connector.data.config, null, 2)}
              </pre>
              <RotateSecretDialog />
            </CardContent>
          </Card>
          <ConnectorActivityPanel workspaceId={params.id} connectorId={params.connectorId} />
        </div>
      ) : null}
    </WorkspaceOwnerLayout>
  );
}
