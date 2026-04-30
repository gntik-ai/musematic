"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
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

  return (
    <WorkspaceOwnerLayout title="Visibility" description="Read-only graph for workspace zero-trust grants and audit context.">
      {visibility.isLoading ? <Skeleton className="h-[680px] rounded-lg" /> : null}
      {visibility.isError ? <EmptyState title="Visibility unavailable" description="The visibility endpoint did not return data." /> : null}
      {visibility.data ? (
        <Tabs>
          <TabsList>
            <TabsTrigger onClick={() => setTab("graph")}>Grants given</TabsTrigger>
            <TabsTrigger onClick={() => setTab("received")}>Grants received</TabsTrigger>
            <TabsTrigger onClick={() => setTab("audit")}>Audit trail</TabsTrigger>
          </TabsList>
          {tab === "graph" ? (
            <TabsContent><VisibilityGraph grant={visibility.data} /></TabsContent>
          ) : null}
          {tab === "received" ? (
          <TabsContent>
            <EmptyState title="No inbound grants" description="Inbound grant aggregation is not exposed by the current API." />
          </TabsContent>
          ) : null}
          {tab === "audit" ? (
          <TabsContent>
            <EmptyState title="Audit trail" description="Visibility audit entries are available from the audit-chain query surface." />
          </TabsContent>
          ) : null}
        </Tabs>
      ) : null}
    </WorkspaceOwnerLayout>
  );
}
