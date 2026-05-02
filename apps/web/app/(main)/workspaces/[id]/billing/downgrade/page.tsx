"use client";

import { useParams } from "next/navigation";
import { WorkspaceOwnerLayout } from "@/components/layout/WorkspaceOwnerLayout";
import { DowngradeForm } from "@/components/features/billing/DowngradeForm";

export default function DowngradePage() {
  const params = useParams<{ id: string }>();
  return (
    <WorkspaceOwnerLayout title="Downgrade" description="Schedule a change at period end.">
      <DowngradeForm workspaceId={params.id} />
    </WorkspaceOwnerLayout>
  );
}
