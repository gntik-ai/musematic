"use client";

import { useParams } from "next/navigation";
import { WorkspaceOwnerLayout } from "@/components/layout/WorkspaceOwnerLayout";
import { EmptyState } from "@/components/shared/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkspaceSettings } from "@/lib/hooks/use-workspace-settings";
import { QuotaConfigForm } from "../settings/_components/QuotaConfigForm";

export default function WorkspaceQuotasPage() {
  const params = useParams<{ id: string }>();
  const settings = useWorkspaceSettings(params.id);

  return (
    <WorkspaceOwnerLayout title="Quotas" description="Per-resource quota controls for workspace-owned capacity.">
      {settings.isLoading ? <Skeleton className="h-80 rounded-lg" /> : null}
      {settings.isError ? <EmptyState title="Quotas unavailable" description="The workspace settings endpoint did not return data." /> : null}
      {settings.data ? <QuotaConfigForm settings={settings.data} workspaceId={params.id} /> : null}
    </WorkspaceOwnerLayout>
  );
}
