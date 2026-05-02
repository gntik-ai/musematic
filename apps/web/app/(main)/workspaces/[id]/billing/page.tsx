"use client";

import { useParams } from "next/navigation";
import { WorkspaceOwnerLayout } from "@/components/layout/WorkspaceOwnerLayout";
import { BillingDashboardCard } from "@/components/features/billing/BillingDashboardCard";

export default function WorkspaceBillingPage() {
  const params = useParams<{ id: string }>();

  return (
    <WorkspaceOwnerLayout title="Billing" description="Plan, quota, and overage controls.">
      <BillingDashboardCard workspaceId={params.id} />
    </WorkspaceOwnerLayout>
  );
}
