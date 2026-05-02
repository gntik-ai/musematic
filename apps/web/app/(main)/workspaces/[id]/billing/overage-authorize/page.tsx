"use client";

import { useParams } from "next/navigation";
import { WorkspaceOwnerLayout } from "@/components/layout/WorkspaceOwnerLayout";
import { OverageAuthorizationForm } from "@/components/features/billing/OverageAuthorizationForm";

export default function OverageAuthorizePage() {
  const params = useParams<{ id: string }>();

  return (
    <WorkspaceOwnerLayout
      title="Overage authorization"
      description="Set or revoke the current billing-period overage cap."
    >
      <OverageAuthorizationForm workspaceId={params.id} />
    </WorkspaceOwnerLayout>
  );
}
