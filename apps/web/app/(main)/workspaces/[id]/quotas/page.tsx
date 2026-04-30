"use client";

import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { WorkspaceOwnerLayout } from "@/components/layout/WorkspaceOwnerLayout";
import { EmptyState } from "@/components/shared/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkspaceSettings } from "@/lib/hooks/use-workspace-settings";
import { QuotaConfigForm } from "../settings/_components/QuotaConfigForm";

export default function WorkspaceQuotasPage() {
  const params = useParams<{ id: string }>();
  const settings = useWorkspaceSettings(params.id);
  const t = useTranslations("workspaces.quotas");

  return (
    <WorkspaceOwnerLayout title={t("title")} description={t("description")}>
      {settings.isLoading ? <Skeleton className="h-80 rounded-lg" /> : null}
      {settings.isError ? (
        <EmptyState title={t("unavailable")} description={t("unavailableDescription")} />
      ) : null}
      {settings.data ? <QuotaConfigForm settings={settings.data} workspaceId={params.id} /> : null}
    </WorkspaceOwnerLayout>
  );
}
