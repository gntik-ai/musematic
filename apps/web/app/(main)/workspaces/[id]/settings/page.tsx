"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
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
  const t = useTranslations("workspaces.settings");

  return (
    <WorkspaceOwnerLayout title={t("title")} description={t("description")}>
      {settings.isLoading ? <Skeleton className="h-96 rounded-lg" /> : null}
      {settings.isError ? (
        <EmptyState title={t("unavailable")} description={t("unavailableDescription")} />
      ) : null}
      {settings.data ? (
        <Tabs>
          <TabsList className="grid w-full grid-cols-2 md:grid-cols-4">
            <TabsTrigger onClick={() => setTab("budget")}>{t("tabs.budget")}</TabsTrigger>
            <TabsTrigger onClick={() => setTab("quotas")}>{t("tabs.quotas")}</TabsTrigger>
            <TabsTrigger onClick={() => setTab("dlp")}>{t("tabs.dlp")}</TabsTrigger>
            <TabsTrigger onClick={() => setTab("residency")}>{t("tabs.residency")}</TabsTrigger>
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
