"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { PlugZap } from "lucide-react";
import { useTranslations } from "next-intl";
import { WorkspaceOwnerLayout } from "@/components/layout/WorkspaceOwnerLayout";
import { EmptyState } from "@/components/shared/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { listWorkspaceConnectors } from "@/lib/api/workspace-owner";
import { ConnectorSetupWizard } from "./_components/ConnectorSetupWizard";

export default function WorkspaceConnectorsPage() {
  const params = useParams<{ id: string }>();
  const workspaceId = params.id;
  const t = useTranslations("workspaces.connectors");
  const connectors = useQuery({
    queryKey: ["workspace-owner", workspaceId, "connectors"],
    queryFn: () => listWorkspaceConnectors(workspaceId),
  });

  return (
    <WorkspaceOwnerLayout title={t("title")} description={t("description")}>
      <div className="space-y-4">
        <div className="flex justify-end"><ConnectorSetupWizard /></div>
        {connectors.isLoading ? <Skeleton className="h-72 rounded-lg" /> : null}
        {connectors.isError ? (
          <EmptyState title={t("unavailable")} description={t("unavailableDescription")} />
        ) : null}
        {connectors.data?.items.length ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {connectors.data.items.map((connector) => (
              <Card key={connector.id}>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <PlugZap className="h-4 w-4" />
                    {connector.name}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="secondary">{t("workspaceOwned")}</Badge>
                    <Badge variant="outline">{connector.connector_type_slug}</Badge>
                    <Badge variant="outline">{connector.health_status}</Badge>
                  </div>
                  <Button asChild className="w-full" size="sm">
                    <Link href={`/workspaces/${workspaceId}/connectors/${connector.id}`}>
                      {t("openDetail")}
                    </Link>
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : null}
        {connectors.data && connectors.data.items.length === 0 ? (
          <EmptyState title={t("empty")} description={t("emptyDescription")} />
        ) : null}
      </div>
    </WorkspaceOwnerLayout>
  );
}
