"use client";

import { useParams } from "next/navigation";
import { WorkspaceOwnerLayout } from "@/components/layout/WorkspaceOwnerLayout";
import { ExportJobCard } from "@/components/features/data-lifecycle/ExportJobCard";

export default function WorkspaceDataExportPage() {
  const params = useParams<{ id: string }>();

  return (
    <WorkspaceOwnerLayout
      title="Data export"
      description="Request a full archive of your workspace data."
    >
      <ExportJobCard workspaceId={params.id} />
    </WorkspaceOwnerLayout>
  );
}
