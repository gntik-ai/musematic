"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { WorkspaceOwnerLayout } from "@/components/layout/WorkspaceOwnerLayout";
import { EmptyState } from "@/components/shared/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getVisibilityGrant } from "@/lib/api/workspace-owner";
import { VisibilityGraph } from "./_components/VisibilityGraph";

export default function WorkspaceVisibilityPage() {
  const params = useParams<{ id: string }>();
  const visibility = useQuery({
    queryKey: ["workspace-owner", params.id, "visibility"],
    queryFn: () => getVisibilityGrant(params.id),
  });
  const [tab, setTab] = useState("graph");
  const t = useTranslations("workspaces.visibility");

  return (
    <WorkspaceOwnerLayout title={t("title")} description={t("description")}>
      {visibility.isLoading ? <Skeleton className="h-[680px] rounded-lg" /> : null}
      {visibility.isError ? (
        <EmptyState title={t("unavailable")} description={t("unavailableDescription")} />
      ) : null}
      {visibility.data ? (
        <Tabs>
          <TabsList>
            <TabsTrigger onClick={() => setTab("graph")}>{t("grantsGiven")}</TabsTrigger>
            <TabsTrigger onClick={() => setTab("received")}>{t("grantsReceived")}</TabsTrigger>
            <TabsTrigger onClick={() => setTab("audit")}>{t("auditTrail")}</TabsTrigger>
          </TabsList>
          {tab === "graph" ? (
            <TabsContent><VisibilityGraph grant={visibility.data} /></TabsContent>
          ) : null}
          {tab === "received" ? (
          <TabsContent>
            <EmptyState title={t("noInboundGrants")} description={t("inboundUnavailable")} />
          </TabsContent>
          ) : null}
          {tab === "audit" ? (
          <TabsContent>
            <EmptyState title={t("auditTrail")} description={t("auditUnavailable")} />
          </TabsContent>
          ) : null}
        </Tabs>
      ) : null}
    </WorkspaceOwnerLayout>
  );
}
