"use client";

import { useParams } from "next/navigation";
import { WorkspaceOwnerLayout } from "@/components/layout/WorkspaceOwnerLayout";
import { UpgradeForm } from "@/components/features/billing/UpgradeForm";

export default function UpgradePage() {
  const params = useParams<{ id: string }>();
  return (
    <WorkspaceOwnerLayout title="Upgrade" description="Move this workspace to Pro.">
      <UpgradeForm workspaceId={params.id} />
    </WorkspaceOwnerLayout>
  );
}
