"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { WorkspaceOwnerLayout } from "@/components/layout/WorkspaceOwnerLayout";
import { EmptyState } from "@/components/shared/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useWorkspaceSettings } from "@/lib/hooks/use-workspace-settings";
import { BudgetForm } from "./_components/BudgetForm";
import { DLPRulesForm } from "./_components/DLPRulesForm";
import { QuotaConfigForm } from "./_components/QuotaConfigForm";
import { ResidencyForm } from "./_components/ResidencyForm";

export default function WorkspaceSettingsPage() {
  const params = useParams<{ id: string }>();
  const settings = useWorkspaceSettings(params.id);
  const [tab, setTab] = useState("budget");

  return (
    <WorkspaceOwnerLayout title="Settings" description="Budget, quota, DLP, and residency controls scoped to this workspace.">
      {settings.isLoading ? <Skeleton className="h-96 rounded-lg" /> : null}
      {settings.isError ? <EmptyState title="Settings unavailable" description="The workspace settings endpoint did not return data." /> : null}
      {settings.data ? (
        <Tabs>
          <TabsList className="grid w-full grid-cols-2 md:grid-cols-4">
            <TabsTrigger onClick={() => setTab("budget")}>Budget</TabsTrigger>
            <TabsTrigger onClick={() => setTab("quotas")}>Quotas</TabsTrigger>
            <TabsTrigger onClick={() => setTab("dlp")}>DLP</TabsTrigger>
            <TabsTrigger onClick={() => setTab("residency")}>Residency</TabsTrigger>
          </TabsList>
          {tab === "budget" ? (
          <TabsContent>
            <BudgetForm settings={settings.data} workspaceId={params.id} />
          </TabsContent>
          ) : null}
          {tab === "quotas" ? (
          <TabsContent>
            <QuotaConfigForm settings={settings.data} workspaceId={params.id} />
          </TabsContent>
          ) : null}
          {tab === "dlp" ? (
          <TabsContent>
            <DLPRulesForm settings={settings.data} workspaceId={params.id} />
          </TabsContent>
          ) : null}
          {tab === "residency" ? (
          <TabsContent>
            <ResidencyForm settings={settings.data} workspaceId={params.id} />
          </TabsContent>
          ) : null}
        </Tabs>
      ) : null}
    </WorkspaceOwnerLayout>
  );
}
